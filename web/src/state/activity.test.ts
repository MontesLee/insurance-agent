import { describe, expect, it } from "vitest";
import {
  activityLabel,
  consumerActivities,
  knownStageZh,
  latestActivity,
} from "./activity";
import type { RuntimeEvent } from "../types/runtime";

function ev(type: string, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: "evt_000001", run_id: "r", timestamp: "2026-09-16T07:00:00Z",
    event_type: type as RuntimeEvent["event_type"], stage: "risk-analysis", skill: null,
    status: null, case_id: "c", artifact_id: null, eval_id: null, repair_attempt: null,
    message: null, data: {}, ...extra,
  };
}

describe("RuntimeEvent → activity wording (pure mapping, §12)", () => {
  const cases: [string, string, Partial<RuntimeEvent>][] = [
    ["run_started", "开始分析", {}],
    ["run_completed", "分析完成", { status: "completed" }],
    ["run_failed", "这次没有完成", {}],
    ["stage_started", "正在识别家庭风险", {}],
    ["stage_completed", "风险分析完成", {}],
    ["stage_failed", "风险分析未完成", {}],
    ["eval_started", "正在校验风险分析结果", { stage: "risk-analysis" }],
    ["eval_passed", "风险分析校验通过", {}],
    ["eval_failed", "风险分析校验未通过", {}],
    ["repair_started", "自动修复（第 1 次）", { repair_attempt: 1 }],
    ["repair_completed", "修复完成，重新执行", {}],
    ["repair_exhausted", "修复次数用尽，转人工复核", {}],
    ["artifact_created", "风险分析产物已生成", {}],
    ["tool_started", "正在核对相关资料", {}],
    ["tool_completed", "已完成资料核对", {}],
    ["tool_failed", "资料核对未完成", {}],
  ];
  it.each(cases)("%s → %s", (type, expected, extra) => {
    expect(activityLabel(ev(type, extra))).toBe(expected);
  });

  it("internal terminal statuses map to consumer wording, never raw codes", () => {
    expect(activityLabel(ev("run_completed", { status: "waiting" }))).toBe("需要你补充信息");
    expect(activityLabel(ev("run_completed", { status: "needs_review" }))).toBe("需要进一步核实");
    expect(activityLabel(ev("run_completed", { status: "failed" }))).toBe("这次没有完成");
    expect(activityLabel(ev("run_completed", { status: null }))).toBe("已结束");
  });

  it("checkpoint_created stays silent (durability noise)", () => {
    expect(activityLabel(ev("checkpoint_created", { stage: null }))).toBeNull();
  });

  it("NEVER surfaces chain-of-thought phrasing", () => {
    const all = [
      "run_started", "run_completed", "run_failed", "stage_started", "stage_completed",
      "stage_failed", "eval_started", "eval_passed", "eval_failed", "repair_started",
      "repair_completed", "repair_exhausted", "artifact_created", "checkpoint_created",
      "checkpoint_resumed", "tool_started", "tool_completed", "tool_failed",
    ].map((t) => activityLabel(ev(t, { stage: t.startsWith("checkpoint") ? null : "risk-analysis" })) ?? "");
    for (const label of all) {
      expect(label).not.toMatch(/思考|猜测|我认为|我想|下一步我/);
    }
  });

  it("agent-loop events map to work-trajectory wording (no CoT, no model talk)", () => {
    expect(activityLabel(ev("agent_step_started", { stage: null }))).toBe("正在理解与决策");
    expect(activityLabel(ev("agent_step_error", { stage: null }))).toBe("处理出现波动，正在重试");
    expect(activityLabel(ev("agent_decision", { stage: null, data: { action: "ask_user" } }))).toBe("等待你补充信息");
    expect(
      activityLabel(ev("agent_decision", { stage: null, data: { action: "call_tool", tool: "record_client_profile" } })),
    ).toBe("选择下一步：整理客户信息");
    // unknown tool → generic, never the raw name
    expect(
      activityLabel(ev("agent_decision", { stage: null, data: { action: "call_tool", tool: "KnowledgeService" } })),
    ).toBe("选择下一步：处理你的请求");
  });

  it("unknown events are hidden — never a raw-name fallback (T2/T10)", () => {
    expect(activityLabel(ev("totally_unknown_event_xyz", { stage: null }))).toBeNull();
    expect(latestActivity([ev("totally_unknown_event_xyz", { stage: null })])).toBeNull();
  });

  it("latestActivity picks the last user-relevant line", () => {
    const events = [
      ev("run_started", { stage: null }),
      ev("checkpoint_created", { stage: null }),
      ev("tool_started", { stage: null }),
    ];
    expect(latestActivity(events)).toBe("正在核对相关资料");
    expect(latestActivity([ev("checkpoint_created", { stage: null })])).toBeNull();
  });
});

