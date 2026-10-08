/**
 * Review Workspace ViewModel adapter (Phase 27.7.7 Step 2).
 *
 * Raw API data → human-readable view model. Pure functions, no React,
 * no HTTP: the workspace fetches everything, hands the raw bundle to
 * `buildReviewWorkspaceVM`, and renders ONLY the result.
 *
 * Honesty rules (mirrors the backend's own):
 *  - every business sentence is copied verbatim from a real field
 *    (reason / objective / summary / direction …). The adapter NEVER
 *    composes conclusions of its own.
 *  - labels (严重/高/医疗/…) are pure display dictionaries over verbatim
 *    enums; the raw value always survives somewhere auditable.
 *  - absent data → null → the component renders 暂无信息. Never guessed.
 */
import type { ApprovalRecord, SupervisorState } from "../../types/approval";
import type { RuntimeEvent } from "../../types/runtime";
import type { ReviewCard } from "../../types/reviewCard";
import type {
  ReviewWorkspaceVM,
  VMClientField,
  VMCustomer,
  VMDeliverable,
  VMExecutiveSummary,
  VMExecutionStep,
  VMHumanReview,
  VMNeed,
  VMProduct,
  VMRecommendation,
  VMReviewItem,
  VMRiskRow,
  VMSolution,
} from "../../types/reviewWorkspace";

// ---- unknown-safe navigation ------------------------------------------- #

const rec = (v: unknown): Record<string, unknown> | null =>
  v !== null && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
const str = (v: unknown): string | null =>
  typeof v === "string" && v.length > 0 ? v : null;
const num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
/** pick the first non-null string produced by `pick` over an array */
const firstStr = (list: unknown[], pick: (r: Record<string, unknown>) => unknown): string | null => {
  for (const item of list) {
    const r = rec(item);
    if (!r) continue;
    const s = str(pick(r));
    if (s !== null) return s;
  }
  return null;
};

/** Amount → human unit: 500000 → "50万"; 12345 → "12,345". */
export function fmtAmount(n: number): string {
  if (n === 0) return "0";
  if (Math.abs(n) >= 10000 && n % 10000 === 0) return `${n / 10000}万`;
  return n.toLocaleString("zh-CN");
}

// ---- display dictionaries (labels ONLY — never new facts) -------------- #

const SEVERITY_LABEL: Record<string, string> = {
  CRITICAL: "严重", HIGH: "高", MEDIUM: "中", LOW: "低",
};
export function severityLabel(raw: string | null): string | null {
  if (raw === null) return null;
  return SEVERITY_LABEL[raw.toUpperCase()] ?? raw;
}

export function priorityLabel(raw: string | null): string | null {
  if (raw === null) return null;
  const up = raw.toUpperCase();
  if (up.startsWith("P0")) return "P0 · 最优先";
  if (up.startsWith("P1")) return "P1 · 高";
  if (up.startsWith("P2")) return "P2 · 中";
  if (up.startsWith("P3")) return "P3 · 低";
  return raw;
}

const TYPE_LABEL: Record<string, string> = {
  medical: "医疗", critical_illness: "重疾", serious_illness: "重疾",
  accident: "意外", savings: "储蓄/养老", life: "寿险",
  death: "寿险（身故）", education: "教育金", income: "收入保障",
};
export function typeLabel(raw: string | null): string | null {
  if (raw === null) return null;
  return TYPE_LABEL[raw.toLowerCase()] ?? raw;
}

const STAGE_LABEL: Record<string, string> = {
  "client-intake": "客户信息整理",
  "requirement-analysis": "需求分析",
  "risk-analysis": "家庭风险分析",
  "coverage-gap-analysis": "保障缺口识别",
  "solution": "解决方案设计",
  "product-candidate-provider": "产品检索与匹配",
  "product-recommendation": "产品推荐判定",
  "report-generation": "方案报告生成",
};
export function stageLabel(stage: string): string {
  return STAGE_LABEL[stage] ?? stage;
}

export const ARTIFACT_TITLE: Record<string, string> = {
  "client-profile": "客户资料",
  "requirement-analysis": "需求分析",
  "risk-assessment": "风险评估",
  "coverage-gap-analysis": "保障缺口分析",
  "solution-plan": "解决方案",
  "product-candidates": "产品候选池",
  "product-recommendation": "产品推荐",
  "knowledge-evidence": "知识证据",
  "insurance-report": "保险需求分析报告",
};

