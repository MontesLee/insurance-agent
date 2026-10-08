/**
 * chatPerf — 28.K.28 frontend latency marks (passive observation only).
 *
 * Records the browser-side timeline of ONE chat turn:
 *
 *     submit  ->  first event  ->  first content delta  ->  terminal
 *             ->  final render
 *
 * Marks ride the standard Performance API; nothing here can break the
 * chat (every call is fail-quiet). The summary of the last turn is
 * stashed in sessionStorage for inspection (console at terminal +
 * `sessionStorage.getItem("webui:perf:last")`).
 */

const MARKS = ["chat:submit", "chat:first-event", "chat:first-content",
  "chat:terminal", "chat:final-render"] as const;
type MarkName = (typeof MARKS)[number];

const state: { turn: string; set: Set<MarkName> } = {
  turn: "", set: new Set(),
};

function mark(name: MarkName): void {
  try {
    if (state.set.has(name)) return; // first occurrence wins
    performance.mark(name);
    state.set.add(name); // only on success — a failed mark stays retryable
  } catch {
    /* Performance API unavailable — observation degrades to no-op */
  }
}

export function markSubmit(): void {
  state.turn = String(Date.now());
  state.set = new Set();
  mark("chat:submit");
}

export function markFirstEvent(): void {
  mark("chat:first-event");
}

export function markFirstContentDelta(): void {
  mark("chat:first-content");
}

export function markTerminal(): void {
  mark("chat:terminal");
}

export function markFinalRender(): void {
  mark("chat:final-render");
}

function sinceSubmit(name: MarkName): number | null {
  try {
    const m = performance.getEntriesByName(name, "mark")[0];
    const t0 = performance.getEntriesByName("chat:submit", "mark")[0];
    return m && t0 ? Math.round(m.startTime - t0.startTime) : null;
  } catch {
    return null;
  }
}

/** Compact turn summary (ms since submit) — console + sessionStorage. */
export function reportTurn(runId: string | null): void {
  try {
    // no tracked turn (e.g. Performance API unavailable) — nothing to
    // report, do not write an all-null summary
    if (!state.set.has("chat:submit")) return;
    const summary = {
      turn: state.turn, runId,
      firstEventMs: sinceSubmit("chat:first-event"),
      firstContentMs: sinceSubmit("chat:first-content"),
      terminalMs: sinceSubmit("chat:terminal"),
      finalRenderMs: sinceSubmit("chat:final-render"),
    };
    sessionStorage.setItem("webui:perf:last", JSON.stringify(summary));
    // eslint-disable-next-line no-console -- profiling output, dev-facing
    console.info("[chatPerf]", summary);
  } catch {
    /* storage/console unavailable — no-op */
  }
}
