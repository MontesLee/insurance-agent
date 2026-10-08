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

export interface StreamUiState {
  text: string;
  kind: "reasoning" | "content";
  /** 28.K.29-A: "answer" = the final-answer stream (message position).
   * Step-boundary events do NOT clear an answer stream — the transcript
   * finalize owns its end (spec §11 no-duplication contract). */
  channel?: "answer";
}

/** 28.K.28: one contiguous run of same-kind stream text inside a step bucket. */
export interface StepSegment {
  kind: "reasoning" | "content";
  text: string;
}

export interface StepOutputBucket {
  key: string;
  segments: StepSegment[];
}

/** Characters retained per bucket (tail-capped; the oldest text drops first). */
export const MAX_BUCKET_CHARS = 4000;

/** Joined display text of a bucket — every segment, in arrival order. */
export function bucketText(b: StepOutputBucket): string {
  return b.segments.map((s) => s.text).join("");
}

/**
 * Append stream text to a bucket, merging into the trailing segment when the
 * kind matches (so an R,C,R,C stream stays 3 segments, not 4), then tail-cap
 * the total at MAX_BUCKET_CHARS by dropping from the FRONT.
 */
export function appendSegment(
  b: StepOutputBucket,
  kind: StepSegment["kind"],
  text: string,
): StepOutputBucket {
  const last = b.segments[b.segments.length - 1];
  let segs: StepSegment[] =
    last && last.kind === kind
      ? [...b.segments.slice(0, -1), { kind, text: last.text + text }]
      : [...b.segments, { kind, text }];

  let total = segs.reduce((n, s) => n + s.text.length, 0);
  while (total > MAX_BUCKET_CHARS && segs.length > 0) {
    const head = segs[0]!;
    const over = total - MAX_BUCKET_CHARS;
    if (head.text.length <= over) {
      segs = segs.slice(1);
      total -= head.text.length;
    } else {
      segs = [{ kind: head.kind, text: head.text.slice(over) }, ...segs.slice(1)];
      total = MAX_BUCKET_CHARS;
    }
  }
  return { key: b.key, segments: segs };
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
  /** live-only LLM output (transient deltas; rebuilt never — not in history) */
  stream: StreamUiState | null;
  /**
   * 28.K.17 (K.16 Option A): epoch-ms timestamp of the LAST
   * agent_stream_delta ARRIVAL — pure UI liveness metadata. The delta's
   * CONTENT is never stored here (reasoning stays only in the stream
   * buffer; content renders exactly as before). Used solely to derive
   * the consumer-safe "generation is actively streaming" state.
   */
  lastDeltaAt: number | null;
  /**
   * Step-scoped streaming outputs (agent-loop transparency). Each
   * agent_step_started opens a bucket; deltas while a bucket is open
   * append to THAT bucket, tagged by kind. Buckets are live-only
   * (transient deltas — rebuilt never, not in history/replay).
   * QA-slice turns (no agent_step events) keep the single global
   * `stream` message bubble — both paths coexist without duplication.
   *
   * 28.K.28 SUPERSEDES E-2: `reasoning` deltas NOW enter the bucket as
   * `kind:"reasoning"` segments (Owner decision — an always-thinking
   * model otherwise leaves the box permanently empty). They stay
   * distinguishable from `kind:"content"` segments so the UI can
   * de-emphasize them, and they STILL never enter the answer bubble
   * (`stream`) — the final assistant answer must not carry CoT.
   * Render-time sanitization applies to reasoning segments too.
   */
  stepOutputs: StepOutputBucket[];
  currentStepKey: string | null;
  /** true once ANY agent_step_started arrived (agent-loop turn) —
      distinguishes QA-slice turns (auto-open composing bucket on first
      content delta) from agent-loop boundary gaps (orphan → bubble only) */
  sawAgentStep: boolean;
  /** the tool the agent is currently executing (null between tools) */
  currentTool: string | null;
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
    stream: null,
    lastDeltaAt: null,
    stepOutputs: [],
    currentStepKey: null,
    sawAgentStep: false,
    currentTool: null,
  };
}