const ARTIFACT_ORDER = [
  "insurance-report", "product-recommendation", "coverage-gap-analysis",
  "risk-assessment", "solution-plan", "requirement-analysis",
  "product-candidates", "knowledge-evidence", "client-profile",
];

export const LEVEL_TEXT: Record<string, string> = {
  AUTO_PASS: "自动校验通过",
  SUMMARY_REVIEW: "需要摘要审核",
  DEEP_REVIEW: "需要深度审核",
};

// ---- raw bundle shape --------------------------------------------------- #

export interface RawBundle {
  approval: ApprovalRecord | null;
  supervisor: SupervisorState | null;
  /** case desc from /api/cases keyed by case_id (null when not found) */
  caseDesc: string | null;
  /** GET /api/runs/{id} — live Run or restored summary (duck-typed) */
  run: unknown;
  events: RuntimeEvent[] | null;
  artifacts: { artifact_type: string; status: string | null; created_at: string | null }[] | null;
  /** artifactType → raw detail JSON (only the successfully fetched ones) */
  details: Record<string, unknown>;
  reviewCard: ReviewCard | null;
}

/** Knowledge-evidence entry, resolved by id for drill-downs. */
export interface VMEvidence {
  id: string;
  content: string | null;
  source: string | null;
  section: string | null;
}

function buildEvidence(b: RawBundle): VMEvidence[] {
  const kev = payloadOf(b, "knowledge-evidence");
  return arr(kev ? kev.evidence : null).flatMap((item) => {
    const e = rec(item);
    const id = e ? str(e.evidence_id) ?? str(e.chunk_id) : null;
    if (!e || !id) return [];
    return [{
      id,
      content: str(e.content),
      source: str(e.source),
      section: str(e.section),
    }];
  });
}

/**
 * An artifact detail's payload. Most artifacts wrap it in
 * `.artifact.payload`; product-candidates carries its fields directly on
 * `.artifact` (legacy catalog shape) — both are handled, no data is
 * invented for either.
 */
function payloadOf(b: RawBundle, type: string): Record<string, unknown> | null {
  const detail = rec(b.details[type]);
  const artifact = detail ? rec(detail.artifact) : null;
  if (!artifact) return null;
  const payload = rec(artifact.payload);
  if (payload && Object.keys(payload).length > 0) return payload;
  return Object.keys(artifact).length > 0 ? artifact : null;
}

// ---- customer (client-profile) ------------------------------------------ //

const CLIENT_SECTIONS: [string, [string, string][]][] = [
  ["家庭", [["age", "年龄"], ["gender", "性别"], ["marital_status", "婚姻状况"],
    ["children", "子女"], ["housing", "住房状况"]]],
  ["职业", [["occupation", "职业"]]],
  ["家庭责任", [["economic_responsibility", "经济责任"]]],
  ["已有保障", [["social_security", "社保"], ["existing_insurance", "已购商业保险"]]],
  ["财务", [["annual_income", "年收入"], ["annual_expense", "年支出"],
    ["mortgage", "房贷余额"], ["insurance_budget", "保险预算"]]],
];

