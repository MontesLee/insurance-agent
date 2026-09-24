import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PilotDashboard, countByStatus } from "./PilotDashboard";
import type { ApprovalRecord } from "../../types/approval";

function rec(over: Partial<ApprovalRecord>): ApprovalRecord {
  return {
    approval_id: "apr_x",
    project_id: "proj-1",
    task_id: "",
    graph_revision: 1,
    request_type: "APPROVAL_FINAL_REVIEW",
    reason: "r",
    context: {},
    options: ["approve", "reject"],
    default_action: null,
    status: "WAITING_HUMAN",
    requested_by: "harness",
    created_at: new Date(Date.now() - 30 * 60000).toISOString(),
    resolved_at: null,
    resolved_by: null,
    decision: null,
    ...over,
  };
}

function stub(approvals: ApprovalRecord[] | "error") {
  return vi.fn(async (input: RequestInfo | URL) => {
    if (String(input).includes("/api/projects/proj-1/approvals")) {
      if (approvals === "error") return Response.json({}, { status: 500 });
      return Response.json({ project_id: "proj-1", approvals });
    }
    return Response.json({}, { status: 404 });
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("countByStatus — aggregation never reinterprets states", () => {
  it("groups exact statuses and preserves unknown ones separately", () => {
    const counts = countByStatus([
      rec({ status: "WAITING_HUMAN" }),
      rec({ status: "WAITING_HUMAN" }),
      rec({ status: "APPROVED", decision: "approve", resolved_at: "2026-09-24T10:00:00Z", resolved_by: "human:alice" }),
      rec({ status: "REJECTED", decision: "reject", resolved_at: "2026-09-24T09:55:00Z", resolved_by: "human:bob" }),
      rec({ status: "UNKNOWN_STATUS" }),
    ]);
    expect(counts).toContainEqual(["WAITING_HUMAN", 2]);
    expect(counts).toContainEqual(["APPROVED", 1]);
    expect(counts).toContainEqual(["REJECTED", 1]);
    expect(counts).toContainEqual(["UNKNOWN_STATUS", 1]); // kept verbatim
  });
});

describe("PilotDashboard — Phase 27.5-5 (read-only)", () => {
  it("renders overview cards with correct values and verbatim statuses", async () => {
    vi.stubGlobal(
      "fetch",
      stub([
        rec({ approval_id: "a1", status: "WAITING_HUMAN" }),
        rec({ approval_id: "a2", status: "APPROVED", decision: "approve", resolved_at: "2026-09-24T10:00:00Z", resolved_by: "human:alice" }),
        rec({ approval_id: "a3", status: "LEGAL_REVIEW_REQUIRED" }),
      ]),
    );
    localStorage.setItem("webui:review-project", "proj-1");
    render(<PilotDashboard onOpenQueue={() => {}} />);
    expect(await screen.findByTestId("dash-card-WAITING_HUMAN").then((e) => e.textContent)).toContain("1");
    expect(screen.getByTestId("dash-card-APPROVED").textContent).toContain("1");
    // unknown status gets its own verbatim card
    expect(screen.getByTestId("dash-card-LEGAL_REVIEW_REQUIRED").textContent).toContain("1");
    expect(screen.getByTestId("dash-waiting-count").textContent).toBe("1");
    // recent decisions show the resolved entry
    expect(screen.getByTestId("dash-recent").textContent).toContain("human:alice");
  });

  it("empty project shows the empty state (distinct from error)", async () => {
    vi.stubGlobal("fetch", stub([]));
    localStorage.setItem("webui:review-project", "proj-1");
    render(<PilotDashboard onOpenQueue={() => {}} />);
    expect(await screen.findByTestId("dash-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("dash-error")).not.toBeInTheDocument();
  });

  it("API error shows the failure banner with Retry — never fake zeros", async () => {
    vi.stubGlobal("fetch", stub("error"));
    localStorage.setItem("webui:review-project", "proj-1");
    render(<PilotDashboard onOpenQueue={() => {}} />);
    expect(await screen.findByTestId("dash-error")).toBeInTheDocument();
    expect(screen.getByText(/Unable to load dashboard data/)).toBeInTheDocument();
    expect(screen.queryByTestId("dash-overview")).not.toBeInTheDocument();
    expect(screen.getByTestId("dash-retry")).toBeInTheDocument();
  });

  it("quick actions navigate to the Review Queue", async () => {
    const open = vi.fn();
    vi.stubGlobal("fetch", stub([rec({ status: "WAITING_HUMAN" })]));
    localStorage.setItem("webui:review-project", "proj-1");
    render(<PilotDashboard onOpenQueue={open} />);
    await screen.findByTestId("dash-overview");
    fireEvent.click(screen.getByTestId("dash-open-queue"));
    fireEvent.click(screen.getByTestId("dash-open-pending"));
    expect(open).toHaveBeenCalledTimes(2);
  });

  it("waiting snapshot renders oldest waiting time from backend created_at", async () => {
    vi.stubGlobal(
      "fetch",
      stub([
        rec({ approval_id: "w1", status: "WAITING_HUMAN", created_at: new Date(Date.now() - 90 * 60000).toISOString() }),
        rec({ approval_id: "w2", status: "WAITING_HUMAN", created_at: new Date(Date.now() - 5 * 60000).toISOString() }),
      ]),
    );
    localStorage.setItem("webui:review-project", "proj-1");
    render(<PilotDashboard onOpenQueue={() => {}} />);
    await screen.findByTestId("dash-snapshot");
    expect(screen.getByTestId("dash-waiting-count").textContent).toBe("2");
    expect(screen.getByTestId("dash-snapshot").textContent).toContain("min"); // average waiting computed
  });
});
