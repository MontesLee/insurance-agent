/**
 * RuntimeEvent → user-visible activity (pure, testable).
 *
 * Two exports of ONE mapping system (28.E-3 — no parallel layers):
 *  - activityLabel(e): the single-line wording for the live footer
 *  - consumerActivities(events): the Consumer Activity DTO — a
 *    deterministic allowlist fold over the event SEQUENCE. Every entry
 *    is event-backed (§49): no fabricated progress, started never
 *    implies completed (§12), unknown events/stages/tools fail CLOSED
 *    (hidden, never raw), and duplicates collapse by semantic identity
 *    (upsert-by-key = the dedup strategy, §15). Ordering follows the
 *    real event order (§16).
 *
 * Rule (§11): show the agent's WORK TRAJECTORY, never model internals —
 * no "我在想/我猜测" phrasing, no tools/skills/agents/routers by name.
 *
 * 28.K.29: `foldConsumerActivities` is the single implementation; the two
 * exports below are thin projections of it (the DTO, and the per-activity
 * creating-event index used by the step-output anchoring in stepAnchors.ts).
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

/** Guarded: a KNOWN stage's Chinese name, or null (fail closed). */
export function knownStageZh(stage: string | null): string | null {
  if (!stage) return null;
  return STAGE_ZH[stage] ?? null;
}

// --------------------------------------------------------------------------- #
// Consumer Activity DTO (28.E-3)
// --------------------------------------------------------------------------- #

export type ConsumerActivityStatus = "running" | "completed" | "waiting" | "failed";

export interface ConsumerActivity {
  /** semantic key — React-internal only; never rendered into the DOM */
  key: string;
  label: string;
  status: ConsumerActivityStatus;
}

/** Per-key consumer copy. Keys without copy for a status fail closed. */
const ACTIVITY_COPY: Record<string, Partial<Record<ConsumerActivityStatus, string>>> = {
  understand: { running: "正在理解你的问题", completed: "已理解你的问题" },
  work: { running: "正在为你分析", completed: "已完成分析", failed: "分析未完成" },
  materials: {
    running: "正在核对相关资料",
    completed: "已完成资料核对",
    failed: "资料核对未完成",
  },
  catalog: {
    running: "正在核对产品资料",
    completed: "已完成产品资料核对",
    failed: "产品资料核对未完成",
  },
  // grounding_* live in the RESERVED vocabulary today (not yet emitted);
  // mapped contract-first, fires only when real events arrive (§49).
  // 28.K.13: the REAL per-stage eval events (eval_started/passed/failed)
  // fold onto the same key — event-backed incremental motion during
  // planning runs, reusing this existing copy table (no new layer).
  verify: {
    running: "正在核实相关信息",
    completed: "已完成信息核实",
    failed: "信息核实未完成",
  },
  // 28.K.25: QA-intent turns — after retrieval completes, the ONLY
  // remaining phases are generation + citation (derivable from the real
  // event sequence: no stage/step events exist on this path). The
  // composing activity states that fact in business language; validated
  // content still renders ONLY via the K.22 post-gate delta stream.
  composing: {
    running: "正在整理回答",
    completed: "已整理回答",
  },
  clarify: { waiting: "需要你补充一些信息" },
  report: { completed: "分析报告已生成" },
};

/** Consumer-meaningful tools (allowlist; accepts kebab/snake spellings). */
const TOOL_ACTIVITY: Record<string, string> = {
  knowledge_search: "materials",
  "knowledge-search": "materials",
  check_catalog_product: "catalog",
  "check-catalog-product": "catalog",
};

/** 28.K.29: the creating event index per activity key (fold metadata only). */
export interface ConsumerActivitySpan {
  /** semantic key — React-internal, never rendered */
  key: string;
  /** index of the FIRST event in the input sequence that created this key */
  firstIndex: number;
}

export interface ConsumerActivityFold {
  items: ConsumerActivity[];
  /** same order as `items` — the event index that created each activity */
  spans: ConsumerActivitySpan[];
}

