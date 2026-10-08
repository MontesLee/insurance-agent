import { describe, expect, it } from "vitest";
import type { RuntimeEvent } from "../../types/runtime";
import type { ReviewCard } from "../../types/reviewCard";
import { buildReviewWorkspaceVM, fmtAmount, type RawBundle } from "./viewModel";

/**
 * Adapter tests over fixtures shaped like the REAL staged pilot payloads
 * (bm-complete-006 single-medical / bm-highrisk no-primary), trimmed but
 * field-accurate. The adapter must copy text verbatim, degrade honestly,
 * and never invent a value.
 */

const detail = (artifact: unknown) => ({ artifact_id: "ART-1", artifact });

const CLIENT_PROFILE = detail({
  payload: {
    client_state_version: "1.0",
    source: { origin_skill: "client-intake", intake_complete: true },
    family_profile: {
      age: { value: "35", status: "KNOWN" },
      gender: { value: "男", status: "KNOWN" },
      marital_status: { value: "已婚", status: "KNOWN" },
      children: { value: "1个（6岁）", status: "KNOWN" },
      housing: { value: "与父母同住", status: "KNOWN" },
    },
    employment_profile: { occupation: { value: "企业中层管理", status: "KNOWN" } },
    responsibility_profile: {
      economic_responsibility: { value: "家庭主要收入来源", status: "KNOWN" },
    },
    existing_protection: {
      social_security: { value: "职工社保+医保", status: "KNOWN" },
      existing_insurance: { value: "一份百万医疗险", status: "KNOWN" },
    },
    financial_profile: {
      annual_income: { value: "80万", status: "KNOWN" },
      annual_expense: { value: "36万", status: "KNOWN" },
      mortgage: { value: "200万", status: "KNOWN" },
      insurance_budget: { value: "3万", status: "KNOWN" },
    },
    missing_from_upstream: [],
    conflicts: [],
  },
});

const REQUIREMENTS = detail({
  payload: {
    analysis_status: "COMPLETE",
    requirements: [{
      requirement_id: "REQ-MED",
      requirement_type: "medical",
      summary: "解决医疗支出压力",
      priority: "P1_HIGH",
      reason: "因为客户是家庭主要收入来源，仅有百万医疗险。",
    }],
  },
});

const RISKS = detail({
  payload: {
    risks: [{
      risk_id: "R1-001",
      risk_name: "大额医疗费用支出",
      priority: "P1",
      severity: "HIGH",
      likelihood: "HIGH",
      residual_risk: "HIGH",
      existing_protection: "一份百万医疗险",
      coverage_assessment: { protected_amount: 0, unprotected_amount: 500000, confidence: 0.7 },
      conclusion: "医疗费用存在较大缺口",
      reason: "因为客户仅有百万医疗险，目录外费用无保障。",
      reasoning_evidence_refs: ["01_medical_insurance_002"],
    }],
  },
});

const GAPS = detail({
  payload: {
    gaps: [{
      gap_id: "GAP-R1-001",
      domain: "medical",
      subject: "大额医疗费用支出",
      related_risk_ids: ["R1-001"],
      current_coverage: { status: "PARTIAL" },
      target_coverage: {
        direction: "补充商业医疗险，对社保目录外费用形成补充",
        rationale: "分层保障",
      },
      gap_level: "CRITICAL",
      confidence: 0.7,
      reason: "因为覆盖状态为 PARTIAL，判定为缺口等级 CRITICAL。",
    }],
    priorities: [{ gap_id: "GAP-R1-001", priority: "P1", reason: "医疗保费最高" }],
    information_gaps: [],
    status: "COMPLETE",
  },
});

const SOLUTION = detail({
  payload: {
    solutions: [{
      solution_id: "SOL-001",
      solution_type: "MEDICAL",
      objective: "建立大额医疗支出保障",
      coverage_direction: "优先补足社保目录外费用",
      priority: "P0",
      trade_offs: [{ axis: "保障范围", chosen: "目录内外均覆盖", reason: "大额支出主要在目录外" }],
      rejected_directions: [{ direction: "仅提高社保", reason: "社保目录限制无法覆盖大额支出" }],
      related_gap_ids: ["GAP-R1-001"],
      reason: "因为 GAP-R1-001 缺口等级 CRITICAL，所以采用 MEDICAL 方案。",
    }],
    information_gaps: [],
    status: "COMPLETE",
  },
});