function buildCustomer(b: RawBundle): VMCustomer {
  const cp = payloadOf(b, "client-profile");
  const fp = cp ? rec(cp.family_profile) : null;
  const sectionRec = (name: string): Record<string, unknown> =>
    cp ? rec(cp[name]) ?? {} : {};
  const fieldValue = (section: Record<string, unknown>, key: string): VMClientField => {
    const fr = rec(section[key]);
    return { label: "", value: fr ? str(fr.value) : null, status: fr ? str(fr.status) : null };
  };
  const fields: VMClientField[] = [];
  const known: string[] = [];
  const unconfirmed: { label: string; status: string | null }[] = [];
  for (const [secName, defs] of CLIENT_SECTIONS) {
    const section = sectionRec(secName === "家庭" ? "family_profile"
      : secName === "职业" ? "employment_profile"
      : secName === "家庭责任" ? "responsibility_profile"
      : secName === "已有保障" ? "existing_protection"
      : "financial_profile");
    for (const [key, label] of defs) {
      const f = fieldValue(section, key);
      f.label = label;
      fields.push(f);
      if (f.value !== null && f.status === "KNOWN") known.push(label);
      else if (f.status !== null || f.value !== null)
        unconfirmed.push({ label, status: f.status });
    }
  }
  // missing_from_upstream: upstream never provided these at all
  for (const m of arr(cp ? cp.missing_from_upstream : null)) {
    const s = str(m);
    if (s) unconfirmed.push({ label: s, status: "MISSING" });
  }

  const demoParts: string[] = [];
  const age = fp ? str(rec(fp.age)?.value) : null;
  const gender = fp ? str(rec(fp.gender)?.value) : null;
  const marital = fp ? str(rec(fp.marital_status)?.value) : null;
  const children = fp ? str(rec(fp.children)?.value) : null;
  if (age) demoParts.push(`${age}岁`);
  if (gender) demoParts.push(gender);
  if (marital) demoParts.push(marital);
  if (children) demoParts.push(`子女${children}`);

  const run = rec(b.run);
  const needs = buildNeeds(b);
  return {
    demographicLine: demoParts.length > 0 ? demoParts.join(" · ") : null,
    caseTitle: b.caseDesc,
    caseId: run ? str(run.case_id) : null,
    needHeadline:
      needs.map((n) => n.summary).filter((s): s is string => s !== null).join("；") ||
      null,
    fields,
    knownLabels: known,
    unconfirmed,
  };
}

function buildNeeds(b: RawBundle): VMNeed[] {
  const ra = payloadOf(b, "requirement-analysis");
  return arr(ra ? ra.requirements : null).flatMap((item) => {
    const r = rec(item);
    if (!r) return [];
    return [{
      id: str(r.requirement_id),
      typeLabel: typeLabel(str(r.requirement_type)),
      summary: str(r.summary),
      priorityLabel: priorityLabel(str(r.priority)),
      reason: str(r.reason),
    }];
  });
}

// ---- risks ⋈ gaps -------------------------------------------------------- //

interface GapRecord {
  gapId: string | null;
  subject: string | null;
  gapLevelRaw: string | null;
  domain: string | null;
  direction: string | null;
  targetRationale: string | null;
  gapReason: string | null;
  currentStatus: string | null;
  relatedRiskIds: string[];
  priorityRaw: string | null;
}

function buildGaps(b: RawBundle): { list: GapRecord[]; byId: Map<string, GapRecord> } {
  const cg = payloadOf(b, "coverage-gap-analysis");
  const list: GapRecord[] = arr(cg ? cg.gaps : null).flatMap((item) => {
    const g = rec(item);
    if (!g) return [];
    const cur = rec(g.current_coverage);
    const tgt = rec(g.target_coverage);
    return [{
      gapId: str(g.gap_id),
      subject: str(g.subject),
      gapLevelRaw: str(g.gap_level),
      domain: typeLabel(str(g.domain)),
      direction: tgt ? str(tgt.direction) : null,
      targetRationale: tgt ? str(tgt.rationale) : null,
      gapReason: str(g.reason),
      currentStatus: cur ? str(cur.status) : null,
      relatedRiskIds: arr(g.related_risk_ids).flatMap((x) => str(x) ?? []),
      priorityRaw: null,
    }];
  });
  // priorities list carries the ordering signal (P1 …)
  for (const p of arr(cg ? cg.priorities : null)) {
    const pr = rec(p);
    if (!pr) continue;
    const gid = str(pr.gap_id);
    const g = list.find((x) => x.gapId === gid);
    if (g) g.priorityRaw = str(pr.priority);
  }
  const byId = new Map<string, GapRecord>();
  for (const g of list) if (g.gapId) byId.set(g.gapId, g);
  return { list, byId };
}

