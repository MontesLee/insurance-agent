/**
 * 28.K.29 — step-output → activity anchoring.
 *
 * The join that decides which activity row a step's output box is rendered
 * under. Pure event-order arithmetic (no content heuristics); these tests pin
 * the cases that matter: produced-a-new-milestone, produced-nothing-new, the
 * implicit QA bucket, and no-activities-at-all.
 */
import { describe, expect, it } from "vitest";
import {
  activityAnchors,
  QA_COMPOSING_BUCKET_KEY,
  stepsAwaitingModel,
} from "./stepAnchors";
import type { EventType, RuntimeEvent } from "../types/runtime";

function ev(type: EventType, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: "e", run_id: "r", timestamp: "t", event_type: type,
    stage: null, skill: null, status: null, case_id: null, artifact_id: null,
    eval_id: null, repair_attempt: null, message: null, data: {}, ...extra,
  };
}
const step = (n: number) => ev("agent_step_started", { data: { step: n } });
const stage = (s: string, done = false) =>
  ev(done ? "stage_completed" : "stage_started", { stage: s });
const tool = (t: string, done = false) =>
  ev(done ? "tool_completed" : "tool_started", { data: { tool: t } });

/** A realistic planning trajectory — mirrors the real SSE order. */
const PLANNING = [
  ev("run_started"),                                                   // 0
  ev("intent_classified", { data: { intent: "insurance_plan" } }),     // 1
  step(1),                                                             // 2
  ev("agent_decision", { data: { action: "call_tool" } }),             // 3
  tool("record_client_profile"),                                       // 4
  stage("client-intake"),                                              // 5
  stage("client-intake", true),                                        // 6
  ev("eval_started", { stage: "client-intake" }),                      // 7
  ev("eval_passed", { stage: "client-intake" }),                       // 8
  step(2),                                                             // 9
  ev("agent_decision", { data: { action: "call_tool" } }),             // 10
  stage("risk-analysis"),                                              // 11
  stage("risk-analysis", true),                                        // 12
  ev("run_completed", { status: "completed" }),                        // 13
];

function anchorOf(events: RuntimeEvent[], key: string) {
  return activityAnchors(events, [key]).get(key);
}

describe("28.K.29 — activityAnchors", () => {
  it("a step owns the milestone it produced (first activity created after it)", () => {
    const a = activityAnchors(PLANNING, ["step-1", "step-2"]);
    expect(a.get("step-1")).toBe("stage:client-intake");
    expect(a.get("step-2")).toBe("stage:risk-analysis");
  });

  it("falls back to the most recent existing activity when nothing new appears", () => {
    // a trailing step (e.g. the closing turn) creates no milestone of its own
    expect(anchorOf([...PLANNING, step(3)], "step-3")).toBe("stage:risk-analysis");
  });

  it("re-running an already-seen stage does not invent a second row", () => {
    const events = [
      ...PLANNING,
      step(3), stage("risk-analysis"), stage("risk-analysis", true),
    ];
    expect(anchorOf(events, "step-3")).toBe("stage:risk-analysis");
  });

  it("qa-composing owns the LAST activity — composing when retrieval ran", () => {
    const qa = [
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      tool("knowledge_search"),
      tool("knowledge_search", true),
      ev("qa_answered", { data: { grounding_status: "grounded" } }),
      ev("run_completed", { status: "completed" }),
    ];
    expect(anchorOf(qa, QA_COMPOSING_BUCKET_KEY)).toBe("composing");
  });

  it("qa-composing falls back to work when no retrieval activity exists", () => {
    const qa = [
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      ev("run_completed", { status: "completed" }),
    ];
    expect(anchorOf(qa, QA_COMPOSING_BUCKET_KEY)).toBe("work");
  });

  it("no activities at all → null (bucket stays unanchored, never dropped)", () => {
    expect(activityAnchors([], ["step-1"])).toEqual(new Map([["step-1", null]]));
    expect(anchorOf([tool("some_unmapped_tool")], "step-1")).toBeNull();
  });

  it("an unresolved bucket resolves FORWARD exactly once, then stays put", () => {
    const t1 = [ev("run_started"), ev("intent_classified"), step(1)];
    // before the stage starts there is nothing new → most recent row
    expect(anchorOf(t1, "step-1")).toBe("work");
    const t2 = [
      ...t1,
      ev("agent_decision", { data: { action: "call_tool" } }),
      stage("client-intake"),
    ];
    expect(anchorOf(t2, "step-1")).toBe("stage:client-intake");
    const t3 = [
      ...t2,
      stage("client-intake", true),
      ev("eval_started", { stage: "client-intake" }),
      ev("eval_passed", { stage: "client-intake" }),
      step(2),
    ];
    expect(anchorOf(t3, "step-1")).toBe("stage:client-intake"); // unchanged
    expect(anchorOf(t3, "step-2")).toBe("verify"); // newest existing row
  });

  it("unknown stages/tools create no activity → no phantom anchor", () => {
    const events = [ev("run_started"), step(1), stage("UNKNOWN_STAGE_XYZ"), tool("weird_tool")];
    // only understand (0) and work (1, created by the step event itself) exist
    expect(activityAnchors(events, ["step-1"]).get("step-1")).toBe("work");
    expect(activityAnchors(events, ["step-1"]).size).toBe(1);
  });

  it("an unknown bucket key is treated as end-of-timeline, never guessed", () => {
    expect(anchorOf(PLANNING, "step-999")).toBe("stage:risk-analysis");
  });

  it("deterministic: same inputs → same map (pure)", () => {
    expect(activityAnchors(PLANNING, ["step-1"])).toEqual(activityAnchors(PLANNING, ["step-1"]));
  });

  it("every bucket key is present in the returned map", () => {
    const a = activityAnchors(PLANNING, ["step-1", "step-2", "qa-composing"]);
    expect([...a.keys()]).toEqual(["step-1", "step-2", "qa-composing"]);
  });
});

