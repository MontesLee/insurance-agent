/**
 * E2E: the real chain, end to end — select case -> POST /api/runs -> SSE stream
 * -> stage progress -> eval -> artifact -> run_completed -> report visible.
 *
 * The SSE events are folded through the SAME reducer the React UI uses, so this
 * test proves: UI pipeline === runtime event sequence (no client-side invention)
 * and UI run_id === SSE run_id === RunManager run_id.
 *
 * Skipped by default (needs the real python runtime). Run with:
 *   E2E_RUNTIME=1 npm test        (from web/)
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { spawn, type ChildProcess } from "node:child_process";
import { resolve } from "node:path";
import { initRunState, runReducer } from "../state/runReducer";
import type { RuntimeEvent } from "../types/runtime";

const REPO = resolve(__dirname, "../../..");
const PORT = 8117;
const BASE = `http://127.0.0.1:${PORT}`;
const CASE = "bm-complete-006-single-medical"; // demo-a: full chain -> grounded report

const enabled = !!process.env.E2E_RUNTIME;

describe.skipIf(!enabled)("E2E: real runtime chain (case -> run -> SSE -> pipeline -> report)", () => {
  let server: ChildProcess;

  beforeAll(async () => {
    server = spawn("python", ["-m", "runtime.server", "--port", String(PORT)], {
      cwd: REPO,
      stdio: "ignore",
      shell: process.platform === "win32",
    });
    const deadline = Date.now() + 30_000;
    for (;;) {
      try {
        const r = await fetch(`${BASE}/api/health`);
        if (r.ok) return;
      } catch {
        /* not up yet */
      }
      if (Date.now() > deadline) throw new Error("runtime server did not start");
      await new Promise((res) => setTimeout(res, 300));
    }
  }, 45_000);

  afterAll(() => {
    server?.kill();
  });

  it(
    "drives one full run and folds it through the UI reducer",
    async () => {
      // ---- 1) select case -> POST /api/runs -------------------------------- #
      const created = (await (
        await fetch(`${BASE}/api/runs`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ case_id: CASE }),
        })
      ).json()) as { run_id: string; case_id: string; status: string };
      expect(created.run_id).toMatch(/^run_/);
      expect(created.case_id).toBe(CASE);

      // ---- 2) SSE stream until the terminal event --------------------------- #
      const events: RuntimeEvent[] = await streamUntilTerminal(`${BASE}/api/runs/${created.run_id}/stream`);
      expect(events.length).toBeGreaterThan(20);
      expect(events[0]!.event_type).toBe("run_started");
      expect(events[events.length - 1]!.event_type).toBe("run_completed");
      expect((events[events.length - 1]! as { status?: string }).status).toBe("completed");

      // ---- 3) run_id / case_id provenance on every event -------------------- #
      for (const e of events) {
        expect(e.run_id).toBe(created.run_id); // SSE run_id === RunManager run_id
        expect(e.case_id).toBe(CASE);
      }

      // ---- 4) fold through the SAME reducer the UI renders ------------------ #
      const meta = (await (await fetch(`${BASE}/api/runs/${created.run_id}`)).json()) as {
        stage_order: { id: string; skill: string | null; produces: string | null }[];
        status: string;
      };
      let ui = initRunState(created.run_id, meta.stage_order);
      ui = runReducer(ui, { type: "events", events })!;

      expect(meta.stage_order).toHaveLength(8);
      expect(ui.status).toBe("completed");
      // UI pipeline === runtime event sequence: every stage reached via its events
      for (const st of Object.values(ui.stages)) {
        expect(st.status, `stage ${st.id}`).toBe("passed");
      }
      // eval surface: 9 canonical artifacts evaluated, all PASS on this case
      expect(ui.evals.filter((e) => e.status === "pass").length).toBeGreaterThanOrEqual(9);
      expect(ui.evals.filter((e) => e.status === "fail")).toHaveLength(0);

      // ---- 5) artifacts + report --------------------------------------------- #
      const artifacts = (await (
        await fetch(`${BASE}/api/runs/${created.run_id}/artifacts`)
      ).json()) as { artifacts: { artifact_type: string; lineage: unknown[] }[] };
      const types = artifacts.artifacts.map((a) => a.artifact_type);
      expect(types).toContain("insurance-report");
      const report = artifacts.artifacts.find((a) => a.artifact_type === "insurance-report")!;
      expect(report.lineage.length).toBeGreaterThanOrEqual(8); // full provenance chain

      const detail = (await (
        await fetch(`${BASE}/api/runs/${created.run_id}/artifacts/insurance-report`)
      ).json()) as { artifact: { payload?: { rendered_report?: string; status?: string } } };
      expect(detail.artifact.payload?.status).toBe("success");
      expect(detail.artifact.payload?.rendered_report).toContain("客户保险需求分析报告");

      // ---- 6) the run the UI would show is the run the runtime executed ----- #
      const finalRun = (await (await fetch(`${BASE}/api/runs/${created.run_id}`)).json()) as {
        run_id: string;
        status: string;
        event_count: number;
      };
      expect(finalRun.run_id).toBe(ui.runId);
      expect(finalRun.status).toBe("completed");
      expect(finalRun.event_count).toBe(events.length);
    },
    120_000,
  );
});

async function streamUntilTerminal(url: string): Promise<RuntimeEvent[]> {
  const resp = await fetch(url, { headers: { Accept: "text/event-stream" } });
  if (!resp.ok || !resp.body) throw new Error(`stream failed: ${resp.status}`);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const out: RuntimeEvent[] = [];

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of block.split("\n")) {
        if (line.startsWith("data: ")) {
          const event = JSON.parse(line.slice(6)) as RuntimeEvent;
          out.push(event);
          if (event.event_type === "run_completed" || event.event_type === "run_failed") {
            return out;
          }
        }
      }
    }
  }
  return out;
}