describe("consumerActivities — the Consumer Activity DTO (28.E-3)", () => {
  it("T1/T8: a QA turn folds to honest event-backed milestones", () => {
    const items = consumerActivities([
      ev("run_started", { stage: null }),
      ev("intent_classified", { stage: null, data: { intent: "insurance_qa" } }),
      ev("agent_step_started", { stage: null }),
      ev("qa_answered", { stage: null, data: { grounding_status: "grounded" } }),
    ]);
    expect(items).toEqual([
      { key: "understand", label: "已理解你的问题", status: "completed" },
      { key: "work", label: "已完成分析", status: "completed" },
    ]);
  });

  it("T7: started NEVER implies completed (mid-run)", () => {
    const items = consumerActivities([
      ev("run_started", { stage: null }),
      ev("intent_classified", { stage: null }),
      ev("tool_started", { stage: null, data: { tool: "knowledge_search" } }),
    ]);
    expect(items).toEqual([
      { key: "understand", label: "已理解你的问题", status: "completed" },
      { key: "work", label: "正在为你分析", status: "running" },
      { key: "materials", label: "正在核对相关资料", status: "running" },
    ]);
  });

  it("QA turn mid-generation: routing done lights the work milestone (event-backed)", () => {
    expect(consumerActivities([
      ev("run_started", { stage: null }),
      ev("intent_classified", { stage: null }),
    ])).toEqual([
      { key: "understand", label: "已理解你的问题", status: "completed" },
      { key: "work", label: "正在为你分析", status: "running" },
    ]);
  });

  it("T8: real started→completed pair yields both phases in order", () => {
    const items = consumerActivities([
      ev("tool_started", { stage: null, data: { tool: "knowledge_search" } }),
      ev("tool_completed", { stage: null, data: { tool: "knowledge_search" } }),
    ]);
    expect(items).toEqual([
      { key: "materials", label: "已完成资料核对", status: "completed" },
    ]);
  });

  it("T9: duplicate started events collapse to ONE activity (semantic dedup)", () => {
    const items = consumerActivities([
      ev("tool_started", { stage: null, data: { tool: "knowledge_search" } }),
      ev("tool_started", { stage: null, data: { tool: "knowledge_search" } }),
      ev("tool_started", { stage: null, data: { tool: "knowledge_search" } }),
    ]);
    expect(items).toHaveLength(1);
    expect(items[0]).toEqual({ key: "materials", label: "正在核对相关资料", status: "running" });
  });

  it("planning stages fold in REAL event order with verb phrasing", () => {
    const items = consumerActivities([
      ev("run_started", { stage: null }),
      ev("intent_classified", { stage: null }),
      ev("stage_started", { stage: "client-intake" }),
      ev("stage_completed", { stage: "client-intake" }),
      ev("stage_started", { stage: "requirement-analysis" }),
      ev("artifact_created", { stage: "report-generation" }),
    ]);
    expect(items.map((a) => [a.key, a.status])).toEqual([
      ["understand", "completed"],
      ["work", "running"], // routing done → generation underway (no terminal yet)
      ["stage:client-intake", "completed"],
      ["stage:requirement-analysis", "running"],
      ["report", "completed"],
    ]);
    expect(items[2]!.label).toBe("已了解家庭基本情况");
    expect(items[4]!.label).toBe("分析报告已生成");
  });

  it("clarification (ask_user) becomes a waiting milestone (Scenario D)", () => {
    const items = consumerActivities([
      ev("run_started", { stage: null }),
      ev("intent_classified", { stage: null }),
      ev("agent_step_started", { stage: null }),
      ev("agent_decision", { stage: null, data: { action: "ask_user" } }),
    ]);
    expect(items.at(-1)).toEqual({ key: "clarify", label: "需要你补充一些信息", status: "waiting" });
  });

  it("T2/T3: unknown events and stages are dropped, never raw", () => {
    const items = consumerActivities([
      ev("totally_unknown_event_xyz", { stage: null }),
      ev("stage_started", { stage: "UNKNOWN_INTERNAL_STAGE_XYZ" }),
      ev("stage_completed", { stage: "UNKNOWN_INTERNAL_STAGE_XYZ" }),
      ev("tool_started", { stage: null, data: { tool: "WeKnoraInternalTool" } }),
      ev("run_started", { stage: null }),
    ]);
    expect(items).toEqual([{ key: "understand", label: "正在理解你的问题", status: "running" }]);
  });

  it("T4/T5/T6: poisoned ids/tools/router fields never appear in labels", () => {
    const items = consumerActivities([
      ev("intent_classified", { stage: null, data: { intent: "insurance_qa", agent: "insurance-qa-agent", decision_source: "rule" } }),
      ev("tool_started", { stage: null, data: { tool: "knowledge_search", agent_id: "product_qa_agent" } }),
    ]);
    const blob = JSON.stringify(items);
    for (const poison of [
      "insurance_qa", "insurance-qa-agent", "product_qa_agent", "insurance-planning-agent",
      "decision_source", "agent_id", "router", "registry", "run_", "case_id", "WeKnora",
    ]) {
      expect(blob.includes(poison), `DTO must not contain ${poison}`).toBe(false);
    }
  });

  it("grounding (reserved vocabulary) maps contract-first, fires only on real events", () => {
    expect(consumerActivities([
      ev("grounding_started", { stage: null }),
      ev("grounding_completed", { stage: null }),
    ])).toEqual([
      { key: "verify", label: "已完成信息核实", status: "completed" },
    ]);
    expect(consumerActivities([ev("grounding_started", { stage: null })])).toEqual([
      { key: "verify", label: "正在核实相关信息", status: "running" },
    ]);
  });

  it("T12: DTO fields are exactly key/label/status — no event passthrough", () => {
    const items = consumerActivities([
      ev("run_started", { stage: null, data: { run_id: "run_leak", provider: "glm", model: "x" } }),
    ]);
    expect(Object.keys(items[0]!).sort()).toEqual(["key", "label", "status"]);
  });

  it("knownStageZh guards the stage allowlist", () => {
    expect(knownStageZh("risk-analysis")).toBe("风险分析");
    expect(knownStageZh("UNKNOWN_INTERNAL_STAGE_XYZ")).toBeNull();
    expect(knownStageZh(null)).toBeNull();
  });
});