/** agent tool name -> workflow stage it executes (for live highlighting) */
const TOOL_TO_STAGE: Record<string, string> = {
  record_client_profile: "client-intake",
  record_requirement_analysis: "requirement-analysis",
  record_risk_assessment: "risk-analysis",
  coverage_gap_analysis: "coverage-gap-analysis",
  solution: "solution",
  product_candidate_provider: "product-candidate-provider",
  recommendation: "product-recommendation",
  report_generation: "report-generation",
  knowledge_search: "product-candidate-provider",
  check_catalog_product: "product-candidate-provider",
};

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
// Phase 28.B prep: the EventType union now carries the FULL dual-end
// vocabulary (schema/event-vocabulary.json + reserved). The table stays
// PARTIAL by design — unknown/unhandled types are stored in the timeline
// without a transition (see the `event` case); the lookup is already
// undefined-safe.
const TRANSITIONS: Partial<Record<EventType, (s: RunUiState, e: RuntimeEvent) => void>> = {
  run_started: (s, e) => {
    s.status = "running";
    s.currentStage = null;
    void e;
  },
  run_completed: (s, e) => {
    s.currentStepKey = null; // freeze step output buckets at terminal
    s.status = statusFromTerminal(e);
    s.currentStage = null;
    s.currentTool = null;
    s.terminalEvent = e;
    // a run parked for human review keeps the blocked stage visibly flagged
    if (s.status === "needs_review") {
      const st = stage(s, e.stage) ?? lastFailedStage(s);
      if (st && (st.status === "failed" || st.status === "running")) st.status = "needs_review";
    }
  },
  run_failed: (s, e) => {
    s.currentStepKey = null;
    s.status = "failed";
    s.currentStage = null;
    s.currentTool = null;
    s.terminalEvent = e;
  },
  // agent-loop events: timeline-only for pipeline/eval state (§22 — they enrich
  // the stream, they never move stage state; the LLM cannot fake progress)
  agent_step_started: (s, e) => {
    // 28.K.29-A: an ANSWER stream (message position) survives step
    // boundaries — only step-scoped streams reset per step
    if (s.stream?.channel !== "answer") s.stream = null;
    // Step-scoped streaming: open a new output bucket for this step.
    // Buckets accumulate content deltas until the next step/decision —
    // giving each LLM call its own Codex-style output area.
    const key = "step-" + (e.data?.["step"] ?? s.stepOutputs.length + 1);
    s.currentStepKey = key;
    s.sawAgentStep = true;
    if (!s.stepOutputs.some((b) => b.key === key)) {
      s.stepOutputs = [...s.stepOutputs, { key, segments: [] }];
    }
  },
  agent_decision: (s) => {
    // 28.K.29-A: keep the answer stream — the decision that ENDS the
    // turn (finish/ask_user) is exactly what produced it; the transcript
    // finalize replaces it (no duplication, no flicker gap)
    if (s.stream?.channel !== "answer") s.stream = null;
    // close attribution — deltas after a decision belong to the next step
    s.currentStepKey = null;
  },
  agent_step_error: () => {},
  // live streaming text: append to the transient buffer; NEVER into events[]
  agent_stream_delta: (s, e) => {
    // 28.K.29-A: answer-channel deltas (agent_decide finish/ask_user
    // `message` — the FINAL user answer streaming as real provider
    // tool-arg fragments) route to the message-position bubble ONLY,
    // never into a step bucket (spec §11: step box = working process,
    // bubble = final answer — the transcript finalize converges here).
    if (e.data["channel"] === "answer") {
      s.lastDeltaAt = Date.now();
      if (e.data["reset"]) {
        s.stream = null;          // retry attempt: discard partial answer
        return;
      }
      const atext = String(e.data["text"] ?? "");
      if (atext.length === 0) return;
      const aprev = s.stream?.kind === "content" ? s.stream.text : "";
      s.stream = { kind: "content", channel: "answer",
                   text: (aprev + atext).slice(-MAX_BUCKET_CHARS) };
      return;
    }
    // 28.K.17: arrival timestamp drives the consumer live-activity row.
    // 28.K.28 SUPERSEDES 28.K.20/E-2: reasoning deltas NOW enter the step
    // bucket as `kind:"reasoning"` segments (Owner decision — glm-5.3 always
    // thinks, so a content-only buffer stays empty for the whole reasoning
    // phase and the box shows nothing). They remain a SEPARATE segment kind
    // so the UI can de-emphasize them, and they still never reach the answer
    // bubble below. Same-kind neighbours merge, so a mixed R,C,R,C stream is
    // 3 segments, not 4.
    s.lastDeltaAt = Date.now();
    const kind: StepSegment["kind"] =
      e.data["kind"] === "reasoning" ? "reasoning" : "content";
    const text = String(e.data["text"] ?? "");
    if (text.length === 0) return;
    if (s.currentStepKey === null && !s.sawAgentStep) {
      // QA-slice turn (NO agent_step events at all): auto-open an
      // implicit composing bucket on the FIRST delta of ANY kind so the
      // per-step output box appears for QA questions too. Agent-loop
      // boundary gaps (sawAgentStep=true, key briefly null) go to the
      // global bubble only — the next agent_step_started opens a
      // proper named bucket.
      const key = "qa-composing";
      s.currentStepKey = key;
      if (!s.stepOutputs.some((b) => b.key === key)) {
        s.stepOutputs = [...s.stepOutputs, { key, segments: [] }];
      }
    }
    if (s.currentStepKey !== null) {
      const target = s.currentStepKey;
      s.stepOutputs = s.stepOutputs.map((b) =>
        b.key === target ? appendSegment(b, kind, text) : b);
      if (s.sawAgentStep) return; // agent-loop: bucket ONLY (no bubble dup)
    }
    // 28.K.28: the answer bubble stays CONTENT-ONLY — CoT must never pollute
    // the final assistant answer, even now that it is displayable in the box.
    if (kind === "reasoning") return;
    // QA-slice: the global bubble also receives the text (K.20/K.26
    // message-position answer stream — coexists with the step box)
    const prev = s.stream?.text ?? "";
    s.stream = { kind: "content", text: (prev + text).slice(-MAX_BUCKET_CHARS) };
  },
  stage_started: (s, e) => {
    s.stream = null;
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
  tool_started: (s, e) => {
    s.currentTool = e.skill;
    // map the agent tool to its workflow stage so the pipeline line goes
    // RUNNING immediately (dialogue tools emit stage_started late or never)
    const st = stage(s, TOOL_TO_STAGE[e.skill ?? ""] ?? null);
    if (st && st.status === "pending") st.status = "running";
  },
  tool_completed: (s) => { s.currentTool = null; },
  tool_failed: (s) => { s.currentTool = null; },
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
        // transient deltas live in `stream`, never in the durable timeline
        events: e.event_type === "agent_stream_delta" ? state.events : [...state.events, e],
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
