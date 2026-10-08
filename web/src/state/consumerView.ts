/**
 * ConsumerView — the ALLOWLIST presentation boundary (Phase 28.E-2).
 *
 * Everything a consumer component renders from runtime-derived state goes
 * through this module. It is pure and deliberately tiny: explicit fields,
 * explicit literals, explicit lookups. No runtime object is spread, cloned,
 * or passed through (`...runtime` / delete-key / JSON round-trips are all
 * forbidden by design) — an internal field can only reach the consumer DOM
 * by being explicitly written here, and none are.
 *
 * Boundary contract (E-0/E-2):
 *  - Completion ≠ Artifact: an artifact card requires a REAL artifact
 *    (an artifact_created event for the report stage in the same run),
 *    never a terminal status alone.
 *  - Unknown artifact types / stage ids never render raw: unknown types
 *    render NO card, unknown stages render a generic label.
 *  - agent identity is presentation-level ("保险顾问助手"), changeable
 *    here without touching any architecture constant.
 */
import type { RunUiState } from "./runReducer";
import { stageZh } from "./activity";
import type { RuntimeEvent } from "../types/runtime";

/** Presentation-level assistant identity (NOT an architecture constant). */
export const ASSISTANT_NAME = "保险顾问助手";

export const REPORT_STAGE = "report-generation";
export const REPORT_ARTIFACT_TYPE = "insurance-report";

export interface ConsumerArtifactView {
  title: string;
  cta: string;
}

/** Consumer-displayable artifacts — the allowlist. */
const ARTIFACT_VIEWS: Record<string, ConsumerArtifactView> = {
  [REPORT_ARTIFACT_TYPE]: {
    title: "客户保险需求分析报告",
    cta: "查看完整报告",
  },
};

/** Allowlist lookup — unknown types are NOT consumer-displayable. */
export function toArtifactView(
  artifactType: string | null | undefined,
): ConsumerArtifactView | null {
  if (!artifactType) return null;
  return ARTIFACT_VIEWS[artifactType] ?? null;
}

/** Stage label — mapped Chinese only; never the raw stage/skill id.
 *  (stageZh echoes unknown ids back — the boundary overrides that.) */
export function consumerStageLabel(stageId: string): string {
  const zh = stageZh(stageId);
  if (!zh || zh === stageId) return "处理中";
  return zh;
}

/**
 * Does this run REALLY carry a consumer artifact? A completed status alone
 * NEVER qualifies — the run must contain an artifact_created event for the
 * report stage (QA turns produce none → no report card, by design).
 */
export function hasRealArtifact(state: RunUiState): boolean {
  if (state.status !== "completed") return false;
  return state.events.some(
    (e: RuntimeEvent) =>
      e.event_type === "artifact_created" && e.stage === REPORT_STAGE,
  );
}

/** The finalize decision for a terminal run (pure; ChatLayout applies it). */
export function consumerFinalizeArtifact(
  state: RunUiState,
): { artifactType: string; title: string } | null {
  if (!hasRealArtifact(state)) return null;
  const view = toArtifactView(REPORT_ARTIFACT_TYPE);
  if (!view) return null;
  return { artifactType: REPORT_ARTIFACT_TYPE, title: view.title };
}

/** Terminal header wording (consumer; E-5 may refine copy). */
export function consumerTerminalHeader(
  status: RunUiState["status"],
  streaming: boolean,
): string {
  if (streaming || status === "running" || status === "queued") {
    return "正在处理你的请求";
  }
  switch (status) {
    case "completed":
      return "已完成";
    case "needs_review":
      return "需要进一步核实";
    case "waiting":
      return "需要你补充信息";
    case "failed":
      return "这次没有完成";
    default:
      return ASSISTANT_NAME;
  }
}

/**
 * Fallback text when no safe backend message exists. Conservative by
 * design: no invented facts, no reasons, no product content.
 */
export function consumerFallbackText(kind: "refusal" | "error"): string {
  return kind === "refusal"
    ? "目前没有足够可靠的信息支持这个回答，先不直接下结论。"
    : "这次处理没有完成，请稍后再试。";
}

// --------------------------------------------------------------------------- #
// Terminal view (28.E-5) — deterministic consumer presentation of the
// run's terminal fact. Precedence is fixed: a failed run can never show
// success/artifact; a completed run never shows error copy. The backend
// status contract is untouched — this is presentation only.
// --------------------------------------------------------------------------- #

export type ConsumerTerminalState =
  | "answer"
  | "refusal"
  | "clarification"
  | "needs_review"
  | "error";

export interface ConsumerTerminalView {
  state: ConsumerTerminalState;
  /** the user-visible final message (server text when safe, else fallback) */
  message: string;
  /** a REAL consumer artifact exists (completed runs only — E-2 gating) */
  artifact: boolean;
}

const TERMINAL_FALLBACKS: Record<ConsumerTerminalState, string> = {
  answer: "（本轮无回复）",
  refusal: consumerFallbackText("refusal"),
  clarification: "需要你补充一些信息后，我才能继续为你分析。",
  needs_review: "这个结果需要进一步人工核实，确认后我会继续处理。",
  error: consumerFallbackText("error"),
};

export function consumerTerminalView(
  status: "completed" | "needs_review" | "waiting" | "failed",
  resultStatus: string | null | undefined,
  replyText: string | null | undefined,
  hasArtifact: boolean,
): ConsumerTerminalView {
  // deterministic precedence (E5-T6): terminal status dominates; a
  // refused-but-completed turn stays completed (honest refusal copy),
  // and artifacts exist ONLY on completed turns with a real event.
  let state: ConsumerTerminalState;
  switch (status) {
    case "failed":
      state = "error";
      break;
    case "needs_review":
      state = "needs_review";
      break;
    case "waiting":
      state = "clarification";
      break;
    case "completed":
      state = resultStatus === "QA_REFUSED" ? "refusal" : "answer";
      break;
  }
  const artifact = state === "answer" && hasArtifact;
  const fallback = TERMINAL_FALLBACKS[state]!;
  // 28.K.1 (P2-①): a needs_review reply is always a SYSTEM template
  // (never business content), so the terminal view maps it to the fixed
  // consumer copy instead of passing server template text through.
  // Business answers (answer/refusal/clarification) keep the server text.
  const useServerText = state !== "needs_review";
  const message = useServerText && replyText && replyText.trim().length > 0
    ? replyText
    : fallback;
  return { state, message, artifact };
}
