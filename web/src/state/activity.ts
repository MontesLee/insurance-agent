/**
 * RuntimeEvent → user-visible activity wording (pure, testable).
 *
 * Rule (§11): show the agent's WORK TRAJECTORY, never model internals —
 * no "我在想/我猜测" phrasing, only observable actions and outcomes.
 */
import type { RuntimeEvent } from "../types/runtime";

/** 中文 stage 名（chat / 用户侧）；Developer Mode 的 Pipeline 沿用英文 labelOf。 */
const STAGE_ZH: Record<string, string> = {
  "client-intake": "客户建档",
  "requirement-analysis": "需求分析",
  "risk-analysis": "风险分析",
  "coverage-gap-analysis": "保障缺口",
  solution: "保障方案",
  "product-candidate-provider": "产品筛选",
  "product-recommendation": "推荐结论",
  "report-generation": "分析报告",
};

export function stageZh(stage: string | null): string {
  if (!stage) return "";
  return STAGE_ZH[stage] ?? stage;
}

export function activityLabel(e: RuntimeEvent): string | null {
  const stage = stageZh(e.stage);
  switch (e.event_type) {
    case "agent_step_started":
      return "正在理解与决策";
    case "agent_step_error":
      return "模型调用异常，正在重试";
    case "agent_stream_delta":
      return null; // transient live text — handled by the stream panel, not the timeline
    case "agent_decision": {
      const action = e.data["action"];
      if (action === "ask_user") return "等待你补充信息";
      if (action === "finish") return e.data["final"] ? "已给出结论" : "准备下一步";
      if (action === "call_tool") return `选择下一步：${zhTool(String(e.data["tool"] ?? e.skill ?? ""))}`;
      if (action === "stop") return "达到单轮步骤上限";
      return "已决策";
    }
    case "run_started":
      return "开始分析";
    case "run_completed":
      return e.status === "completed" ? "分析完成" : `分析结束（${e.status ?? "?"}）`;
    case "run_failed":
      return "运行失败";
    case "stage_started":
      return `正在${verbOf(e.stage)}`;
    case "stage_completed":
      return `${verbOf(e.stage)}完成`;
    case "stage_failed":
      return `${verbOf(e.stage)}失败`;
    case "eval_started":
      return stage ? `正在校验${stage}结果` : "正在校验结果";
    case "eval_passed":
      return stage ? `${stage}校验通过` : "校验通过";
    case "eval_failed":
      return stage ? `${stage}校验未通过` : "校验未通过";
    case "repair_started":
      return `自动修复（第 ${e.repair_attempt ?? 1} 次）`;
    case "repair_completed":
      return `修复完成，重新执行`;
    case "repair_exhausted":
      return "修复次数用尽，转人工复核";
    case "artifact_created":
      return stage ? `${stage}产物已生成` : "产物已生成";
    case "checkpoint_created":
      return null; // durability detail — noise in the user timeline
    case "checkpoint_resumed":
      return "从检查点恢复";
    case "tool_started":
      return "正在检索保险知识库";
    case "tool_completed":
      return "知识检索完成";
    case "tool_failed":
      return "知识检索失败";
    default:
      return null;
  }
}

export function zhTool(tool: string): string {
  const map: Record<string, string> = {
    record_client_profile: "整理客户信息",
    record_requirement_analysis: "整理保障需求",
    record_risk_assessment: "整理风险情况",
    coverage_gap_analysis: "保障缺口分析",
    solution: "保障方案设计",
    product_candidate_provider: "候选产品筛选",
    recommendation: "推荐结论",
    report_generation: "分析报告生成",
    knowledge_search: "知识检索",
    check_catalog_product: "产品目录核验",
  };
  return map[tool] ?? tool;
}

function verbOf(stage: string | null): string {
  switch (stage) {
    case "client-intake":
      return "了解家庭基本情况";
    case "requirement-analysis":
      return "分析保障需求";
    case "risk-analysis":
      return "识别家庭风险";
    case "coverage-gap-analysis":
      return "分析保障缺口";
    case "solution":
      return "设计保障方案";
    case "product-candidate-provider":
      return "筛选候选产品";
    case "product-recommendation":
      return "形成推荐结论";
    case "report-generation":
      return "生成分析报告";
    default:
      return "处理";
  }
}

/** The user-facing latest-activity line for an event stream (last non-null). */
export function latestActivity(events: RuntimeEvent[]): string | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const label = activityLabel(events[i]!);
    if (label) return label;
  }
  return null;
}