// product-candidates carries fields directly on `.artifact` (no payload
// wrapper) — the legacy catalog shape the adapter must also accept.
const CANDIDATES = {
  artifact_id: "ART-7",
  artifact: {
    skill: "product-candidate-provider",
    version: "0.1",
    status: "COMPLETE",
    candidates: [{
      candidate_id: "C001",
      product_id: "P001",
      product_name: "demo-百万医疗险A（标准版）",
      product_type: "medical",
      company: "demo-insurer-A",
      features: ["住院医疗费用", "特定门诊"],
      constraints: [{ constraint: "deductible", value: "10000元" }],
      premium: { annual: 400, basis: "demo_reference" },
      term: { years: 1 },
      related_gap_ids: ["GAP-R1-001"],
      eligibility: {
        status: "ELIGIBLE",
        checks: [
          { rule: "age", status: "PASS", detail: "age=35" },
          { rule: "occupation_class", status: "UNKNOWN", detail: "occupation class not available; check skipped" },
        ],
        reasons: [],
      },
    }],
  },
};

const REC = (over: Record<string, unknown> = {}) => detail({
  payload: {
    status: "COMPLETE",
    decision_context: {},
    candidate_evaluations: [{
      candidate_id: "C001",
      requirement_fit: { overall: "strong_fit", score: 1.0, matched: ["REQ-MED"] },
      risk_fit: { overall: "strong_fit", covered_risks: ["R1-001"] },
      evidence: { status: "supported", refs: ["01_medical_insurance_002"], missing_evidence: [] },
      recommendation_status: "primary",
      reason: "因为需求匹配度 strong_fit，判定推荐状态为 primary",
      provenance: [
        { type: "requirement", ref: "REQ-MED" },
        { type: "knowledge", ref: "01_medical_insurance_002" },
      ],
    }],
    primary_recommendation: {
      candidate_id: "C001",
      fit: "strong_fit",
      reason: "因为需求匹配度 strong_fit、覆盖高优先级风险 R1-001，所以作为主推荐",
      provenance: [
        { type: "requirement", ref: "REQ-MED" },
        { type: "knowledge", ref: "01_medical_insurance_002" },
      ],
      product: { product_id: "P001", product_name: "demo-百万医疗险A（标准版）" },
    },
    alternatives: [],
    not_recommended: [],
    tradeoffs: [],
    uncertainties: [],
    human_review_required: false,
    ...over,
  },
});

const KEV = detail({
  payload: {
    status: "success",
    evidence: [{
      evidence_id: "01_medical_insurance_002",
      content: "百万医疗险以费用报销为主要赔付方式。",
      source: "01_medical_insurance",
      section: "2. 赔付方式",
    }],
  },
});

const REPORT = detail({
  payload: {
    status: "success",
    structured_report: { title: "客户保险需求分析报告", generated_at: "2026-09-24T07:11:19Z" },
    rendered_report: "# 客户保险需求分析报告\n\n## 01 客户画像",
  },
});

const CARD = (over: Record<string, unknown> = {}): ReviewCard => ({
  schema_version: "1.0",
  card_id: "HRC-test",
  case_id: "bm-x",
  run_id: "run-1",
  generated_at: "2026-09-24T12:00:00Z",
  customer_summary: { age: "35", unresolved: [] },
  agent_summary: {
    case_status: "COMPLETED",
    objective: ["REQ-MED · 医疗 (P1_HIGH)"],
    recommendation_status: "COMPLETE",
    primary: { candidate_id: "C001", product_id: "P001", product_name: "demo-百万医疗险A" },
    recommendation: ["demo-百万医疗险A"],
    risk_highlights: [],
    waiting_for_user: null,
  },
  automatic_validation: {
    schema_check: "PASS", trace_check: "PASS", evidence_check: "PASS", logic_check: "PASS",
    eval_summary: { total: 9, passed: 9, failed: 0, failed_eval_ids: [] },
    failed_checks: [],
  },
  risk_flags: [],
  review_action: { required: true, level: "SUMMARY_REVIEW", reasons: [] },
  validation_status: "PASS",
  sampling: { rate: 0.1, triggered: false, seed: "bm-x" },
  ...over,
}) as ReviewCard;

function ev(over: Partial<RuntimeEvent>): RuntimeEvent {
  return {
    event_id: "e1", run_id: "run-1", timestamp: "2026-09-24T09:30:00Z",
    event_type: "stage_completed", stage: null, skill: null, status: null,
    case_id: null, artifact_id: null, eval_id: null, repair_attempt: null,
    message: null, data: {},
    ...over,
  };
}

