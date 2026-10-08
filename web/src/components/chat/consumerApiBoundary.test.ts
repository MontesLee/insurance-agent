/**
 * Consumer API boundary (28.E-6 §30): consumer-surface components may
 * only call the consumer API surface. Internal endpoints (approvals,
 * supervisor, control, review-card, cases, metrics, diagnostics) must
 * never be referenced from consumer code — enforced by source scan,
 * the same approach as the backend's frontend-structure guard.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const CONSUMER_API_ALLOWLIST = new Set([
  "agentConfig", // provider-configured banner (no internals rendered)
  "createChat",
  "getChat",
  "postChatMessage",
  "getRun", // run metadata for the SSE view
  "runEvents",
  "getArtifact",
  "streamUrl",
  // 28.G identity + opaque artifact references
  "whoami",
  "issueArtifactRef",
  "artifactByRef",
]);

const FORBIDDEN_API = [
  "approvals", "approvalDetail", "approve", "reject", "supervisor",
  "alerts", "notifications", "control", "reviewCard", "cases",
  "createRun", "metrics", "diagnostics", "health",
];

const chatDir = join(__dirname);
const shellDir = join(__dirname, "..", "shell");

function consumerSources(): string[] {
  return readdirSync(chatDir)
    .filter((f) => f.endsWith(".tsx") && !f.endsWith(".test.tsx"))
    .map((f) => join(chatDir, f))
    .concat(
      readdirSync(shellDir)
        .filter((f) => f.endsWith("ConsumerShell.tsx"))
        .map((f) => join(shellDir, f)),
    );
}

describe("consumer API allowlist (source scan)", () => {
  it("chat/shell components call only the consumer API surface", () => {
    for (const path of consumerSources()) {
      const src = readFileSync(path, "utf-8");
      const used = [...src.matchAll(/api\.([A-Za-z]+)/g)].map((m) => m[1]!);
      for (const name of used) {
        expect(
          CONSUMER_API_ALLOWLIST.has(name),
          `${path} uses api.${name} — not on the consumer allowlist`,
        ).toBe(true);
      }
      for (const bad of FORBIDDEN_API) {
        expect(
          src.includes(`api.${bad}`),
          `${path} must not call api.${bad}`,
        ).toBe(false);
      }
    }
  });

  it("consumer sources exist (scan is not vacuous)", () => {
    expect(consumerSources().length).toBeGreaterThanOrEqual(5);
  });
});