/**
 * Deterministic fold: events (in real order) → consumer activity list.
 * Upsert-by-key = semantic dedup; unknown values are skipped, never shown.
 *
 * 28.K.29: the fold ALSO reports, per activity, the index of the event that
 * created it (`spans`). That is event-order METADATA — it adds no new
 * activity state and the public DTO (`consumerActivities`) is unchanged; it
 * exists so a step's output box can be anchored to the activity row that
 * step actually produced.
 */
export function foldConsumerActivities(events: RuntimeEvent[]): ConsumerActivityFold {
  const order: string[] = [];
  const status = new Map<string, ConsumerActivityStatus>();
  const firstIndex = new Map<string, number>();
  // 28.K.25: intent tracked from the real intent_classified event — the
  // QA-intent derivation below is event-backed, never assumed.
  let intent = "";

  const stageLabels = new Map<string, string>();

  const remember = (key: string, i: number) => {
    if (!firstIndex.has(key)) firstIndex.set(key, i);
  };
  const upsert = (key: string, next: ConsumerActivityStatus, i: number) => {
    const label = ACTIVITY_COPY[key]?.[next];
    if (label === undefined) return; // no safe copy — fail closed (hidden)
    if (!status.has(key)) order.push(key);
    remember(key, i);
    status.set(key, next);
  };
  const upsertStage = (stage: string | null, next: ConsumerActivityStatus, i: number) => {
    const zh = knownStageZh(stage);
    if (zh === null) return; // unknown stage — hidden, never the raw id
    const verb = verbOf(stage);
    const key = "stage:" + stage;
    const label =
      next === "running" ? `正在${verb}` : next === "completed" ? `已${verb}` : `${zh}未完成`;
    if (!status.has(key)) order.push(key);
    stageLabels.set(key, label);
    remember(key, i);
    status.set(key, next);
  };

  let terminal = false;
  for (let i = 0; i < events.length; i++) {
    const e = events[i]!;
    // 28.K.25 (I10): once the REAL terminal event is folded, later
    // stale/replayed execution events cannot reopen progress — the
    // terminal priority (failed > needs_review > waiting > completed)
    // stays authoritative.
    if (terminal) break;
    switch (e.event_type) {
      case "run_started":
        upsert("understand", "running", i);
        break;
      case "intent_classified":
        upsert("understand", "completed", i);
        intent = String(e.data["intent"] ?? "");
        // routing finished = the assistant IS now working on the reply
        // (QA-slice turns emit no agent_step events — this is the only
        // event-backed fact marking generation as underway)
        upsert("work", "running", i);
        break;
      case "agent_step_started":
        upsert("work", "running", i);
        break;
      case "qa_answered":
        upsert("work", "completed", i); // the answer was delivered — real fact
        if (status.has("composing")) upsert("composing", "completed", i);
        break;
      case "agent_decision": {
        const action = e.data["action"];
        if (action === "ask_user") upsert("clarify", "waiting", i);
        else if (action === "finish" && e.data["final"]) upsert("work", "completed", i);
        break;
      }
      case "tool_started":
      case "tool_completed":
      case "tool_failed": {
        const key = TOOL_ACTIVITY[String(e.data["tool"] ?? e.skill ?? "")];
        if (!key) break;
        if (e.event_type === "tool_started") {
          upsert(key, "running", i);
        } else if (e.event_type === "tool_completed") {
          upsert(key, "completed", i);
          // 28.K.25: on a QA-intent turn, retrieval completion means the
          // turn is now in the generation/citation phase (that path has
          // no stage or step events) — real derivation, business copy.
          if (intent === "insurance_qa" || intent === "product_qa"
              || intent === "unknown_insurance_intent") {
            upsert("composing", "running", i);
          }
        } else {
          // 28.K.25 (I6): a tool-level failure inside a STILL-RUNNING turn
          // is internal retry noise — keep the business row stable (the
          // terminal event decides the final outcome wording).
          if (status.get(key) !== "completed") upsert(key, "running", i);
        }
        break;
      }
      case "run_completed":
        // terminal fact closes the work milestone (§17 terminal semantics)
        if (e.status === "completed") upsert("work", "completed", i);
        else if (e.status === "failed" || e.status === "needs_review") upsert("work", "failed", i);
        if (status.has("composing")) upsert("composing", "completed", i);
        terminal = true;
        break;
      case "run_failed":
        upsert("work", "failed", i);
        if (status.has("composing")) upsert("composing", "completed", i);
        terminal = true;
        break;
      case "grounding_started":
        upsert("verify", "running", i);
        break;
      case "grounding_completed":
        upsert("verify", "completed", i);
        break;
      // 28.K.13: quality-eval checkpoints are REAL runtime events emitted
      // between planning stages — they map onto the verify activity so the
      // consumer sees genuine motion; unknown/poisoned payloads already
      // fail closed in upsert (copy-table allowlist).
      case "eval_started":
        upsert("verify", "running", i);
        break;
      case "eval_passed":
        upsert("verify", "completed", i);
        break;
      case "eval_failed":
        upsert("verify", "failed", i);
        break;
      case "stage_started":
        upsertStage(e.stage, "running", i);
        break;
      case "stage_completed":
        upsertStage(e.stage, "completed", i);
        break;
      case "stage_failed":
        upsertStage(e.stage, "failed", i);
        break;
      case "artifact_created":
        if (e.stage === "report-generation") upsert("report", "completed", i);
        break;
      default:
        break; // internal/noise events stay hidden (evals, checkpoints, …)
    }
  }

  return {
    items: order.map((key) => ({
      key,
      label:
        stageLabels.get(key) ??
        ACTIVITY_COPY[key]?.[status.get(key) as ConsumerActivityStatus] ??
        "",
      status: status.get(key) as ConsumerActivityStatus,
    })),
    spans: order.map((key) => ({ key, firstIndex: firstIndex.get(key) ?? 0 })),
  };
}

