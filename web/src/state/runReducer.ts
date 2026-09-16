/**
 * Event -> UI state transitions. THE explicit mapping (no guessing):
 * every supported event_type has exactly one entry in TRANSITIONS, and nothing
 * outside that table may mutate pipeline/eval state. The UI is a projection of
 * the runtime event sequence — it never invents stage progress.
 */
import type { EventType, RuntimeEvent, RunStatus, StageInfo } from "../types/runtime";
import { RUN_TERMINAL_EVENT_TYPES } from "../types/runtime";

export type StageUiStatus = "pending" | "running" | "passed" | "failed" | "needs_review";

export interface StageUiState {
  id: string;
  status: StageUiStatus;
  attempts: number;
  repairAttempt: number | null;
  artifactId: string | null;
  evalId: string | null;
  lastEvalStatus: "pass" | "fail" | null;
  durationMs: number | null;
  lastEventAt: string | null;
}

export interface EvalUiEntry {
  key: string;
  evalId: string | null;
  stage: string | null;
  status: "running" | "pass" | "fail";
  at: string;
  repairAttempt: number | null;
}

export interface RunUiState {
  runId: string;
  status: RunStatus | "unknown";
  stageOrder: StageInfo[];
  stages: Record<string, StageUiState>;
  evals: EvalUiEntry[];
  events: RuntimeEvent[];
  currentStage: string | null;
  terminalEvent: RuntimeEvent | null;
  connected: boolean;
}

export function initRunState(runId: string, stageOrder: StageInfo[]): RunUiState {
  return {
    runId,
    status: "unknown",
    stageOrder,
    stages: Object.fromEntries(
      stageOrder.map((s) => [
        s.id,
        {
          id: s.id,
          status: "pending" satisfies StageUiStatus,
          attempts: 0,
          repairAttempt: null,
          artifactId: null,
          evalId: null,
          lastEvalStatus: null,
          durationMs: null,
          lastEventAt: null,
        } satisfies StageUiState,
      ]),
    ),
    evals: [],
    events: [],
    currentStage: null,
    terminalEvent: null,
    connected: false,
  };
}

function stage(state: RunUiState, id: string | null): StageUiState | null {
  if (!id) return null;
  return state.stages[id] ?? null;
}

/** Terminal run event status field -> authoritative Run status. */
function statusFromTerminal(e: RuntimeEvent): RunStatus {
  switch (e.status) {
    case "completed":
    case "needs_review":
    case "waiting":
    case "failed":
      return e.status;
    default:
      return "failed";
  }
}

/**
 * The explicit transition table. `void` entries = timeline-only events (they are
 * recorded, but must NOT move pipeline/eval state).
 */
const TRANSITIONS: Record<EventType, (s: RunUiState, e: RuntimeEvent) => void> = {
  run_started: (s, e) => {
    s.status = "running";
    s.currentStage = null;
    void e;
  },
  run_completed: (s, e) => {
    s.status = statusFromTerminal(e);
    s.currentStage = null;
    s.terminalEvent = e;
    // a run parked for human review keeps the blocked stage visibly flagged
    if (s.status === "needs_review") {
      const st = stage(s, e.stage) ?? lastFailedStage(s);
      if (st && (st.status === "failed" || st.status === "running")) st.status = "needs_review";
    }
  },
  run_failed: (s, e) => {
    s.status = "failed";
    s.currentStage = null;
    s.terminalEvent = e;
  },
  stage_started: (s, e) => {
    const st = stage(s, e.stage);
    if (!st) return;
    st.status = "running";
    st.attempts += 1;
    if (e.repair_attempt != null) st.repairAttempt = e.repair_attempt;
    st.lastEventAt = e.timestamp;
    s.currentStage = e.stage;
  },
  stage_completed: (s, e) => {
    const st = stage(s, e.stage);
    if (!st) return;
    st.status = "passed";
    st.artifactId = e.artifact_id ?? st.artifactId;
    st.lastEventAt = e.timestamp;
    const dur = e.data["duration_ms"];
    if (typeof dur === "number") st.durationMs = dur;
  },
  stage_failed: (s, e) => {
    const st = stage(s, e.stage);
    if (!st) return;
    st.status = "failed";
    st.lastEventAt = e.timestamp;
    s.currentStage = e.stage;
  },
  eval_started: (s, e) => {
    s.evals.push({
      key: e.event_id,
      evalId: e.eval_id,
      stage: e.stage,
      status: "running",
      at: e.timestamp,
      repairAttempt: e.repair_attempt,
    });
  },
  eval_passed: (s, e) => {
    closeEval(s, e, "pass");
    const st = stage(s, e.stage);
    if (st) st.lastEvalStatus = "pass";
  },
  eval_failed: (s, e) => {
    closeEval(s, e, "fail");
    const st = stage(s, e.stage);
    if (st) st.lastEvalStatus = "fail";
  },
  repair_started: (s, e) => {
    const st = stage(s, e.stage);
    if (st && e.repair_attempt != null) st.repairAttempt = e.repair_attempt;
  },
  repair_completed: (s, e) => {
    const st = stage(s, e.stage);
    if (st && e.repair_attempt != null) st.repairAttempt = e.repair_attempt;
  },
  repair_exhausted: (s, e) => {
    const st = stage(s, e.stage);
    if (st) st.status = "needs_review";
  },
  artifact_created: (s, e) => {
    const st = stage(s, e.stage);
    if (st && e.artifact_id) st.artifactId = e.artifact_id;
  },
  checkpoint_created: () => {},
  checkpoint_resumed: () => {},
  tool_started: () => {},
  tool_completed: () => {},
  tool_failed: () => {},
};

