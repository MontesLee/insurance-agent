import { describe, expect, it } from "vitest";
import { initRunState, runReducer, type RunAction } from "./runReducer";
import type { RuntimeEvent } from "../types/runtime";

const ORDER = [
  { id: "client-intake", skill: "client-intake", produces: "client-profile" },
  { id: "risk-analysis", skill: "risk-analysis", produces: "risk-assessment" },
  { id: "solution", skill: "solution", produces: "solution-plan" },
  { id: "report-generation", skill: "report-generation", produces: "insurance-report" },
];

function ev(partial: Partial<RuntimeEvent> & Pick<RuntimeEvent, "event_type">): RuntimeEvent {
  return {
    event_id: "evt_000000",
    run_id: "run_x",
    timestamp: "2026-09-16T07:00:00Z",
    stage: null,
    skill: null,
    status: null,
    case_id: "case-1",
    artifact_id: null,
    eval_id: null,
    repair_attempt: null,
    message: null,
    data: {},
    ...partial,
  };
}

function apply(events: RuntimeEvent[]) {
  let s = initRunState("run_x", ORDER);
  const action: RunAction = { type: "events", events };
  return runReducer(s, action)!;
}

describe("event -> stage state mapping (the explicit transition table)", () => {
  it("pending until stage_started, running while live, passed on stage_completed", () => {
    const s = apply([
      ev({ event_type: "run_started" }),
      ev({ event_type: "stage_started", stage: "risk-analysis" }),
    ]);
    expect(s.status).toBe("running");
    expect(s.stages["client-intake"]!.status).toBe("pending");
    expect(s.stages["risk-analysis"]!.status).toBe("running");
    expect(s.currentStage).toBe("risk-analysis");
    expect(s.stages["risk-analysis"]!.attempts).toBe(1);
  });

  it("stage_completed sets passed + duration + artifact linkage", () => {
    const s = apply([
      ev({ event_type: "stage_started", stage: "risk-analysis" }),
      ev({ event_type: "artifact_created", stage: "risk-analysis", artifact_id: "ART-003" }),
      ev({ event_type: "stage_completed", stage: "risk-analysis", status: "PASS",
           artifact_id: "ART-003", data: { duration_ms: 12.5 } }),
    ]);
    expect(s.stages["risk-analysis"]!.status).toBe("passed");
    expect(s.stages["risk-analysis"]!.artifactId).toBe("ART-003");
    expect(s.stages["risk-analysis"]!.durationMs).toBe(12.5);
  });

  it("repair flow: attempt counter, then needs_review on repair_exhausted", () => {
    const s = apply([
      ev({ event_type: "stage_started", stage: "solution" }),
      ev({ event_type: "stage_failed", stage: "solution", status: "FAIL" }),
      ev({ event_type: "repair_started", stage: "solution", repair_attempt: 1 }),
      ev({ event_type: "stage_started", stage: "solution", repair_attempt: 1 }),
      ev({ event_type: "repair_exhausted", stage: "solution", repair_attempt: 2 }),
    ]);
    expect(s.stages["solution"]!.status).toBe("needs_review");
    expect(s.stages["solution"]!.repairAttempt).toBe(1);
    expect(s.stages["solution"]!.attempts).toBe(2);
  });

  it("events for unknown stages are recorded in the timeline but never crash", () => {
    const s = apply([ev({ event_type: "stage_started", stage: "not-a-stage" })]);
    expect(s.events).toHaveLength(1);
    expect(Object.keys(s.stages)).not.toContain("not-a-stage");
  });

  it("timeline-only events (checkpoint/tool) do not move stage state", () => {
    const s = apply([
      ev({ event_type: "checkpoint_created", data: { checkpoint_id: "CP-001" } }),
      ev({ event_type: "tool_started", stage: "solution", data: { tool: "knowledge-search" } }),
      ev({ event_type: "tool_completed", stage: "solution" }),
    ]);
    expect(s.stages["solution"]!.status).toBe("pending");
    expect(s.events).toHaveLength(3);
  });
});

describe("event -> eval state mapping", () => {
  it("eval_started -> evaluating, eval_passed closes it as PASS", () => {
    const s = apply([
      ev({ event_type: "eval_started", stage: "risk-analysis" }),
      ev({ event_type: "eval_passed", stage: "risk-analysis", eval_id: "EVAL-003" }),
    ]);
    expect(s.evals).toHaveLength(1);
    expect(s.evals[0]!.status).toBe("pass");
    expect(s.evals[0]!.evalId).toBe("EVAL-003");
    expect(s.stages["risk-analysis"]!.lastEvalStatus).toBe("pass");
  });

  it("fail -> repair -> re-eval pairs correctly by stage", () => {
    const s = apply([
      ev({ event_type: "eval_started", stage: "solution" }),
      ev({ event_type: "eval_failed", stage: "solution", eval_id: "EVAL-005" }),
      ev({ event_type: "repair_started", stage: "solution", repair_attempt: 1 }),
      ev({ event_type: "eval_started", stage: "solution", repair_attempt: 1 }),
      ev({ event_type: "eval_passed", stage: "solution", eval_id: "EVAL-006" }),
    ]);
    const closed = s.evals.filter((e) => e.status !== "running");
    expect(closed.map((e) => e.status)).toEqual(["fail", "pass"]);
    expect(s.evals[1]!.repairAttempt).toBe(1);
  });
});

describe("run terminal handling", () => {
  it("run_completed carries the authoritative final status", () => {
    const s = apply([
      ev({ event_type: "run_started" }),
      ev({ event_type: "run_completed", status: "completed" }),
    ]);
    expect(s.status).toBe("completed");
    expect(s.terminalEvent?.event_type).toBe("run_completed");
  });

  it("needs_review terminal flags the stopped stage", () => {
    const s = apply([
      ev({ event_type: "stage_started", stage: "solution" }),
      ev({ event_type: "stage_failed", stage: "solution", status: "FAIL" }),
      ev({ event_type: "repair_exhausted", stage: "solution" }),
      ev({ event_type: "run_completed", status: "needs_review", stage: "solution" }),
    ]);
    expect(s.status).toBe("needs_review");
    expect(s.stages["solution"]!.status).toBe("needs_review");
  });

  it("server meta never overrides a terminal event the stream already delivered", () => {
    let s = apply([ev({ event_type: "run_completed", status: "completed" })]);
    s = runReducer(s, { type: "meta", status: "running", currentStage: null })!;
    expect(s.status).toBe("completed");
  });
});

describe("replay equals live (refresh safety)", () => {
  it("applying the same events in one batch or one-by-one yields identical state", () => {
    const events = [
      ev({ event_type: "run_started" }),
      ev({ event_type: "stage_started", stage: "client-intake" }),
      ev({ event_type: "artifact_created", stage: "client-intake", artifact_id: "ART-001" }),
      ev({ event_type: "eval_passed", stage: "client-intake", eval_id: "EVAL-001" }),
      ev({ event_type: "stage_completed", stage: "client-intake", status: "PASS" }),
      ev({ event_type: "run_completed", status: "completed" }),
    ];
    const batched = apply(events);
    let one = initRunState("run_x", ORDER);
    for (const e of events) one = runReducer(one, { type: "event", event: e })!;
    expect(one).toEqual(batched);
  });
});