function bundle(over: Partial<RawBundle> = {}): RawBundle {
  return {
    approval: null,
    supervisor: null,
    caseDesc: "单一需求客户（仅医疗保障）",
    run: { run_id: "run-1", case_id: "bm-x", status: "completed", restored: true },
    events: [
      ev({ event_type: "run_started" }),
      ev({ event_type: "stage_completed", stage: "requirement-analysis" }),
      ev({ event_type: "stage_completed", stage: "solution" }),
      ev({ event_type: "stage_failed", stage: "report-generation" }),
      ev({ event_type: "run_completed" }),
    ],
    artifacts: [{ artifact_type: "insurance-report", status: "VALID", created_at: "2026-09-24T07:11:19Z" }],
    details: {
      "client-profile": CLIENT_PROFILE,
      "requirement-analysis": REQUIREMENTS,
      "risk-assessment": RISKS,
      "coverage-gap-analysis": GAPS,
      "solution-plan": SOLUTION,
      "product-candidates": CANDIDATES,
      "product-recommendation": REC(),
      "knowledge-evidence": KEV,
      "insurance-report": REPORT,
    },
    reviewCard: CARD(),
    ...over,
  };
}

describe("fmtAmount", () => {
  it("converts clean 万 multiples and localizes the rest", () => {
    expect(fmtAmount(500000)).toBe("50万");
    expect(fmtAmount(2000000)).toBe("200万");
    expect(fmtAmount(0)).toBe("0");
    expect(fmtAmount(12345)).toBe("12,345");
  });
});

describe("customer projection", () => {
  it("builds the demographic line verbatim from client-profile values", () => {
    const vm = buildReviewWorkspaceVM(bundle());
    expect(vm.customer.demographicLine).toBe("35岁 · 男 · 已婚 · 子女1个（6岁）");
    expect(vm.customer.caseTitle).toBe("单一需求客户（仅医疗保障）");
    expect(vm.customer.needHeadline).toBe("解决医疗支出压力");
    expect(vm.customer.knownLabels).toHaveLength(13);
    expect(vm.customer.unconfirmed).toEqual([]);
  });

  it("treats UNKNOWN and missing_from_upstream fields as unconfirmed, never as values", () => {
    const cp = JSON.parse(JSON.stringify(CLIENT_PROFILE)) as {
      artifact: { payload: Record<string, unknown> };
    };
    const payload = cp.artifact.payload;
    const fam = payload.family_profile as Record<string, { value: string; status: string }>;
    fam.age = { value: "", status: "UNKNOWN" };
    payload.missing_from_upstream = ["健康状况"];
    const vm = buildReviewWorkspaceVM(bundle({ details: { ...bundle().details, "client-profile": cp } }));
    expect(vm.customer.demographicLine).not.toContain("35岁");
    expect(vm.customer.unconfirmed).toEqual(
      expect.arrayContaining([
        { label: "年龄", status: "UNKNOWN" },
        { label: "健康状况", status: "MISSING" },
      ]),
    );
    expect(vm.humanReview.suggest.some((s) => s.title.includes("年龄"))).toBe(true);
  });
});

describe("risk ⋈ gap projection", () => {
  it("joins risk to gap and formats amounts; raw enums survive", () => {
    const vm = buildReviewWorkspaceVM(bundle());
    const row = vm.risks[0]!;
    expect(row.riskId).toBe("R1-001");
    expect(row.name).toBe("大额医疗费用支出");
    expect(row.gapId).toBe("GAP-R1-001");
    expect(row.gapLevelLabel).toBe("严重");
    expect(row.gapLevelRaw).toBe("CRITICAL");
    expect(row.unprotectedLabel).toBe("50万未受保障");
    expect(row.advice).toContain("补充商业医疗险");
    expect(row.rationale.reason).toContain("百万医疗险");
    expect(row.rationale.evidenceRefs).toEqual(["01_medical_insurance_002"]);
  });

  it("keeps orphan gaps as rows (subject as name) instead of dropping them", () => {
    const gaps = JSON.parse(JSON.stringify(GAPS)) as typeof GAPS;
    const g = (gaps.artifact as { payload: { gaps: Record<string, unknown>[] } }).payload.gaps[0]!;
    g.related_risk_ids = [];
    const vm = buildReviewWorkspaceVM(bundle({ details: { ...bundle().details, "coverage-gap-analysis": gaps } }));
    expect(vm.risks).toHaveLength(2);
    expect(vm.risks[1]!.name).toBe("大额医疗费用支出");
    expect(vm.risks[1]!.riskId).toBeNull();
  });
});