function buildRisks(b: RawBundle, gaps: GapRecord[]): VMRiskRow[] {
  const ra = payloadOf(b, "risk-assessment");
  const rows: VMRiskRow[] = [];
  const usedGapIds = new Set<string>();
  for (const item of arr(ra ? ra.risks : null)) {
    const r = rec(item);
    if (!r) continue;
    const riskId = str(r.risk_id);
    const ca = rec(r.coverage_assessment);
    const protectedAmt = ca ? num(ca.protected_amount) : null;
    const unprotectedAmt = ca ? num(ca.unprotected_amount) : null;
    const gap =
      gaps.find((g) => riskId !== null && g.relatedRiskIds.includes(riskId)) ?? null;
    if (gap?.gapId) usedGapIds.add(gap.gapId);
    const existing = str(r.existing_protection);
    const current = existing !== null
      ? protectedAmt !== null && protectedAmt > 0
        ? `${existing}（已保障 ${fmtAmount(protectedAmt)}）`
        : existing
      : null;
    rows.push({
      riskId,
      name: str(r.risk_name),
      severityLabel: severityLabel(str(r.severity)),
      severityRaw: str(r.severity),
      current,
      gapId: gap?.gapId ?? null,
      gapSubject: gap?.subject ?? null,
      gapLevelLabel: severityLabel(gap?.gapLevelRaw ?? null),
      gapLevelRaw: gap?.gapLevelRaw ?? null,
      unprotectedLabel: unprotectedAmt !== null && unprotectedAmt > 0
        ? `${fmtAmount(unprotectedAmt)}未受保障` : null,
      advice: gap?.direction ?? null,
      rationale: {
        conclusion: str(r.conclusion),
        reason: str(r.reason),
        protectedLabel: protectedAmt !== null ? fmtAmount(protectedAmt) : null,
        unprotectedLabel: unprotectedAmt !== null ? fmtAmount(unprotectedAmt) : null,
        confidence: ca ? num(ca.confidence) : num(r.confidence),
        likelihood: str(r.likelihood),
        residual: str(r.residual_risk),
        evidenceRefs: arr(r.reasoning_evidence_refs).flatMap((x) => str(x) ?? []),
        gapReason: gap?.gapReason ?? null,
        targetRationale: gap?.targetRationale ?? null,
      },
    });
  }
  // gaps with no matching risk row still deserve a row (subject as name)
  for (const g of gaps) {
    if (!g.gapId || usedGapIds.has(g.gapId)) continue;
    rows.push({
      riskId: null, name: g.subject, severityLabel: null, severityRaw: null,
      current: g.currentStatus !== null ? `当前覆盖状态：${g.currentStatus}` : null,
      gapId: g.gapId, gapSubject: g.subject,
      gapLevelLabel: severityLabel(g.gapLevelRaw), gapLevelRaw: g.gapLevelRaw,
      unprotectedLabel: null, advice: g.direction,
      rationale: {
        conclusion: null, reason: null, protectedLabel: null, unprotectedLabel: null,
        confidence: null, likelihood: null, residual: null, evidenceRefs: [],
        gapReason: g.gapReason, targetRationale: g.targetRationale,
      },
    });
  }
  return rows;
}

// ---- solutions ----------------------------------------------------------- //

function buildSolutions(b: RawBundle): VMSolution[] {
  const sp = payloadOf(b, "solution-plan");
  return arr(sp ? sp.solutions : null).flatMap((item) => {
    const s = rec(item);
    if (!s) return [];
    return [{
      id: str(s.solution_id),
      typeLabel: typeLabel(str(s.solution_type)),
      objective: str(s.objective),
      direction: str(s.coverage_direction),
      priorityLabel: priorityLabel(str(s.priority)),
      gapIds: arr(s.related_gap_ids).flatMap((x) => str(x) ?? []),
      reason: str(s.reason),
      tradeoffs: arr(s.trade_offs).flatMap((t) => {
        const r = rec(t);
        return r ? [{
          axis: str(r.axis), chosen: str(r.chosen), reason: str(r.reason),
        }] : [];
      }),
      rejected: arr(s.rejected_directions).flatMap((t) => {
        const r = rec(t);
        return r ? [{ direction: str(r.direction), reason: str(r.reason) }] : [];
      }),
    }];
  });
}

// ---- recommendation (⋈ product-candidates) ------------------------------- //