describe("28.K.13 — per-stage quality-eval events fold onto verify (real motion)", () => {
  it("eval_started/passed map to the verify activity in real order", () => {
    const items = consumerActivities([
      ev("run_started", { stage: null }),
      ev("intent_classified", { stage: null }),
      ev("stage_started", { stage: "client-intake" }),
      ev("stage_completed", { stage: "client-intake" }),
      ev("eval_started", { stage: "client-intake" }),
      ev("eval_passed", { stage: "client-intake" }),
    ]);
    expect(items.map((i) => i.key)).toEqual([
      "understand", "work", "stage:client-intake", "verify",
    ]);
    expect(items[3]).toEqual({
      key: "verify", label: "已完成信息核实", status: "completed",
    });
  });

  it("mid-eval shows the running copy; eval_failed shows the failed copy", () => {
    const mid = consumerActivities([
      ev("run_started", { stage: null }),
      ev("eval_started", { stage: "solution" }),
    ]);
    expect(mid[1]).toEqual({
      key: "verify", label: "正在核实相关信息", status: "running",
    });
    const failed = consumerActivities([ev("eval_failed", { stage: "solution" })]);
    expect(failed[0]).toEqual({
      key: "verify", label: "信息核实未完成", status: "failed",
    });
  });

  it("T1-style planning trajectory: understand → stage work → verify → report, real order", () => {
    const items = consumerActivities([
      ev("run_started", { stage: null }),
      ev("intent_classified", { stage: null }),
      ev("stage_started", { stage: "client-intake" }),
      ev("stage_completed", { stage: "client-intake" }),
      ev("eval_started", { stage: "client-intake" }),
      ev("eval_passed", { stage: "client-intake" }),
      ev("stage_started", { stage: "solution" }),
      ev("stage_completed", { stage: "solution" }),
      ev("artifact_created", { stage: "report-generation" }),
      ev("run_completed", { stage: null, status: "completed" }),
    ]);
    expect(items.map((i) => i.key)).toEqual([
      "understand", "work", "stage:client-intake", "verify",
      "stage:solution", "report",
    ]);
    expect(items[items.length - 1]!.status).toBe("completed");
  });
});