/**
 * 28.K.30 — which steps still have a generation in flight.
 *
 * The empty step box's "正在思考…" line (and the empty box itself) is only
 * mounted while the model is still generating. These tests pin the boundary:
 * it is read off real events only, and only events that PROVE the model has
 * returned close it.
 */
describe("stepsAwaitingModel (28.K.30)", () => {
  const stepEv = (n: number) => ev("agent_step_started", { data: { step: n } });
  const toolStart = (n: number, t = "knowledge_search") =>
    ev("tool_started", { data: { step: n, tool: t } });
  const toolDone = (n: number, t = "knowledge_search") =>
    ev("tool_completed", { data: { step: n, tool: t } });
  const decide = (n: number) =>
    ev("agent_decision", { data: { step: n, action: "call_tool" } });

  it("a freshly started step is awaiting the model", () => {
    expect([...stepsAwaitingModel([ev("run_started"), stepEv(2)])]).toEqual(["step-2"]);
  });

  it("the model having picked a tool closes the wait (the tool cannot precede it)", () => {
    const events = [stepEv(2), toolStart(2)];
    expect(stepsAwaitingModel(events).has("step-2")).toBe(false);
  });

  it("an agent_decision closes the wait too", () => {
    expect(stepsAwaitingModel([stepEv(3), decide(3)]).has("step-3")).toBe(false);
  });

  it("a tool that already COMPLETED also closes the wait (replay-safe)", () => {
    expect(stepsAwaitingModel([stepEv(1), toolDone(1)]).has("step-1")).toBe(false);
  });

  it("steps are independent: step 2 awaits while step 1 does not", () => {
    const events = [stepEv(1), toolStart(1), toolDone(1), stepEv(2)];
    const awaiting = stepsAwaitingModel(events);
    expect(awaiting.has("step-1")).toBe(false);
    expect(awaiting.has("step-2")).toBe(true);
  });

  it("only step-scoped events count — stage/QA/terminal events are ignored", () => {
    const events = [
      stepEv(1),
      ev("stage_started", { stage: "client-intake" }),
      ev("eval_passed", { stage: "client-intake" }),
      // the terminal decision carries NO step (it is not a step's decision)
      ev("agent_decision", { data: { action: "finish", final: true } }),
    ];
    expect([...stepsAwaitingModel(events)]).toEqual(["step-1"]);
  });

  it("the QA-slice bucket never appears (it has no step events to observe)", () => {
    const events = [
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      ev("tool_completed", { data: { tool: "knowledge_search" } }),
    ];
    expect(stepsAwaitingModel(events).size).toBe(0);
    expect(stepsAwaitingModel(events).has(QA_COMPOSING_BUCKET_KEY)).toBe(false);
  });

  it("pure: same input → same answer", () => {
    const events = [stepEv(1), toolStart(1), stepEv(2)];
    expect([...stepsAwaitingModel(events)]).toEqual([...stepsAwaitingModel(events)]);
  });
});