function buildRecommendation(
  b: RawBundle,
  gapsById: Map<string, GapRecord>,
): VMRecommendation | null {
  const recArt = payloadOf(b, "product-recommendation");
  if (!recArt) return null;
  const candArt = payloadOf(b, "product-candidates");
  const candById = new Map<string, Record<string, unknown>>();
  for (const c of arr(candArt ? candArt.candidates : null)) {
    const r = rec(c);
    const id = r ? str(r.candidate_id) : null;
    if (r && id) candById.set(id, r);
  }
  const evals: Record<string, unknown>[] = arr(recArt.candidate_evaluations)
    .flatMap((e): Record<string, unknown>[] => {
      const r = rec(e);
      return r ? [r] : [];
    });
  const evalOf = (cid: string): Record<string, unknown> | null =>
    evals.find((e) => str(e.candidate_id) === cid) ?? null;

  const toProduct = (cid: string, why: string | null): VMProduct => {
    const c = candById.get(cid) ?? null;
    const ev = evalOf(cid);
    const fit = rec(ev ? ev.requirement_fit : null);
    const evidence = rec(ev ? ev.evidence : null);
    const elig = rec(c ? c.eligibility : null);
    const constraints: Record<string, unknown>[] = arr(c ? c.constraints : null)
      .flatMap((x): Record<string, unknown>[] => {
        const r = rec(x);
        return r ? [r] : [];
      });
    // only a real deductible constraint may carry the 免赔额 label —
    // other constraints (e.g. guaranteed_renewal) must not be mislabeled
    const deductible = firstStr(
      constraints.filter((r) => str(r.constraint)?.toLowerCase() === "deductible"),
      (r) => r.value,
    );
    const solves = arr(c ? c.related_gap_ids : null).flatMap((gid) => {
      const s = str(gid);
      return s ? [gapsById.get(s)?.subject ?? s] : [];
    });
    const premium = rec(c ? c.premium : null);
    const term = rec(c ? c.term : null);
    const confirmations = arr(elig ? elig.checks : null).flatMap((chk) => {
      const r = rec(chk);
      const rule = r ? str(r.rule) : null;
      const status = r ? str(r.status) : null;
      return rule && status && status !== "PASS"
        ? [{ label: `核保项「${rule}」未校验`, detail: str(r?.detail) ?? status }]
        : [];
    });
    return {
      candidateId: cid,
      name: c ? str(c.product_name) : null,
      company: c ? str(c.company) : null,
      solves,
      premiumAnnual: premium ? num(premium.annual) : null,
      termYears: term ? num(term.years) : null,
      features: arr(c ? c.features : null).flatMap((f) => str(f) ?? []),
      deductible,
      why,
      fit: fit ? str(fit.overall) : null,
      evidenceStatus: evidence ? str(evidence.status) : null,
      provenance: arr(ev ? ev.provenance : null).flatMap((p) => {
        const r = rec(p);
        const t = r ? str(r.type) : null;
        const ref = r ? str(r.ref) : null;
        return t && ref ? [{ type: t, ref }] : [];
      }),
      confirmations,
    };
  };

  const prim = rec(recArt.primary_recommendation);
  const primary = prim && str(prim.candidate_id)
    ? toProduct(str(prim.candidate_id)!, str(prim.reason))
    : null;

  const alternatives: VMProduct[] = arr(recArt.alternatives).flatMap((a) => {
    const r = rec(a);
    const cid = r ? str(r.candidate_id) : null;
    return cid ? [toProduct(cid, str(r?.reason))] : [];
  });

  const noPrimaryReasons: string[] = [];
  if (primary === null) {
    const seen = new Set<string>();
    for (const nr of arr(recArt.not_recommended)) {
      const r = rec(nr);
      const reason = r ? str(r.reason) : null;
      if (reason && !seen.has(reason)) { seen.add(reason); noPrimaryReasons.push(reason); }
    }
    for (const u of arr(recArt.uncertainties)) {
      const r = rec(u);
      const d = r ? str(r.detail) : null;
      const cid = r ? str(r.candidate_id) : null;
      const line = d ? (cid ? `候选 ${cid}：${d}` : d) : null;
      if (line && !seen.has(line)) { seen.add(line); noPrimaryReasons.push(line); }
    }
  }

  const insufficient: { candidateId: string; provenance: { type: string; ref: string }[] }[] =
    evals.flatMap((e) => {
      const cid = str(e.candidate_id);
      if (!cid || str(e.recommendation_status) !== "insufficient_evidence") return [];
      return [{
        candidateId: cid,
        provenance: arr(e.provenance).flatMap((p) => {
          const r = rec(p);
          const t = r ? str(r.type) : null;
          const ref = r ? str(r.ref) : null;
          return t && ref ? [{ type: t, ref }] : [];
        }),
      }];
    });

  return {
    primary,
    noPrimaryReasons,
    alternatives,
    insufficient,
    humanReviewRequired: recArt.human_review_required === true,
    recommendationStatus: str(recArt.status),
  };
}

