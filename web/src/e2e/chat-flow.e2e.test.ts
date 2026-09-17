/**
 * E2E: the CHAT flow against the real python runtime (§34).
 *
 * Open chat → new conversation → prompt maps to a demo case → send →
 * POST /api/runs → SSE RuntimeEvents → same reducers the UI uses
 * (runReducer + chatsReducer) → Agent Activity pipeline → eval → artifact →
 * completed → final assistant message + report artifact card.
 *
 * Run with: E2E_RUNTIME=1 npm test
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { spawn, type ChildProcess } from "node:child_process";
import { resolve } from "node:path";
import { chatsReducer, mapPromptToCase, makeChat, finalAssistantText } from "../state/chatState";
import { initRunState, runReducer } from "../state/runReducer";
import { latestActivity } from "../state/activity";
import type { RuntimeEvent } from "../types/runtime";

const REPO = resolve(__dirname, "../../..");
const PORT = 8119;
const BASE = `http://127.0.0.1:${PORT}`;
const enabled = !!process.env.E2E_RUNTIME;

describe.skipIf(!enabled)("E2E: chat → run → SSE → activity → report (real backend)", () => {
  let server: ChildProcess;

  beforeAll(async () => {
    server = spawn("python", ["-m", "runtime.server", "--port", String(PORT)], {
      cwd: REPO, stdio: "ignore", shell: process.platform === "win32",
    });
    const deadline = Date.now() + 30_000;
    for (;;) {
      try {
        if ((await fetch(`${BASE}/api/health`)).ok) return;
      } catch { /* not up yet */ }
      if (Date.now() > deadline) throw new Error("runtime server did not start");
      await new Promise((r) => setTimeout(r, 300));
    }
  }, 45_000);

  afterAll(() => server?.kill());

  it("drives one full chat conversation through the same reducers the UI renders", async () => {
    // ---- user sends a prompt in a fresh chat ------------------------------ #
    const prompt = "给孩子配置重疾险前，我应该先考虑什么？";
    const caseId = mapPromptToCase(prompt);
    expect(caseId).toBe("bm-complete-001");

    let chat = makeChat(caseId, "新对话");
    chat = chatsReducer([chat], { type: "send", chatId: chat.id, text: prompt, caseId })[0]!;
    expect(chat.messages[0]).toMatchObject({ kind: "user", text: prompt });
    expect(chat.title).toBe(prompt.slice(0, 24));

    // ---- POST /api/runs (the ONLY execution path — no second engine) ------ #
    const created = (await (
      await fetch(`${BASE}/api/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: caseId }),
      })
    ).json()) as { run_id: string };
    chat = chatsReducer([chat], { type: "bindRun", chatId: chat.id, runId: created.run_id })[0]!;
    expect(chat.runId).toBe(created.run_id);
    expect(chat.messages.some((m) => m.kind === "activity" && m.runId === created.run_id)).toBe(true);

    // ---- SSE stream → the UI's runReducer --------------------------------- #
    const meta = (await (await fetch(`${BASE}/api/runs/${created.run_id}`)).json()) as {
      stage_order: { id: string; skill: string | null; produces: string | null }[];
    };
    const events = await streamUntilTerminal(`${BASE}/api/runs/${created.run_id}/stream`);
    let ui = initRunState(created.run_id, meta.stage_order);
    ui = runReducer(ui, { type: "events", events })!;

    for (const e of events) {
      expect(e.run_id).toBe(created.run_id); // chat run === SSE run === RunManager run
      expect(e.case_id).toBe(caseId);
    }
    expect(events[0]!.event_type).toBe("run_started");
    expect(events.at(-1)!.event_type).toBe("run_completed");
    expect(events.at(-1)!.status).toBe("completed");

    // what the Agent Activity card would show: all 8 stages passed, evals green
    expect(meta.stage_order).toHaveLength(8);
    for (const st of Object.values(ui.stages)) expect(st.status, st.id).toBe("passed");
    expect(ui.evals.filter((e) => e.status === "pass").length).toBeGreaterThanOrEqual(9);
    expect(latestActivity(events)).toBe("分析完成"); // no chain-of-thought anywhere

    // ---- finalize the transcript exactly like ChatLayout does ------------- #
    const artifactType =
      meta.stage_order.find((s) => s.id === "report-generation")?.produces ?? "insurance-report";
    chat = chatsReducer([chat], {
      type: "finalize", chatId: chat.id, runId: created.run_id, status: "completed",
      artifactType, artifactTitle: "客户保险需求分析报告",
    })[0]!;
    const kinds = chat.messages.map((m) => m.kind);
    expect(kinds).toEqual(["user", "activity", "assistant", "artifact"]);
    expect(chat.messages[2]!.kind === "assistant" && chat.messages[2]!.text).toBe(finalAssistantText("completed"));
    // idempotent on refresh-replay
    chat = chatsReducer([chat], {
      type: "finalize", chatId: chat.id, runId: created.run_id, status: "completed",
      artifactType, artifactTitle: "客户保险需求分析报告",
    })[0]!;
    expect(chat.messages).toHaveLength(4);

    // ---- the artifact card's report is real -------------------------------- #
    const detail = (await (
      await fetch(`${BASE}/api/runs/${created.run_id}/artifacts/${artifactType}`)
    ).json()) as { artifact: { payload?: { rendered_report?: string } } };
    expect(detail.artifact.payload?.rendered_report).toContain("客户保险需求分析报告");

    // ---- a second chat sending the SAME case while it is done → 201 again;
    //      while running → 409 contract (Phase 1.1) ------------------------- #
    const run2 = await fetch(`${BASE}/api/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: "bm-noev-001" }),
    });
    expect(run2.status).toBe(201);
    const r2 = (await run2.json()) as { run_id: string };
    // immediately start another run of the SAME case while r2 is executing
    const run3 = await fetch(`${BASE}/api/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: "bm-noev-001" }),
    });
    const body3 = (await run3.json()) as { error?: string; run_id?: string };
    if (run3.status === 409) {
      expect(body3.error).toBe("case_already_running");
      expect(body3.run_id).toBe(r2.run_id);
    } else {
      // r2 finished before run3 landed (fast engine) — then it must be 201
      expect(run3.status).toBe(201);
    }
    // drain r2 so the server quiets down
    await streamUntilTerminal(`${BASE}/api/runs/${r2.run_id}/stream`);
  }, 120_000);
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
          if (event.event_type === "run_completed" || event.event_type === "run_failed") return out;
        }
      }
    }
  }
  return out;
}
