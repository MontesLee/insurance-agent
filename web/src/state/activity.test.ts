import { describe, expect, it } from "vitest";
import { activityLabel, latestActivity } from "./activity";
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
    ["run_failed", "运行失败", {}],
    ["stage_started", "正在识别家庭风险", {}],
    ["stage_completed", "识别家庭风险完成", {}],
    ["stage_failed", "识别家庭风险失败", {}],
    ["eval_started", "正在校验风险分析结果", { stage: "risk-analysis" }],
    ["eval_passed", "风险分析校验通过", {}],
    ["eval_failed", "风险分析校验未通过", {}],
    ["repair_started", "自动修复（第 1 次）", { repair_attempt: 1 }],
    ["repair_completed", "修复完成，重新执行", {}],
    ["repair_exhausted", "修复次数用尽，转人工复核", {}],
    ["artifact_created", "风险分析产物已生成", {}],
    ["tool_started", "正在检索保险知识库", {}],
    ["tool_completed", "知识检索完成", {}],
    ["tool_failed", "知识检索失败", {}],
  ];
  it.each(cases)("%s → %s", (type, expected, extra) => {
    expect(activityLabel(ev(type, extra))).toBe(expected);
  });

  it("checkpoint_created stays silent (durability noise)", () => {
    expect(activityLabel(ev("checkpoint_created"))).toBeNull();
  });

  it("NEVER surfaces chain-of-thought phrasing", () => {
    const all = [
      "run_started", "run_completed", "run_failed", "stage_started", "stage_completed",
      "stage_failed", "eval_started", "eval_passed", "eval_failed", "repair_started",
      "repair_completed", "repair_exhausted", "artifact_created", "checkpoint_created",
      "checkpoint_resumed", "tool_started", "tool_completed", "tool_failed",
    ].map((t) => activityLabel(ev(t)) ?? "");
    for (const label of all) {
      expect(label).not.toMatch(/思考|猜测|我认为|我想|下一步我/);
    }
  });

  it("agent-loop events map to work-trajectory wording (no CoT)", () => {
    expect(activityLabel(ev("agent_step_started"))).toBe("正在理解与决策");
    expect(activityLabel(ev("agent_decision", { data: { action: "ask_user" } }))).toBe("等待你补充信息");
    expect(activityLabel(ev("agent_decision", { data: { action: "call_tool", tool: "record_client_profile" } }))).toBe("选择下一步：整理客户信息");
    expect(activityLabel(ev("agent_decision", { data: { action: "stop" } }))).toBe("达到单轮步骤上限");
    expect(activityLabel(ev("agent_step_error"))).toBe("模型调用异常，正在重试");
    // never reasoning-flavored wording
    const labels = [
      activityLabel(ev("agent_step_started")),
      activityLabel(ev("agent_decision", { data: { action: "call_tool", tool: "knowledge_search" } })),
    ];
    for (const l of labels) expect(l).not.toMatch(/思考|猜测|认为/);
  });

  it("latestActivity picks the last user-relevant line", () => {
    const events = [ev("run_started"), ev("checkpoint_created", { event_type: "checkpoint_created" }), ev("tool_started")];
    expect(latestActivity(events)).toBe("正在检索保险知识库");
    expect(latestActivity([ev("checkpoint_created", { event_type: "checkpoint_created" })])).toBeNull();
  });
});