// ---- human review items --------------------------------------------------- //

function buildHumanReview(
  b: RawBundle,
  customer: VMCustomer,
  reco: VMRecommendation | null,
): VMHumanReview {
  const must: VMReviewItem[] = [];
  const suggest: VMReviewItem[] = [];
  const card = b.reviewCard;
  if (card) {
    for (const f of card.risk_flags) {
      const item: VMReviewItem = {
        title: f.message,
        detail: f.evidence_ref,
        source: `Review Card · ${f.type}（${f.severity}）`,
      };
      if (f.severity === "HIGH") must.push(item);
      else if (f.severity === "MEDIUM") suggest.push(item);
    }
    for (const fc of card.automatic_validation.failed_checks) {
      must.push({
        title: `自动校验未通过：${fc.check_id}`,
        detail: fc.message,
        source: `${fc.artifact_type ?? "—"} · ${fc.eval_id ?? "—"}`
          .replace(/· —$/, ""),
      });
    }
  }
  if (reco?.humanReviewRequired) {
    must.push({
      title: "推荐引擎标记：本方案需要人工确认后才能交付",
      detail: null,
      source: "product-recommendation.human_review_required",
    });
  }
  // uncertainties (evidence not sufficient) — real blockers for a rec
  const recArt = payloadOf(b, "product-recommendation");
  for (const u of arr(recArt ? recArt.uncertainties : null)) {
    const r = rec(u);
    const d = r ? str(r.detail) : null;
    const cid = r ? str(r.candidate_id) : null;
    if (d)
      suggest.push({
        title: cid ? `候选 ${cid}：${d}` : d,
        detail: null,
        source: "product-recommendation.uncertainties",
      });
  }
  // eligibility checks the pipeline could not verify
  if (reco?.primary)
    for (const c of reco.primary.confirmations)
      suggest.push({ title: c.label, detail: c.detail, source: "产品核保校验" });
  // client fields not confirmed
  for (const u of customer.unconfirmed) {
    suggest.push({
      title: `客户「${u.label}」尚未确认`,
      detail: u.status === "MISSING" ? "上游未提供该信息" : `字段状态：${u.status ?? "—"}`,
      source: "client-profile",
    });
  }
  // explicit information_gaps from gap/solution artifacts
  const cg = payloadOf(b, "coverage-gap-analysis");
  const sp = payloadOf(b, "solution-plan");
  for (const [src, art] of [["保障缺口分析", cg], ["解决方案", sp]] as const) {
    for (const g of arr(art ? art.information_gaps : null)) {
      const s = str(g) ?? (rec(g) ? str(rec(g)?.description) : null);
      if (s) suggest.push({ title: s, detail: null, source: `${src} · 信息缺口` });
    }
  }
  const verifiedNote = customer.knownLabels.length > 0
    ? `客户基本资料 ${customer.knownLabels.length} 项已由客户录入确认（client-intake）`
    : null;
  return { must, suggest, verifiedNote };
}

// ---- executive summary ----------------------------------------------------- //

