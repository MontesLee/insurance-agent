import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewWorkspace } from "./ReviewWorkspace";
import type { ApprovalRecord } from "../../types/approval";
import type { RuntimeEvent } from "../../types/runtime";

/**
 * Phase 27.7.7 — human-readable workspace. Fixtures mirror the REAL
 * staged pilot payloads (trimmed, field-accurate). Behaviors locked by
 * earlier phases stay locked: auto-link (no manual run input), verbatim
 * statuses, no fabrication, loud failures with Retry, artifact JSON copy.
 */

const APPROVAL: ApprovalRecord = {
  approval_id: "apr_1",
  project_id: "proj-1",
  task_id: "",
  graph_revision: 1,
  request_type: "APPROVAL_FINAL_REVIEW",
  reason: "final deliverable requires human review before delivery",
  context: { artifact_ids: ["art-9"], task_types: ["report"] },
  options: ["approve", "reject"],
  default_action: null,
  status: "WAITING_HUMAN",
  requested_by: "harness",
  created_at: new Date(Date.now() - 10 * 60000).toISOString(),
  resolved_at: null,
  resolved_by: null,
  decision: null,
};

const LEGACY_APPROVAL: ApprovalRecord = {
  ...APPROVAL,
  context: { ...APPROVAL.context, run_id: "run-1" },
};

const CARD = (
  over: {
    level?: "AUTO_PASS" | "SUMMARY_REVIEW" | "DEEP_REVIEW";
    flags?: { type: string; severity: "HIGH" | "MEDIUM" | "LOW"; message: string; evidence_ref: string | null }[];
  } = {},
) => ({
  schema_version: "1.0",
  card_id: "HRC-1",
  case_id: "bm-x",
  run_id: "run-1",
  generated_at: "2026-09-24T12:00:00Z",
  generator: "test",
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
  risk_flags: over.flags ?? [],
  review_action: { required: true, level: over.level ?? "SUMMARY_REVIEW", reasons: [] },
  validation_status: "PASS",
  sampling: { rate: 0.1, triggered: false, seed: "bm-x" },
});

const SUPERVISOR = {
  project_id: "proj-1",
  supervisor: {
    project_id: "proj-1", status: "RUNNING", risk_level: "LOW",
    active_alerts: [], pending_interventions: [],
    last_event_id: null, last_checkpoint_id: null, updated_at: "2026-09-24T09:33:00Z",
  },
};

const RUN = { run_id: "run-1", case_id: "bm-x", status: "completed", created_at: "2026-09-24T07:11:00Z", restored: true };

function ev(eid: string, over: Partial<RuntimeEvent>): RuntimeEvent {
  return {
    event_id: eid, run_id: "run-1", timestamp: "2026-09-24T09:30:00Z",
    event_type: "stage_completed", stage: null, skill: null, status: null,
    case_id: null, artifact_id: null, eval_id: null, repair_attempt: null,
    message: null, data: {},
    ...over,
  };
}

const EVENTS: RuntimeEvent[] = [
  ev("e1", { event_type: "run_started" }),
  ev("e2", { event_type: "stage_completed", stage: "client-intake" }),
  ev("e3", { event_type: "stage_completed", stage: "requirement-analysis" }),
  ev("e4", { event_type: "stage_started", stage: "risk-analysis" }),
  ev("e5", { event_type: "stage_completed", stage: "risk-analysis" }),
  ev("e6", { event_type: "stage_failed", stage: "report-generation" }),
  ev("e7", { event_type: "run_completed" }),
];

const ARTIFACT_LIST = [
  "client-profile", "requirement-analysis", "risk-assessment", "coverage-gap-analysis",
  "solution-plan", "product-candidates", "product-recommendation", "knowledge-evidence",
  "insurance-report",
].map((t, i) => ({
  artifact_id: `ART-00${i + 1}`, artifact_type: t,
  producer_stage: t, producer_skill: t, created_at: "2026-09-24T07:11:19Z",
  status: "VALID", input_artifacts: [], evidence_refs: [], lineage: [],
}));

const detail = (artifact: unknown) => ({ artifact_id: "ART-1", artifact });

