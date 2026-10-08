/**
 * Review Workspace ViewModel (Phase 27.7.7) — the human-readable
 * projection types. Raw API/artifact shapes are translated by
 * components/review/viewModel.ts; React components render ONLY these
 * types (no artifact-payload parsing inside components).
 *
 * Rules baked into the shapes:
 *  - every business string comes verbatim from a real artifact field
 *    (`reason`, `objective`, `summary`, …) — the UI authors nothing;
 *  - everything that can be absent is `| null` and renders 暂无信息;
 *  - enums are kept alongside their Chinese label so the raw value
 *    stays auditable (expandable areas show it).
 */

/** One client-profile field: {value, status} pairs from client-intake. */
export interface VMClientField {
  label: string;
  value: string | null;
  /** raw status vocabulary (KNOWN / UNKNOWN / …), verbatim */
  status: string | null;
}

export interface VMCustomer {
  /** "35岁 · 男 · 已婚 · 1个孩子" — demographic line from client-profile */
  demographicLine: string | null;
  /** case description from the demo case catalog (/api/cases) */
  caseTitle: string | null;
  caseId: string | null;
  /** core need headline: requirement summaries joined */
  needHeadline: string | null;
  fields: VMClientField[];
  /** labels of the fields whose status is KNOWN (🟢 已验证) */
  knownLabels: string[];
  /** fields that are NOT confirmed (🟡 建议确认) */
  unconfirmed: { label: string; status: string | null }[];
}

export interface VMNeed {
  id: string | null;
  typeLabel: string | null;
  summary: string | null;
  priorityLabel: string | null;
  /** natural-language reason from the requirement artifact */
  reason: string | null;
}

/** One 风险 → 当前情况 → 保障缺口 → 建议 row (risk ⋈ gap). */
export interface VMRiskRow {
  riskId: string | null;
  name: string | null;
  severityLabel: string | null;
  severityRaw: string | null;
  /** existing protection + protected amount, human phrasing */
  current: string | null;
  gapId: string | null;
  gapSubject: string | null;
  gapLevelLabel: string | null;
  gapLevelRaw: string | null;
  unprotectedLabel: string | null;
  /** Agent 建议: the gap's target_coverage.direction */
  advice: string | null;
  /** expandable: 为什么得出这个结论 */
  rationale: {
    conclusion: string | null;
    reason: string | null;
    protectedLabel: string | null;
    unprotectedLabel: string | null;
    confidence: number | null;
    likelihood: string | null;
    residual: string | null;
    evidenceRefs: string[];
    gapReason: string | null;
    targetRationale: string | null;
  };
}

export interface VMSolution {
  id: string | null;
  typeLabel: string | null;
  objective: string | null;
  direction: string | null;
  priorityLabel: string | null;
  gapIds: string[];
  reason: string | null;
  tradeoffs: { axis: string | null; chosen: string | null; reason: string | null }[];
  rejected: { direction: string | null; reason: string | null }[];
}

export interface VMProduct {
  candidateId: string;
  name: string | null;
  company: string | null;
  /** gap subjects this product addresses (via related_gap_ids) */
  solves: string[];
  premiumAnnual: number | null;
  termYears: number | null;
  features: string[];
  deductible: string | null;
  /** 为什么推荐 — the evaluation's natural-language reason */
  why: string | null;
  fit: string | null;
  evidenceStatus: string | null;
  provenance: { type: string; ref: string }[];
  /** eligibility checks the pipeline could NOT verify (🟡 建议确认) */
  confirmations: { label: string; detail: string }[];
}

export interface VMRecommendation {
  /** null when the run produced NO primary recommendation (honest state) */
  primary: VMProduct | null;
  /** when primary is null: the real reasons (not_recommended / uncertainties) */
  noPrimaryReasons: string[];
  alternatives: VMProduct[];
  /** candidates blocked by insufficient evidence (evidence-chain drill-down) */
  insufficient: { candidateId: string; provenance: { type: string; ref: string }[] }[];
  humanReviewRequired: boolean;
  recommendationStatus: string | null;
}

export interface VMReviewItem {
  title: string;
  detail: string | null;
  /** where this item comes from (shown small, auditable) */
  source: string;
}

export interface VMHumanReview {
  must: VMReviewItem[];
  suggest: VMReviewItem[];
  /** e.g. "客户基本资料 13 项已由客户录入确认" */
  verifiedNote: string | null;
}

export interface VMDeliverable {
  artifactType: string;
  titleLabel: string;
  statusLabel: string | null;
  createdAt: string | null;
  /** the insurance report renders a full-document drill-down */
  isReport: boolean;
}

export interface VMExecutionStep {
  key: string;
  /** human verb phrase — 已完成需求分析 (label map over stage ids) */
  label: string;
  stage: string;
  status: "completed" | "failed";
  timestamp: string;
}

/** The five executive-summary cards; each answers exactly one question. */
export interface VMExecutiveSummary {
  need: string | null;
  currentCoverage: string | null;
  mainGap: string | null;
  agentAdvice: string | null;
  reviewStatus: { text: string | null; tone: "ok" | "warn" | "alert" };
}

export interface ReviewWorkspaceVM {
  runId: string | null;
  customer: VMCustomer;
  needs: VMNeed[];
  summary: VMExecutiveSummary;
  risks: VMRiskRow[];
  solutions: VMSolution[];
  recommendation: VMRecommendation | null;
  humanReview: VMHumanReview;
  deliverables: VMDeliverable[];
  reportMarkdown: string | null;
  reportTitle: string | null;
  reportGeneratedAt: string | null;
  execution: VMExecutionStep[];
  /** knowledge-evidence entries, resolvable by id in drill-downs */
  evidence: { id: string; content: string | null; source: string | null; section: string | null }[];
}