function buildSummary(
  b: RawBundle,
  customer: VMCustomer,
  risks: VMRiskRow[],
  solutions: VMSolution[],
  humanReview: VMHumanReview,
): VMExecutiveSummary {
  const gaps = risks.filter((r) => r.gapLevelRaw !== null);
  const worstOrder: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
  const worst = gaps.slice().sort((a, c) =>
    (worstOrder[a.gapLevelRaw ?? ""] ?? 9) - (worstOrder[c.gapLevelRaw ?? ""] ?? 9))[0] ?? null;
  const mainGap = worst
    ? `${worst.gapSubject ?? worst.name ?? "保障缺口"} · ${worst.gapLevelLabel ?? ""}`.trim()
    : null;
  const covNow = customer.fields
    .filter((f) => f.label === "社保" || f.label === "已购商业保险")
    .map((f) => f.value)
    .filter((v): v is string => v !== null)
    .join("；") || null;
  const advice = solutions
    .map((s) => s.objective)
    .filter((o): o is string => o !== null)
    .join("；") || null;
  const card = b.reviewCard;
  const open = humanReview.must.length + humanReview.suggest.length;
  let reviewStatus: VMExecutiveSummary["reviewStatus"];
  if (card) {
    const level = card.review_action.level;
    reviewStatus = {
      text: `${LEVEL_TEXT[level] ?? level}${open > 0 ? ` · ${open} 项待人工确认` : ""}${card.validation_status === "FAIL" ? " · 自动校验未通过" : ""}`,
      tone: level === "AUTO_PASS" && card.validation_status !== "FAIL" ? "ok"
        : level === "DEEP_REVIEW" || card.validation_status === "FAIL" ? "alert" : "warn",
    };
  } else {
    reviewStatus = {
      text: b.approval ? `审批状态：${b.approval.status}` : null,
      tone: "warn",
    };
  }
  return {
    need: customer.needHeadline,
    currentCoverage: covNow,
    mainGap,
    agentAdvice: advice,
    reviewStatus,
  };
}

// ---- deliverables / report / execution -------------------------------------- //

function buildDeliverables(b: RawBundle): VMDeliverable[] {
  const list = (b.artifacts ?? []).slice();
  list.sort((a, c) => {
    const ia = ARTIFACT_ORDER.indexOf(a.artifact_type);
    const ic = ARTIFACT_ORDER.indexOf(c.artifact_type);
    return (ia === -1 ? 99 : ia) - (ic === -1 ? 99 : ic);
  });
  return list.map((a) => ({
    artifactType: a.artifact_type,
    titleLabel: ARTIFACT_TITLE[a.artifact_type] ?? a.artifact_type,
    statusLabel: a.status === "VALID" ? "已生成" : (a.status ?? null),
    createdAt: a.created_at,
    isReport: a.artifact_type === "insurance-report",
  }));
}

function buildExecution(events: RuntimeEvent[] | null): VMExecutionStep[] {
  const steps: VMExecutionStep[] = [];
  const byStage = new Map<string, VMExecutionStep>();
  for (const e of events ?? []) {
    if (e.event_type !== "stage_completed" && e.event_type !== "stage_failed") continue;
    const stage = e.stage ?? "unknown-stage";
    const step: VMExecutionStep = {
      key: `${stage}#${steps.length}`,
      label: stageLabel(stage),
      stage,
      status: e.event_type === "stage_completed" ? "completed" : "failed",
      timestamp: e.timestamp,
    };
    const prev = byStage.get(stage);
    if (prev && prev.status === "completed") continue; // keep first completion
    if (prev) steps.splice(steps.indexOf(prev), 1, step);
    else steps.push(step);
    byStage.set(stage, step);
  }
  return steps;
}

// ---- entry ------------------------------------------------------------------- //

export function buildReviewWorkspaceVM(b: RawBundle): ReviewWorkspaceVM {
  const customer = buildCustomer(b);
  const { list: gaps, byId: gapsById } = buildGaps(b);
  const risks = buildRisks(b, gaps);
  const solutions = buildSolutions(b);
  const recommendation = buildRecommendation(b, gapsById);
  const humanReview = buildHumanReview(b, customer, recommendation);
  const summary = buildSummary(b, customer, risks, solutions, humanReview);
  const reportArt = payloadOf(b, "insurance-report");
  const sr = reportArt ? rec(reportArt.structured_report) : null;
  return {
    runId: rec(b.run) ? str(rec(b.run)?.run_id) : null,
    customer,
    needs: buildNeeds(b),
    summary,
    risks,
    solutions,
    recommendation,
    humanReview,
    deliverables: buildDeliverables(b),
    reportMarkdown: reportArt ? str(reportArt.rendered_report) : null,
    reportTitle: sr ? str(sr.title) : null,
    reportGeneratedAt: sr ? str(sr.generated_at) : null,
    execution: buildExecution(b.events),
    evidence: buildEvidence(b),
  };
}