function closeEval(s: RunUiState, e: RuntimeEvent, outcome: "pass" | "fail") {
  // close the most recent 'running' eval of this stage (an eval_started may lack
  // eval_id; pairing by stage + order is deterministic in our event stream)
  for (let i = s.evals.length - 1; i >= 0; i--) {
    const ev = s.evals[i]!;
    if (ev.status === "running" && (ev.stage ?? null) === (e.stage ?? null)) {
      ev.status = outcome;
      ev.evalId = e.eval_id ?? ev.evalId;
      return;
    }
  }
  s.evals.push({
    key: e.event_id,
    evalId: e.eval_id,
    stage: e.stage,
    status: outcome,
    at: e.timestamp,
    repairAttempt: e.repair_attempt,
  });
}

function lastFailedStage(s: RunUiState): StageUiState | null {
  for (let i = s.events.length - 1; i >= 0; i--) {
    const e = s.events[i]!;
    if (e.event_type === "stage_failed") return stage(s, e.stage);
  }
  return null;
}

export type RunAction =
  | { type: "init"; runId: string; stageOrder: StageInfo[] }
  | { type: "event"; event: RuntimeEvent }
  | { type: "events"; events: RuntimeEvent[] }
  | { type: "meta"; status: RunStatus; currentStage: string | null }
  | { type: "connected"; value: boolean };

/** Immutable-ish reducer (drafted via shallow copy; stages copied on write).
 * Accepts null before the first "init" (no run selected yet). */
export function runReducer(state: RunUiState | null, action: RunAction): RunUiState | null {
  switch (action.type) {
    case "init":
      return initRunState(action.runId, action.stageOrder);
    case "event": {
      if (!state) return state;
      const e = action.event;
      // per-stage shallow copies keep the reducer PURE: transitions below mutate
      // freely, and React (StrictMode) may invoke the reducer more than once
      const next: RunUiState = {
        ...state,
        stages: Object.fromEntries(
          Object.entries(state.stages).map(([k, v]) => [k, { ...v }]),
        ),
        evals: state.evals.map((v) => ({ ...v })),
        events: [...state.events, e],
      };
      const t = TRANSITIONS[e.event_type];
      if (t) t(next, e);
      return next;
    }
    case "events": {
      let s: RunUiState | null = state;
      for (const e of action.events) s = runReducer(s, { type: "event", event: e });
      return s;
    }
    case "meta": {
      if (!state) return state;
      // server-reported Run status wins when the stream has caught up (refresh case)
      if (state.terminalEvent) return state;
      return { ...state, status: action.status, currentStage: action.currentStage };
    }
    case "connected":
      if (!state) return state;
      return { ...state, connected: action.value };
    default:
      return state;
  }
}

export function isTerminal(e: RuntimeEvent): boolean {
  return RUN_TERMINAL_EVENT_TYPES.has(e.event_type);
}

/** UI summary for the Eval panel: per stage pass/repair trail, in event order. */
export function evalTrail(state: RunUiState): (EvalUiEntry & { label: string })[] {
  return state.evals.map((ev) => ({
    ...ev,
    label: ev.stage ?? "run",
  }));
}
