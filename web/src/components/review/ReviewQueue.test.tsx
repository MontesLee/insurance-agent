import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewQueue } from "./ReviewQueue";
import type { ApprovalRecord } from "../../types/approval";

/** Backend-verbatim approval records (runtime/approval/models.py). */
function rec(over: Partial<ApprovalRecord>): ApprovalRecord {
  return {
    approval_id: "apr_1",
    project_id: "proj-1",
    task_id: "task-1",
    graph_revision: 1,
    request_type: "RECOMMENDATION_REVIEW",
    reason: "王先生家庭保障分析",
    context: { client_name: "王先生", stage: "product-recommendation" },
    options: ["approve", "reject"],
    default_action: null,
    status: "WAITING_HUMAN",
    requested_by: "harness",
    created_at: new Date(Date.now() - 25 * 60000).toISOString(),
    resolved_at: null,
    resolved_by: null,
    decision: null,
    ...over,
  };
}

function stubApprovals(
  approvals: ApprovalRecord[],
  status = 200,
  cards: Record<string, unknown> = {},
  failCards = false,
) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/projects/proj-1/approvals")) {
      return Response.json({ project_id: "proj-1", approvals }, { status });
    }
    const rid = url.match(/\/api\/runs\/([^/]+)\/review-card$/)?.[1];
    if (rid) {
      if (failCards) return Response.json({ error: "boom" }, { status: 500 });
      const card = cards[rid];
      return card
        ? Response.json(card)
        : Response.json({ error: "unknown run" }, { status: 404 });
    }
    return Response.json({}, { status: 404 });
  });
}

