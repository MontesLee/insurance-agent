import { beforeEach, describe, expect, it, vi } from "vitest";
import type * as ChatPerf from "./chatPerf";

// minimal Performance API stub (jsdom lacks mark/getEntriesByName)
const entries: { name: string; startTime: number }[] = [];
let clock = 0;

class MockPerformance {
  mark(name: string) {
    entries.push({ name, startTime: ++clock * 100 });
  }
  getEntriesByName(name: string) {
    return entries.filter((e) => e.name === name);
  }
}

// fresh module per test (module-level mark state must not leak)
async function fresh(): Promise<typeof ChatPerf> {
  vi.resetModules();
  return await import("./chatPerf");
}

describe("chatPerf marks (28.K.28 passive observation)", () => {
  beforeEach(() => {
    entries.length = 0;
    clock = 0;
    sessionStorage.clear();
  });

  it("records first occurrences only, in submit-relative ms", async () => {
    vi.stubGlobal("performance", new MockPerformance());
    const p = await fresh();
    p.markSubmit();            // 100
    p.markFirstEvent();        // 200
    p.markFirstEvent();        // duplicate — ignored
    p.markFirstContentDelta(); // 300
    p.markTerminal();          // 400
    p.markFinalRender();       // 500
    p.reportTurn("run_x");

    const raw = sessionStorage.getItem("webui:perf:last");
    expect(raw).toBeTruthy();
    const s = JSON.parse(raw!);
    expect(s.runId).toBe("run_x");
    expect(s.firstEventMs).toBe(100);
    expect(s.firstContentMs).toBe(200);
    expect(s.terminalMs).toBe(300);
    expect(s.finalRenderMs).toBe(400);
  });

  it("a new turn resets the mark set (marks re-recordable)", async () => {
    vi.stubGlobal("performance", new MockPerformance());
    const p = await fresh();
    p.markSubmit();
    p.markTerminal();
    p.markSubmit();            // next turn
    p.markTerminal();
    expect(entries.filter((e) => e.name === "chat:terminal")).toHaveLength(2);
  });

  it("never throws when the Performance API is missing", async () => {
    vi.stubGlobal("performance", undefined);
    const p = await fresh();
    expect(() => {
      p.markSubmit();
      p.markFirstEvent();
      p.reportTurn(null);
    }).not.toThrow();
    // reporting degraded — no turn was tracked, no summary written
    expect(sessionStorage.getItem("webui:perf:last")).toBeNull();
  });
});