/**
 * The Consumer Activity DTO — the public projection of the fold above
 * (unchanged shape: key / label / status, in real event order).
 */
export function consumerActivities(events: RuntimeEvent[]): ConsumerActivity[] {
  return foldConsumerActivities(events).items;
}

// --------------------------------------------------------------------------- #
// single-line wording (live footer)
// --------------------------------------------------------------------------- #

export function activityLabel(e: RuntimeEvent): string | null {
  const stage = knownStageZh(e.stage) ?? "";
  switch (e.event_type) {
    case "agent_step_started":
      return "正在理解与决策";
    case "agent_step_error":
      return "处理出现波动，正在重试";
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
      if (e.status === "completed") return "分析完成";
      // map internal statuses to consumer wording — never the raw code
      if (e.status === "waiting") return "需要你补充信息";
      if (e.status === "needs_review") return "需要进一步核实";
      if (e.status === "failed") return "这次没有完成";
      return "已结束";
    case "run_failed":
      return "这次没有完成";
    case "stage_started":
      return stage ? `正在${verbOf(e.stage)}` : null;
    case "stage_completed":
      return stage ? `${stage}完成` : null;
    case "stage_failed":
      return stage ? `${stage}未完成` : null;
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
      return "正在核对相关资料";
    case "tool_completed":
      return "已完成资料核对";
    case "tool_failed":
      return "资料核对未完成";
    case "intent_classified":
    case "qa_answered":
    case "grounding_started":
    case "grounding_completed":
      return null; // covered by the activity DTO list, not the footer line
    default:
      return null; // unknown event — hidden, never the raw name
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
    knowledge_search: "核对相关资料",
    check_catalog_product: "核对产品资料",
  };
  return map[tool] ?? "处理你的请求"; // guarded — never the raw tool name
}

/** 28.K.25: exported for the ○ pending-stage rendering (AgentActivity). */
export function verbOfStage(stage: string): string {
  return verbOf(stage);
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