const DETAILS: Record<string, unknown> = {
  "client-profile": detail({
    payload: {
      family_profile: {
        age: { value: "35", status: "KNOWN" }, gender: { value: "男", status: "KNOWN" },
        marital_status: { value: "已婚", status: "KNOWN" }, children: { value: "1个（6岁）", status: "KNOWN" },
        housing: { value: "与父母同住", status: "KNOWN" },
      },
      employment_profile: { occupation: { value: "企业中层管理", status: "KNOWN" } },
      responsibility_profile: { economic_responsibility: { value: "家庭主要收入来源", status: "KNOWN" } },
      existing_protection: {
        social_security: { value: "职工社保+医保", status: "KNOWN" },
        existing_insurance: { value: "一份百万医疗险", status: "KNOWN" },
      },
      financial_profile: {
        annual_income: { value: "80万", status: "KNOWN" }, annual_expense: { value: "36万", status: "KNOWN" },
        mortgage: { value: "200万", status: "KNOWN" }, insurance_budget: { value: "3万", status: "KNOWN" },
      },
      missing_from_upstream: [], conflicts: [],
    },
  }),
  "requirement-analysis": detail({
    payload: {
      analysis_status: "COMPLETE",
      requirements: [{
        requirement_id: "REQ-MED", requirement_type: "medical", summary: "解决医疗支出压力",
        priority: "P1_HIGH", reason: "因为客户是家庭主要收入来源。",
      }],
    },
  }),
  "risk-assessment": detail({
    payload: {
      risks: [{
        risk_id: "R1-001", risk_name: "大额医疗费用支出", severity: "HIGH", likelihood: "HIGH",
        residual_risk: "HIGH", existing_protection: "一份百万医疗险",
        coverage_assessment: { protected_amount: 0, unprotected_amount: 500000, confidence: 0.7 },
        conclusion: "医疗费用存在较大缺口", reason: "因为客户仅有百万医疗险，目录外费用无保障。",
        reasoning_evidence_refs: ["01_medical_insurance_002"],
      }],
    },
  }),
  "coverage-gap-analysis": detail({
    payload: {
      gaps: [{
        gap_id: "GAP-R1-001", domain: "medical", subject: "大额医疗费用支出",
        related_risk_ids: ["R1-001"], current_coverage: { status: "PARTIAL" },
        target_coverage: { direction: "补充商业医疗险，对社保目录外费用形成补充", rationale: "分层保障" },
        gap_level: "CRITICAL", confidence: 0.7, reason: "因为覆盖状态为 PARTIAL。",
      }],
      priorities: [], information_gaps: [], status: "COMPLETE",
    },
  }),
  "solution-plan": detail({
    payload: {
      solutions: [{
        solution_id: "SOL-001", solution_type: "MEDICAL", objective: "建立大额医疗支出保障",
        coverage_direction: "优先补足社保目录外费用", priority: "P0",
        trade_offs: [{ axis: "保障范围", chosen: "目录内外均覆盖", reason: "大额支出主要在目录外" }],
        rejected_directions: [{ direction: "仅提高社保", reason: "社保目录限制无法覆盖大额支出" }],
        related_gap_ids: ["GAP-R1-001"], reason: "因为 GAP-R1-001 缺口等级 CRITICAL，所以采用 MEDICAL 方案。",
      }],
      information_gaps: [], status: "COMPLETE",
    },
  }),
  // legacy catalog shape: fields directly on `.artifact`, no payload wrapper
  "product-candidates": {
    artifact_id: "ART-7",
    artifact: {
      skill: "product-candidate-provider", version: "0.1", status: "COMPLETE",
      candidates: [{
        candidate_id: "C001", product_id: "P001", product_name: "demo-百万医疗险A（标准版）",
        product_type: "medical", company: "demo-insurer-A",
        features: ["住院医疗费用", "特定门诊"],
        constraints: [{ constraint: "deductible", value: "10000元" }],
        premium: { annual: 400, basis: "demo_reference" }, term: { years: 1 },
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
  },
  "product-recommendation": detail({
    payload: {
      status: "COMPLETE",
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
        candidate_id: "C001", fit: "strong_fit",
        reason: "因为需求匹配度 strong_fit、覆盖高优先级风险 R1-001，所以作为主推荐",
        provenance: [
          { type: "requirement", ref: "REQ-MED" },
          { type: "knowledge", ref: "01_medical_insurance_002" },
        ],
        product: { product_id: "P001", product_name: "demo-百万医疗险A（标准版）" },
      },
      alternatives: [], not_recommended: [], tradeoffs: [], uncertainties: [],
      human_review_required: false,
    },
  }),
  "knowledge-evidence": detail({
    payload: {
      status: "success",
      evidence: [{
        evidence_id: "01_medical_insurance_002",
        content: "百万医疗险以费用报销为主要赔付方式。",
        source: "01_medical_insurance", section: "2. 赔付方式",
      }],
    },
  }),
  "insurance-report": detail({
    payload: {
      status: "success",
      structured_report: { title: "客户保险需求分析报告", generated_at: "2026-09-24T07:11:19Z" },
      rendered_report: "# 客户保险需求分析报告\n\n## 01 客户画像\n\n- 年龄：35",
    },
  }),
};

interface CardFlag {
  type: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  message: string;
  evidence_ref: string | null;
}

interface StubOpts {
  noRun?: boolean;
  legacy?: boolean;
  failCard?: boolean;
  cardLevel?: "AUTO_PASS" | "SUMMARY_REVIEW" | "DEEP_REVIEW";
  cardFlags?: CardFlag[];
  noPrimary?: boolean;
  noDetails?: boolean;
  backendDownOnce?: boolean;
}

function stubAll(opts: StubOpts = {}) {
  const seen: string[] = [];
  let down = opts.backendDownOnce === true;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    seen.push(url);
    if (down && url.includes("/api/runs/run-1")) {
      down = false;
      throw new TypeError("Failed to fetch");
    }
    if (url.includes("/api/approvals/apr_1")) {
      if (opts.noRun)
        return Response.json({ project_id: "proj-1", approval: APPROVAL, review_context: {} });
      if (opts.legacy)
        return Response.json({ project_id: "proj-1", approval: LEGACY_APPROVAL });
      return Response.json({
        project_id: "proj-1", approval: APPROVAL,
        review_context: { run_id: "run-1", artifact_ids: ["art-9"] },
      });
    }
    if (url.includes("/api/projects/proj-1/supervisor"))
      return Response.json(SUPERVISOR);
    if (url.endsWith("/api/cases"))
      return Response.json({ cases: [{ id: "bm-x", category: "complete", desc: "单一需求客户（仅医疗保障）", kb: null }] });
    if (url.endsWith("/api/runs/run-1/review-card")) {
      if (opts.failCard) return Response.json({ error: "boom" }, { status: 500 });
      return Response.json(CARD({ level: opts.cardLevel, flags: opts.cardFlags }));
    }
    if (url.endsWith("/api/runs/run-1/events"))
      return Response.json({ run_id: "run-1", count: EVENTS.length, events: EVENTS });
    if (/\/api\/runs\/run-1\/artifacts\/[^/]+$/.test(url)) {
      const type = url.split("/artifacts/")[1] ?? "";
      if (opts.noDetails) return Response.json({ error: "none" }, { status: 404 });
      if (opts.noPrimary && type === "product-recommendation")
        return Response.json({
          artifact_id: "ART-8",
          artifact: {
            payload: {
              status: "NO_CANDIDATES",
              candidate_evaluations: [],
              primary_recommendation: null,
              alternatives: [],
              not_recommended: [
                { candidate_id: "C001", reason: "因为产品校验未通过（product_ineligible），所以不推荐" },
              ],
              tradeoffs: [], uncertainties: [], human_review_required: true,
            },
          },
        });
      return Response.json(DETAILS[type] ?? { error: "unknown artifact_type for this run" }, { status: DETAILS[type] ? 200 : 404 });
    }
    if (url.includes("/api/runs/run-1/artifacts"))
      return Response.json({ run_id: "run-1", count: ARTIFACT_LIST.length, artifacts: ARTIFACT_LIST });
    if (url.endsWith("/api/runs/run-1"))
      return Response.json(RUN);
    return Response.json({}, { status: 404 });
  });
  return { fetchMock, seen };
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

async function openWorkspace(opts: StubOpts = {}) {
  const { fetchMock, seen } = stubAll(opts);
  vi.stubGlobal("fetch", fetchMock);
  render(<ReviewWorkspace projectId="proj-1" approvalId="apr_1" onBack={() => {}} />);
  if (!opts.noRun && !opts.backendDownOnce)
    await screen.findByTestId("workspace-header");
  return { seen, fetchMock };
}

describe("Review Workspace — Phase 27.7.7 human-readable IA", () => {
  it("case header answers who / need / status without any internal ids", async () => {
    await openWorkspace();
    const h = screen.getByTestId("workspace-header");
    expect(h.textContent).toContain("35岁 · 男 · 已婚 · 子女1个（6岁）");
    expect(h.textContent).toContain("待人工审核");
    expect(h.textContent).toContain("单一需求客户（仅医疗保障）");
    expect(h.textContent).toContain("解决医疗支出压力");
    // internal identifiers stay OUT of the first paint
    expect(h.textContent).not.toContain("run-1");
    expect(h.textContent).not.toContain("apr_1");
    // customer profile drill-down toggles
    expect(screen.queryByTestId("client-profile-fields")).toBeNull();
    fireEvent.click(screen.getByTestId("show-client-profile"));
    expect(screen.getByTestId("client-profile-fields").textContent).toContain("职工社保+医保");
    expect(screen.getByTestId("start-human-review")).toBeInTheDocument();
  });

  it("executive summary: five cards, one question each", async () => {
    await openWorkspace();
    const s = screen.getByTestId("workspace-summary");
    expect(s.textContent).toContain("客户需求");
    expect(s.textContent).toContain("解决医疗支出压力");
    expect(s.textContent).toContain("职工社保+医保；一份百万医疗险");
    expect(s.textContent).toContain("大额医疗费用支出 · 严重");
    expect(s.textContent).toContain("建立大额医疗支出保障");
    expect(s.textContent).toContain("需要摘要审核");
  });

  it("risk table renders the join and expands to rationale + evidence原文", async () => {
    await openWorkspace();
    const row = screen.getByTestId("risk-row-R1-001");
    expect(row.textContent).toContain("大额医疗费用支出");
    expect(row.textContent).toContain("严重");
    expect(row.textContent).toContain("50万未受保障");
    expect(row.textContent).toContain("补充商业医疗险");
    // expand
    fireEvent.click(row);
    const risks = screen.getByTestId("workspace-risks");
    expect(risks.textContent).toContain("医疗费用存在较大缺口");
    expect(risks.textContent).toContain("因为客户仅有百万医疗险");
    expect(risks.textContent).toContain("百万医疗险以费用报销为主要赔付方式");
    expect(risks.textContent).toContain("01_medical_insurance");
  });

  it("solution section explains why, including rejected directions", async () => {
    await openWorkspace();
    const s = screen.getByTestId("workspace-solution");
    expect(s.textContent).toContain("因为 GAP-R1-001 缺口等级 CRITICAL");
    expect(s.textContent).toContain("建立大额医疗支出保障");
    expect(s.textContent).toContain("仅提高社保");
    expect(s.textContent).toContain("社保目录限制无法覆盖大额支出");
  });

  it("product section: why + table + 推荐依据 + 需要确认", async () => {
    await openWorkspace();
    const p = screen.getByTestId("workspace-products");
    expect(p.textContent).toContain("因为需求匹配度 strong_fit、覆盖高优先级风险 R1-001");
    expect(p.textContent).toContain("demo-百万医疗险A（标准版）");
    expect(p.textContent).toContain("¥400");
    expect(p.textContent).toContain("1 年");
    expect(p.textContent).toContain("住院医疗费用");
    expect(p.textContent).toContain("免赔额 10000元");
    expect(p.textContent).toContain("大额医疗费用支出");
    expect(p.textContent).toContain("核保项「occupation_class」未校验");
  });

  it("no primary recommendation → honest block with real reasons, nothing invented", async () => {
    await openWorkspace({ noPrimary: true });
    const p = screen.getByTestId("workspace-products");
    expect(p.textContent).toContain("本次未形成主推荐");
    expect(p.textContent).toContain("因为产品校验未通过（product_ineligible），所以不推荐");
    // human_review_required=true surfaces as a 需要确认 item
    const hr = screen.getByTestId("workspace-human-review");
    expect(hr.textContent).toContain("需要人工确认后才能交付");
  });

  it("human review buckets: 无/建议确认/已验证 counts", async () => {
    await openWorkspace();
    const hr = screen.getByTestId("workspace-human-review");
    expect(hr.textContent).toContain("需要你确认（0）");
    expect(hr.textContent).toContain("建议确认（1）"); // occupation_class
    expect(hr.textContent).toContain("客户基本资料 13 项已由客户录入确认");
  });

  it("HIGH card flag escalates to 需要确认", async () => {
    await openWorkspace({
      cardFlags: [{ type: "missing_evidence", severity: "HIGH", message: "关键证据缺失", evidence_ref: "rec:e1" }],
    });
    const hr = screen.getByTestId("workspace-human-review");
    expect(hr.textContent).toContain("关键证据缺失");
    expect(hr.textContent).toContain("需要你确认（1）");
  });

  it("deliverables: report card opens the rendered full report", async () => {
    await openWorkspace();
    const d = screen.getByTestId("workspace-deliverables");
    expect(d.textContent).toContain("客户保险需求分析报告");
    expect(d.textContent).toContain("已生成 · 待人工审核");
    fireEvent.click(screen.getByTestId("open-full-report"));
    expect(screen.getByTestId("full-report").textContent).toContain("客户画像");
  });

  it("execution: human-verb checklist, failures kept, raw log behind a toggle", async () => {
    await openWorkspace();
    const e = screen.getByTestId("workspace-execution");
    expect(e.textContent).toContain("已完成需求分析");
    expect(e.textContent).toContain("已完成家庭风险分析");
    expect(e.textContent).toContain("方案报告生成失败");
    // raw log is inside a collapsed <details>, present but not first paint
    expect(screen.getByTestId("workspace-timeline").textContent).toContain("run_started");
  });

  it("technical details keeps ALL internals accessible (run/approval/card/evidence/registry)", async () => {
    await openWorkspace();
    expect(screen.getByTestId("run-linked").textContent).toContain("run-1");
    expect(screen.getByTestId("workspace-approval").textContent).toContain("APPROVAL_FINAL_REVIEW");
    expect(screen.getByTestId("workspace-approval").textContent).toContain("apr_1");
    expect(screen.getByTestId("review-context-artifacts").textContent).toContain("art-9");
    expect(screen.getByTestId("review-card-detail").textContent).toContain("SUMMARY_REVIEW");
    expect(screen.getByTestId("workspace-evidence").textContent).toContain("主推荐:demo-百万医疗险A（标准版）");
    expect(screen.getByTestId("workspace-evidence").textContent).toContain("01_medical_insurance_002");
    expect(screen.getByTestId("workspace-artifact-insurance-report")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-case").textContent).toContain("RUNNING");
  });

  it("artifact JSON copy preserved inside technical details", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await openWorkspace();
    fireEvent.click(screen.getByTestId("workspace-artifact-copy-product-recommendation"));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(
      screen.getByTestId("workspace-artifact-copy-product-recommendation"),
    ).toHaveTextContent("已复制");
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
  });

  it("all artifact payloads missing → 暂无信息 everywhere, page intact", async () => {
    await openWorkspace({ noDetails: true });
    const h = screen.getByTestId("workspace-header");
    expect(h.textContent).toContain("单一需求客户"); // demographic absent → case title fallback
    expect(screen.getByTestId("workspace-risks").textContent).toContain("暂无信息");
    expect(screen.getByTestId("workspace-products").textContent).toContain("未产出产品推荐");
    expect(screen.getByTestId("workspace-execution")).toBeInTheDocument();
  });
});

describe("Review Workspace — locked behaviors from 27.5-3 / 27.7.6", () => {
  it("auto-links from review_context; no manual run input anywhere", async () => {
    await openWorkspace();
    expect(screen.queryByTestId("workspace-run-input")).toBeNull();
    expect(screen.queryByTestId("workspace-run-load")).toBeNull();
    expect(screen.getByTestId("run-linked").textContent).toContain("run-1");
  });

  it("legacy approval: falls back to raw context run_id", async () => {
    await openWorkspace({ legacy: true });
    expect(screen.getByTestId("run-linked").textContent).toContain("run-1");
  });

  it("missing run context: notice + decision panel still usable, no run fetches", async () => {
    const { seen } = await openWorkspace({ noRun: true });
    expect(await screen.findByTestId("run-unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("decision-panel")).toBeInTheDocument();
    expect(seen.some((u) => u.includes("/api/runs"))).toBe(false);
  });

  it("backend-down bundle failure is loud with Retry; retry recovers", async () => {
    const { fetchMock } = await openWorkspace({ backendDownOnce: true });
    expect(await screen.findByText(/案例分析加载失败/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("workspace-header")).toBeInTheDocument();
    expect(fetchMock.mock.calls.length).toBeGreaterThan(1);
  });

  it("review card fetch failure degrades softly (page still renders, card absent)", async () => {
    await openWorkspace({ failCard: true });
    expect(screen.getByTestId("workspace-header")).toBeInTheDocument();
    const t = screen.getByTestId("workspace-technical");
    expect(t.textContent).toContain("无 Review Card");
  });
});