/** Minimal backend-shaped Review Card (types/reviewCard.ts). */
function card(over: Record<string, unknown> = {}) {
  return {
    schema_version: "1.0",
    card_id: "HRC-00000001",
    case_id: "case-x",
    run_id: "run-1",
    generated_at: "2026-09-24T12:00:00Z",
    customer_summary: { age: "40", unresolved: [] },
    agent_summary: {
      case_status: "COMPLETED",
      objective: [],
      recommendation_status: "COMPLETE",
      primary: { candidate_id: "C001", product_id: "P001", product_name: "医疗险A" },
      recommendation: ["医疗险A"],
      risk_highlights: [],
      waiting_for_user: null,
    },
    automatic_validation: {
      schema_check: "PASS",
      trace_check: "PASS",
      evidence_check: "PASS",
      logic_check: "PASS",
      eval_summary: { total: 9, passed: 9, failed: 0, failed_eval_ids: [] },
      failed_checks: [],
    },
    risk_flags: [],
    review_action: { required: false, level: "AUTO_PASS", reasons: ["all checks PASS"] },
    validation_status: "PASS",
    sampling: { rate: 0.1, triggered: false, seed: "case-x:run-1" },
    ...over,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("Review Queue — Phase 27.5-2", () => {
  it("case 1: renders a 3-item approval list with verbatim statuses", async () => {
    vi.stubGlobal(
      "fetch",
      stubApprovals([
        rec({ approval_id: "apr_1" }),
        rec({ approval_id: "apr_2", status: "APPROVED", decision: "approve" }),
        rec({ approval_id: "apr_3", status: "REJECTED", decision: "reject" }),
      ]),
    );
    localStorage.setItem("webui:review-project", "proj-1");
    render(<ReviewQueue onOpenApproval={() => {}} />);
    await waitFor(() => screen.getByTestId("queue-list"));
    expect(screen.getByTestId("queue-item-apr_1")).toBeInTheDocument();
    expect(screen.getByTestId("queue-item-apr_2")).toBeInTheDocument();
    expect(screen.getByTestId("queue-item-apr_3")).toBeInTheDocument();
    // statuses are verbatim backend vocabulary
    expect(screen.getByTestId("approval-status-WAITING_HUMAN")).toBeInTheDocument();
    expect(screen.getByTestId("approval-status-APPROVED")).toBeInTheDocument();
    expect(screen.getByTestId("approval-status-REJECTED")).toBeInTheDocument();
    // actionable-first ordering: apr_1 (WAITING) renders before resolved ones
    const first = screen.getByTestId("queue-item-apr_1");
    const last = screen.getByTestId("queue-item-apr_3");
    expect(first.compareDocumentPosition(last)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(screen.getByTestId("queue-count").textContent).toContain("待处理 1");
    localStorage.removeItem("webui:review-project");
  });

  it("case 2: empty queue shows the empty state, not an error", async () => {
    vi.stubGlobal("fetch", stubApprovals([]));
    localStorage.setItem("webui:review-project", "proj-1");
    render(<ReviewQueue onOpenApproval={() => {}} />);
    expect(await screen.findByTestId("queue-empty")).toBeInTheDocument();
    expect(screen.getByText(/当前没有待审核事项/)).toBeInTheDocument();
    expect(screen.queryByTestId("queue-error")).not.toBeInTheDocument();
    localStorage.removeItem("webui:review-project");
  });

  it("case 3: API error shows the failure banner with Retry", async () => {
    vi.stubGlobal("fetch", stubApprovals([], 500));
    localStorage.setItem("webui:review-project", "proj-1");
    render(<ReviewQueue onOpenApproval={() => {}} />);
    expect(await screen.findByTestId("queue-error")).toBeInTheDocument();
    expect(screen.getByText(/审核队列加载失败/)).toBeInTheDocument();
    expect(screen.getByTestId("queue-retry")).toBeInTheDocument();
    localStorage.removeItem("webui:review-project");
  });

  it("case 4: clicking an item opens the approval detail entry", async () => {
    const open = vi.fn();
    vi.stubGlobal("fetch", stubApprovals([rec({ approval_id: "apr_9" })]));
    localStorage.setItem("webui:review-project", "proj-1");
    render(<ReviewQueue onOpenApproval={open} />);
    fireEvent.click(await screen.findByTestId("queue-item-apr_9"));
    expect(open).toHaveBeenCalledWith("apr_9");
    localStorage.removeItem("webui:review-project");
  });

  it("no silent fallback: an unknown backend status renders verbatim", async () => {
    vi.stubGlobal(
      "fetch",
      stubApprovals([rec({ approval_id: "apr_x", status: "SOMETHING_NEW" })]),
    );
    localStorage.setItem("webui:review-project", "proj-1");
    render(<ReviewQueue onOpenApproval={() => {}} />);
    expect(await screen.findByTestId("approval-status-SOMETHING_NEW")).toBeInTheDocument();
    localStorage.removeItem("webui:review-project");
  });
});

describe("Review Queue — Phase 27.7.6 v2 (risk-based review tasks)", () => {
  const deepItem = rec({
    approval_id: "apr_deep",
    context: { run_id: "run-deep", client_name: "高风险案例" },
  });
  const sumItem = rec({
    approval_id: "apr_sum",
    context: { run_id: "run-sum" },
    status: "APPROVED",
    decision: "approve",
  });
  const noRunItem = rec({
    approval_id: "apr_none",
    context: { client_name: "无运行上下文" },
  });
  const withRuns = [deepItem, sumItem, noRunItem];
  const CARDS = {
    "run-deep": card({
      run_id: "run-deep",
      risk_flags: [
        { type: "missing_evidence", severity: "HIGH", message: "证据链断裂", evidence_ref: "eval:E1:x" },
      ],
      review_action: { required: true, level: "DEEP_REVIEW", reasons: ["HIGH flag: missing_evidence"] },
      validation_status: "FAIL",
      automatic_validation: {
        schema_check: "PASS", trace_check: "PASS", evidence_check: "FAIL", logic_check: "PASS",
        eval_summary: { total: 6, passed: 5, failed: 1, failed_eval_ids: ["EVAL-006"] },
        failed_checks: [],
      },
    }),
    "run-sum": card({
      run_id: "run-sum",
      risk_flags: [
        { type: "no_primary_recommendation", severity: "MEDIUM", message: "无主推荐", evidence_ref: "rec:status=NO_CANDIDATES" },
      ],
      review_action: { required: true, level: "SUMMARY_REVIEW", reasons: ["MEDIUM flag"] },
      sampling: { rate: 0.1, triggered: true, seed: "x:run-sum" },
    }),
  };

  async function openQueue() {
    vi.stubGlobal("fetch", stubApprovals(withRuns, 200, CARDS));
    localStorage.setItem("webui:review-project", "proj-1");
    render(<ReviewQueue onOpenApproval={() => {}} />);
    await screen.findByTestId("queue-list");
    await screen.findByTestId("card-level-DEEP_REVIEW");
  }

  afterEach(() => localStorage.removeItem("webui:review-project"));

  it("rows show card level badge, validation chips and top issue verbatim", async () => {
    await openQueue();
    expect(screen.getByTestId("card-level-DEEP_REVIEW")).toBeInTheDocument();
    expect(screen.getByTestId("card-level-SUMMARY_REVIEW")).toBeInTheDocument();
    expect(screen.getByTestId("card-issue-apr_deep").textContent).toContain("证据链断裂");
    expect(screen.getByTestId("card-issue-apr_sum").textContent).toContain("随机抽审命中");
    // approval without run context degrades honestly
    expect(screen.getByText(/无 Review Card/)).toBeInTheDocument();
  });

  it("filter High Risk keeps only DEEP_REVIEW/HIGH items", async () => {
    await openQueue();
    fireEvent.click(screen.getByTestId("queue-filter-high"));
    expect(screen.getByTestId("queue-item-apr_deep")).toBeInTheDocument();
    expect(screen.queryByTestId("queue-item-apr_sum")).not.toBeInTheDocument();
    expect(screen.queryByTestId("queue-item-apr_none")).not.toBeInTheDocument();
  });

  it("filter Need Review uses backend status (ACTIVE approvals only)", async () => {
    await openQueue();
    fireEvent.click(screen.getByTestId("queue-filter-need"));
    expect(screen.getByTestId("queue-item-apr_deep")).toBeInTheDocument();
    expect(screen.queryByTestId("queue-item-apr_sum")).not.toBeInTheDocument(); // APPROVED
  });

  it("filter Random Audit keeps only sampling-triggered items", async () => {
    await openQueue();
    fireEvent.click(screen.getByTestId("queue-filter-audit"));
    expect(screen.queryByTestId("queue-item-apr_deep")).not.toBeInTheDocument();
    expect(screen.getByTestId("queue-item-apr_sum")).toBeInTheDocument();
  });

  it("filter with no matches shows the filtered-empty state", async () => {
    // no HIGH/DEEP items in this dataset -> High Risk filter empties the list
    vi.stubGlobal(
      "fetch",
      stubApprovals([sumItem, noRunItem], 200, CARDS),
    );
    localStorage.setItem("webui:review-project", "proj-1");
    render(<ReviewQueue onOpenApproval={() => {}} />);
    await screen.findByTestId("queue-list");
    fireEvent.click(screen.getByTestId("queue-filter-high"));
    expect(await screen.findByTestId("queue-filtered-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("queue-item-apr_sum")).not.toBeInTheDocument();
  });

  it("card fetch failure degrades to a hint, never blocks the list", async () => {
    vi.stubGlobal(
      "fetch",
      stubApprovals(withRuns, 200, CARDS, /* failCards */ true),
    );
    localStorage.setItem("webui:review-project", "proj-1");
    render(<ReviewQueue onOpenApproval={() => {}} />);
    expect(
      await screen.findByTestId("card-load-failed-apr_deep"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("queue-item-apr_sum")).toBeInTheDocument();
    expect(screen.getByText(/无 Review Card/)).toBeInTheDocument();
  });
});