describe("recommendation projection", () => {
  it("joins primary to catalog candidate (premium/term/features/confirmations)", () => {
    const vm = buildReviewWorkspaceVM(bundle());
    const p = vm.recommendation?.primary ?? null;
    expect(p?.name).toBe("demo-百万医疗险A（标准版）");
    expect(p?.premiumAnnual).toBe(400);
    expect(p?.termYears).toBe(1);
    expect(p?.solves).toEqual(["大额医疗费用支出"]);
    expect(p?.why).toContain("strong_fit");
    expect(p?.confirmations).toEqual([
      { label: "核保项「occupation_class」未校验", detail: "occupation class not available; check skipped" },
    ]);
    expect(vm.humanReview.suggest.some((s) => s.title.includes("occupation_class"))).toBe(true);
  });

  it("no primary → real reasons surface, nothing invented", () => {
    const rec = REC({
      primary_recommendation: null,
      human_review_required: true,
      not_recommended: [
        { candidate_id: "C001", reason: "因为产品校验未通过（product_ineligible），所以不推荐" },
        { candidate_id: "C002", reason: "因为产品校验未通过（product_ineligible），所以不推荐" },
      ],
      uncertainties: [{ type: "insufficient_evidence", detail: "coverage ['accident'] lacks knowledge backing", candidate_id: "C008" }],
    });
    const vm = buildReviewWorkspaceVM(bundle({ details: { ...bundle().details, "product-recommendation": rec } }));
    expect(vm.recommendation?.primary).toBeNull();
    // deduped not_recommended + uncertainty detail
    expect(vm.recommendation?.noPrimaryReasons).toEqual([
      "因为产品校验未通过（product_ineligible），所以不推荐",
      "候选 C008：coverage ['accident'] lacks knowledge backing",
    ]);
    expect(vm.humanReview.must.some((m) => m.source.includes("human_review_required"))).toBe(true);
  });

  it("missing recommendation artifact → null (renders 未产出)", () => {
    const details = { ...bundle().details };
    delete details["product-recommendation"];
    const vm = buildReviewWorkspaceVM(bundle({ details }));
    expect(vm.recommendation).toBeNull();
  });
});

describe("summary / human review / execution", () => {
  it("five summary cards answer from real fields", () => {
    const vm = buildReviewWorkspaceVM(bundle());
    expect(vm.summary.need).toBe("解决医疗支出压力");
    expect(vm.summary.currentCoverage).toBe("职工社保+医保；一份百万医疗险");
    expect(vm.summary.mainGap).toBe("大额医疗费用支出 · 严重");
    expect(vm.summary.agentAdvice).toBe("建立大额医疗支出保障");
    expect(vm.summary.reviewStatus.text).toContain("摘要审核");
    expect(vm.summary.reviewStatus.tone).toBe("warn");
  });

  it("HIGH card flags become 需要确认; MEDIUM become 建议确认", () => {
    const vm = buildReviewWorkspaceVM(bundle({
      reviewCard: CARD({
        risk_flags: [
          { type: "missing_evidence", severity: "HIGH", message: "关键证据缺失", evidence_ref: "rec:e1" },
          { type: "no_primary_recommendation", severity: "MEDIUM", message: "无主推荐", evidence_ref: null },
        ],
      }),
    }));
    expect(vm.humanReview.must.map((m) => m.title)).toContain("关键证据缺失");
    expect(vm.humanReview.suggest.map((s) => s.title)).toContain("无主推荐");
    expect(vm.summary.reviewStatus.text).toContain("3 项待人工确认");
  });

  it("execution steps use human verbs, keep failures, dedupe stages", () => {
    const vm = buildReviewWorkspaceVM(bundle());
    expect(vm.execution.map((s) => `${s.status}:${s.label}`)).toEqual([
      "completed:需求分析",
      "completed:解决方案设计",
      "failed:方案报告生成",
    ]);
    expect(vm.evidence[0]!.id).toBe("01_medical_insurance_002");
  });

  it("empty bundle degrades to nulls everywhere (no fabrication)", () => {
    const vm = buildReviewWorkspaceVM({
      approval: null, supervisor: null, caseDesc: null, run: null,
      events: null, artifacts: null, details: {}, reviewCard: null,
    });
    expect(vm.customer.demographicLine).toBeNull();
    expect(vm.risks).toEqual([]);
    expect(vm.solutions).toEqual([]);
    expect(vm.recommendation).toBeNull();
    expect(vm.humanReview.must).toEqual([]);
    expect(vm.humanReview.verifiedNote).toBeNull();
    expect(vm.reportMarkdown).toBeNull();
  });
});
