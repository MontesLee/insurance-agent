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

function stubApprovals(approvals: ApprovalRecord[], status = 200) {
  return vi.fn(async (input: RequestInfo | URL) => {
    if (String(input).includes("/api/projects/proj-1/approvals")) {
      return Response.json({ project_id: "proj-1", approvals }, { status });
    }
    return Response.json({}, { status: 404 });
  });
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
