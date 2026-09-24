import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DecisionPanel } from "./DecisionPanel";
import type { ApprovalRecord } from "../../types/approval";

function rec(over: Partial<ApprovalRecord> = {}): ApprovalRecord {
  return {
    approval_id: "apr_1",
    project_id: "proj-1",
    task_id: "",
    graph_revision: 1,
    request_type: "APPROVAL_FINAL_REVIEW",
    reason: "final deliverable requires human review",
    context: {},
    options: ["approve", "reject"],
    default_action: null,
    status: "WAITING_HUMAN",
    requested_by: "harness",
    created_at: "2026-09-24T09:30:00Z",
    resolved_at: null,
    resolved_by: null,
    decision: null,
    ...over,
  };
}

const calls: string[] = [];

function stubMutate(opts?: { fail?: boolean }) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/approve") || url.endsWith("/reject")) {
      calls.push(`${init?.method} ${url.slice(-20)} ${String(init?.body ?? "")}`);
      if (opts?.fail) return Response.json({ error: "boom" }, { status: 500 });
      return Response.json(rec({
        status: url.endsWith("/approve") ? "APPROVED" : "REJECTED",
        decision: url.endsWith("/approve") ? "approve" : "reject",
        resolved_at: "2026-09-24T10:00:00Z",
        resolved_by: "human:alice",
      }));
    }
    return Response.json({}, { status: 404 });
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  calls.length = 0;
});

describe("Decision Panel — Phase 27.5-4", () => {
  it("renders the panel with verbatim current status and both actions", () => {
    vi.stubGlobal("fetch", stubMutate());
    render(<DecisionPanel approval={rec()} onDecided={() => {}} />);
    const panel = screen.getByTestId("decision-panel");
    expect(screen.getByTestId("approval-status-WAITING_HUMAN")).toBeInTheDocument();
    expect(screen.getByTestId("decision-approve")).toBeInTheDocument();
    expect(screen.getByTestId("decision-reject")).toBeInTheDocument();
    expect(panel.textContent).toContain("—"); // reviewer identity unknown
  });

  it("approve flow: confirmation required, API called, success rendered (no optimistic update)", async () => {
    const onDecided = vi.fn();
    vi.stubGlobal("fetch", stubMutate());
    render(<DecisionPanel approval={rec()} onDecided={onDecided} />);
    fireEvent.click(screen.getByTestId("decision-approve"));
    // confirmation gate BEFORE any API call
    expect(screen.getByTestId("decision-confirm")).toBeInTheDocument();
    expect(calls.length).toBe(0);
    fireEvent.click(screen.getByTestId("confirm-yes"));
    await screen.findByTestId("decision-success");
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("/approve");
    expect(onDecided).toHaveBeenCalled(); // re-read backend record
  });

  it("reject validation: empty comment blocks submission; a valid comment submits", async () => {
    vi.stubGlobal("fetch", stubMutate());
    render(<DecisionPanel approval={rec()} onDecided={() => {}} />);
    const reject = screen.getByTestId("decision-reject") as HTMLButtonElement;
    expect(reject.disabled).toBe(true); // empty comment → disabled
    fireEvent.change(screen.getByTestId("decision-comment"), {
      target: { value: "Evidence insufficient for recommendation." },
    });
    expect(reject.disabled).toBe(false);
    fireEvent.click(reject);
    await screen.findByTestId("decision-success");
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("/reject");
    expect(calls[0]).toContain("Evidence insufficient");
  });

  it("API error: failure shown with retry, no fake status update", async () => {
    vi.stubGlobal("fetch", stubMutate({ fail: true }));
    render(<DecisionPanel approval={rec()} onDecided={() => {}} />);
    fireEvent.change(screen.getByTestId("decision-comment"), {
      target: { value: "理由" },
    });
    fireEvent.click(screen.getByTestId("decision-reject"));
    const err = await screen.findByTestId("decision-error");
    expect(err.textContent).toContain("决定提交失败");
    expect(screen.getByTestId("decision-retry")).toBeInTheDocument();
    // status badge still shows the backend truth — never flipped locally
    expect(screen.getByTestId("approval-status-WAITING_HUMAN")).toBeInTheDocument();
  });

  it("already-decided approval shows the immutable decision record with disabled actions", () => {
    vi.stubGlobal("fetch", stubMutate());
    render(
      <DecisionPanel
        approval={rec({
          status: "APPROVED",
          decision: "approve",
          resolved_at: "2026-09-24T10:00:00Z",
          resolved_by: "human:alice",
        })}
        onDecided={() => {}}
      />,
    );
    const history = screen.getByTestId("decision-history");
    expect(history.textContent).toContain("APPROVED");
    expect(history.textContent).toContain("human:alice");
    expect(history.textContent).toContain("2026-09-24 10:00");
    expect(screen.queryByTestId("decision-approve")).not.toBeInTheDocument();
    expect(screen.queryByTestId("decision-reject")).not.toBeInTheDocument();
  });

  it("request_fix (27.7.6 v2): comment required, confirm-gated, recorded as REJECT with REQUEST_FIX prefix", async () => {
    vi.stubGlobal("fetch", stubMutate());
    render(<DecisionPanel approval={rec()} onDecided={() => {}} />);
    const fix = screen.getByTestId("decision-request-fix") as HTMLButtonElement;
    expect(fix.disabled).toBe(true); // 修正意见必填
    fireEvent.change(screen.getByTestId("decision-comment"), {
      target: { value: "推荐理由缺少家庭责任分析,请补充。" },
    });
    expect(fix.disabled).toBe(false);
    fireEvent.click(fix);
    // confirm gate BEFORE any API call, with the REJECT-recording caveat shown
    const confirm = screen.getByTestId("decision-confirm");
    expect(confirm.textContent).toContain("REJECT 记录");
    expect(calls.length).toBe(0);
    fireEvent.click(screen.getByTestId("confirm-yes"));
    await screen.findByTestId("decision-success");
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("/reject"); // existing endpoint, no state-machine change
    expect(calls[0]).toContain("REQUEST_FIX: 推荐理由缺少家庭责任分析");
  });

  it("unknown backend status renders verbatim — no mapping", () => {
    vi.stubGlobal("fetch", stubMutate());
    render(<DecisionPanel approval={rec({ status: "LEGAL_REVIEW_REQUIRED" })} onDecided={() => {}} />);
    expect(screen.getByTestId("approval-status-LEGAL_REVIEW_REQUIRED")).toBeInTheDocument();
  });

  it("waitFor sanity: submitting state disables buttons while the API is in flight", async () => {
    let release: (() => void) | null = null;
    const gate = new Promise<void>((r) => (release = r));
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        await gate;
        return Response.json(rec({ status: "APPROVED", decision: "approve" }));
      }),
    );
    render(<DecisionPanel approval={rec()} onDecided={() => {}} />);
    fireEvent.click(screen.getByTestId("decision-approve"));
    fireEvent.click(screen.getByTestId("confirm-yes"));
    await waitFor(() =>
      expect((screen.getByTestId("decision-approve") as HTMLButtonElement).disabled).toBe(true),
    );
    release!();
    await screen.findByTestId("decision-success");
  });
});
