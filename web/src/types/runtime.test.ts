/**
 * Dual-end event-vocabulary contract (Phase 28.B prep, Step 2) —
 * frontend guard. The EventType union in ./runtime.ts must EQUAL
 * schema/event-vocabulary.json "vocabulary" + "reserved": every backend
 * event type is nameable in typed frontend code (no silent swallow),
 * and nothing else drifts in. Mirror guard #1 (backend side):
 * tests/contract/test_event_vocabulary.py asserts vocabulary ==
 * runtime/events.py EVENT_TYPES.
 */
import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

// repo root discovery that works in every vitest environment (jsdom
// rewrites import.meta.url away from the file scheme): try cwd (web/)
// then its parent (repo root).
function findRepoRoot(): string {
  for (const c of [process.cwd(), join(process.cwd(), "..")]) {
    if (existsSync(join(c, "schema", "event-vocabulary.json"))) return c;
  }
  throw new Error("repo root not found from " + process.cwd());
}
const repoRoot = findRepoRoot();

const schema = JSON.parse(
  readFileSync(join(repoRoot, "schema", "event-vocabulary.json"), "utf8"),
) as { vocabulary: string[]; reserved: string[] };

const source = readFileSync(
  join(repoRoot, "web", "src", "types", "runtime.ts"),
  "utf8",
);
const unionBlock = source.slice(
  source.indexOf("export type EventType"),
  source.indexOf("RUN_TERMINAL_EVENT_TYPES"),
);
// only union members (`| "name"`), never quoted words inside comments
const unionTypes = Array.from(
  unionBlock.matchAll(/\|\s*"([a-z][a-z0-9_]*)"/g),
  (m) => m[1],
);

describe("event vocabulary contract (web side)", () => {
  it("EventType union equals schema vocabulary + reserved", () => {
    expect(new Set(unionTypes)).toEqual(
      new Set([...schema.vocabulary, ...schema.reserved]),
    );
  });

  it("union has no duplicates", () => {
    expect(unionTypes.length).toBe(new Set(unionTypes).size);
  });

  it("the router-migration telemetry types are receivable", () => {
    for (const t of [
      "intent_classified",
      "qa_answered",
      "grounding_started",
      "grounding_completed",
    ]) {
      expect(unionTypes).toContain(t);
    }
  });

  it("reserved types are exactly the contract-first pair (documented)", () => {
    expect(schema.reserved).toEqual([
      "grounding_started",
      "grounding_completed",
    ]);
  });
});
