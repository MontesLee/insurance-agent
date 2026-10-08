/**
 * 28.K.25 — Consumer Safe Execution Progress tests.
 *
 * QA path now emits the EXISTING tool_* vocabulary around retrieval
 * (backend) → the fold shows 正在核实相关资料 → 已完成资料核实 →
 * (QA-intent derivation) 正在整理回答 → completed. Planning shows ○
 * upcoming workflow stages once the spine started. Tool-level retry
 * noise stays business-stable.
 */
import { describe, expect, it } from "vitest";
import { consumerActivities } from "./activity";

function ev(type: string, extra: Record<string, unknown> = {}) {
  return {
    event_id: Math.random().toString(36).slice(2), run_id: "r",
    timestamp: "t", event_type: type, stage: null, skill: null,
    status: null, case_id: null, artifact_id: null, eval_id: null,
    repair_attempt: null, message: null, data: {}, ...extra,
  } as never;
}
const tool = (t: string) => ev(t, { data: { tool: "knowledge_search", step: 1 } });

describe("28.K.25 — QA retrieval + composing projection", () => {
  it("U1/I1: QA turn folds retrieval → composing with real events", () => {
    const items = consumerActivities([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      tool("tool_started"),
      tool("tool_completed"),
      ev("qa_answered", { data: { grounding_status: "grounded" } }),
      ev("run_completed", { status: "completed" }),
    ]);
    expect(items.map((i) => `${i.label}:${i.status}`)).toEqual([
      "已理解你的问题:completed",
      "已完成分析:completed",
      "已完成资料核对:completed",
      "已整理回答:completed",
    ]);
  });

  it("U1 mid-run: retrieval done → composing running before answer", () => {
    const items = consumerActivities([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      tool("tool_started"),
      tool("tool_completed"),
    ]);
    const composing = items.find((i) => i.key === "composing");
    expect(composing).toEqual({
      key: "composing", label: "正在整理回答", status: "running",
    });
  });

  it("I2: refusal path — no composing if generation never delivered", () => {
    // insufficient evidence: backend emits tool_started/completed then
    // qa_answered(refused) — composing completed only if it started
    const items = consumerActivities([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      tool("tool_started"),
      tool("tool_completed"),
      ev("qa_answered", { data: { grounding_status: "refused" } }),
      ev("run_completed", { status: "completed" }),
    ]);
    // composing DID start (retrieval completed) → closes at qa_answered
    expect(items.find((i) => i.key === "composing")?.status).toBe("completed");
  });

  it("composing never appears without the retrieval-completed fact", () => {
    const items = consumerActivities([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      ev("qa_answered", { data: { grounding_status: "grounded" } }),
    ]);
    expect(items.find((i) => i.key === "composing")).toBeUndefined();
  });

  it("planning intent does NOT derive composing from tool completion", () => {
    const items = consumerActivities([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_plan" } }),
      tool("tool_started"),
      tool("tool_completed"),
    ]);
    expect(items.find((i) => i.key === "composing")).toBeUndefined();
  });

  it("I6: tool retry noise stays business-stable (no failed flapping)", () => {
    const items = consumerActivities([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "unknown_insurance_intent" } }),
      tool("tool_started"),
      tool("tool_failed"),     // internal retry
      tool("tool_started"),    // retry
      tool("tool_completed"),  // success
    ]);
    const materials = items.find((i) => i.key === "materials");
    expect(materials?.status).toBe("completed");
    expect(items.filter((i) => i.key === "materials")).toHaveLength(1);
  });

  it("U6: duplicate/replayed events collapse (idempotent fold)", () => {
    const base = [
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      tool("tool_completed"),
      tool("tool_completed"), // replay
      ev("run_completed", { status: "completed" }),
    ];
    const items = consumerActivities(base);
    expect(items.filter((i) => i.key === "materials")).toHaveLength(1);
    expect(items.map((i) => i.key)).toEqual(
      ["understand", "work", "materials", "composing"]);
  });

  it("U7/I10: terminal closes; late stale events cannot reopen progress", () => {
    const items = consumerActivities([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      ev("run_failed", { status: "failed" }),
      tool("tool_started"), // stale post-terminal
      ev("agent_step_started"),
    ]);
    expect(items.find((i) => i.key === "work")?.status).toBe("failed");
    // materials appears (started) but composing is NOT derived after
    // terminal — the fold's terminal branch already ran
    expect(items.find((i) => i.key === "composing")).toBeUndefined();
  });

  it("U3/U4/U5: no internal names leak into labels", () => {
    const items = consumerActivities([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      tool("tool_started"),
      ev("agent_stream_delta", { data: { kind: "reasoning", text: "内部R" } }),
      ev("qa_answered"),
      ev("run_completed", { status: "completed" }),
    ]);
    const blob = JSON.stringify(items);
    for (const bad of ["knowledge_search", "tool", "skill", "agent",
                       "run_", "provider", "model", "reasoning", "内部R"]) {
      expect(blob.includes(bad), bad).toBe(false);
    }
  });
});
