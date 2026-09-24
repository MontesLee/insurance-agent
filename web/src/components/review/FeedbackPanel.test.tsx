import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FeedbackPanel } from "./FeedbackPanel";
import {
  FEEDBACK_CATEGORIES,
  feedbackClient,
  type FeedbackRecord,
} from "../../api/feedbackClient";
import type { ApprovalRecord } from "../../types/approval";

function approval(over: Partial<ApprovalRecord> = {}): ApprovalRecord {
  return {
    approval_id: "apr_1",
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
    created_at: "2026-09-24T09:30:00Z",
    resolved_at: null,
    resolved_by: null,
    decision: null,
    ...over,
  };
}

const DECIDED = approval({
  status: "REJECTED",
  decision: "reject",
  resolved_at: "2026-09-24T10:00:00Z",
  resolved_by: "human:alice",
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("Feedback Panel — Phase 27.7 (capture only)", () => {
  it("renders the closed category set; submit disabled until category+description", async () => {
    render(<FeedbackPanel approval={DECIDED} />);
    for (const c of FEEDBACK_CATEGORIES) {
      expect(screen.getByTestId(`feedback-cat-${c}`)).toBeInTheDocument();
    }
    const submit = screen.getByTestId("feedback-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true); // nothing filled
    fireEvent.click(screen.getByTestId("feedback-cat-REASONING"));
    expect(submit.disabled).toBe(true); // description still empty
    fireEvent.change(screen.getByTestId("feedback-description"), {
      target: { value: "覆盖推荐忽视了收入替代需求" },
    });
    expect(submit.disabled).toBe(false);
    // empty state renders after the (async) store read
    expect(await screen.findByTestId("feedback-empty")).toBeInTheDocument();
  });

  it("valid submission persists a record and re-renders the list verbatim (no optimistic update)", async () => {
    render(<FeedbackPanel approval={DECIDED} />);
    fireEvent.click(screen.getByTestId("feedback-cat-EVIDENCE_ISSUE"));
    fireEvent.change(screen.getByTestId("feedback-description"), {
      target: { value: "知识来源过时,条款已更新" },
    });
    fireEvent.change(screen.getByTestId("feedback-refs"), {
      target: { value: "01_medical_insurance_002, REQ-MED" },
    });
    fireEvent.change(screen.getByTestId("feedback-expected"), {
      target: { value: "应引用最新条款并标注版本" },
    });
    fireEvent.click(screen.getByTestId("feedback-submit"));
    // the record appears only AFTER the store round-trip + reload
    const list = await screen.findByTestId("feedback-list");
    await waitFor(() =>
      expect(list.querySelectorAll('[data-testid^="feedback-record-"]').length).toBe(1),
    );
    const rec = list.querySelector('[data-testid^="feedback-record-"]')!;
    expect(rec.textContent).toContain("EVIDENCE_ISSUE"); // category verbatim
    expect(rec.textContent).toContain("知识来源过时,条款已更新");
    expect(rec.textContent).toContain("01_medical_insurance_002, REQ-MED");
    expect(rec.textContent).toContain("应引用最新条款并标注版本");
    expect(rec.textContent).toContain("captured");
    expect(rec.textContent).toContain("apr_1#reject"); // decision anchor
    // form cleared after success
    expect((screen.getByTestId("feedback-description") as HTMLTextAreaElement).value).toBe("");
  });

  it("failure keeps user input and offers retry", async () => {
    vi.spyOn(feedbackClient, "createFeedback").mockRejectedValue(
      new Error("store unavailable"),
    );
    render(<FeedbackPanel approval={DECIDED} />);
    fireEvent.click(screen.getByTestId("feedback-cat-KNOWLEDGE_GAP"));
    fireEvent.change(screen.getByTestId("feedback-description"), {
      target: { value: "重疾条款知识缺失" },
    });
    fireEvent.click(screen.getByTestId("feedback-submit"));
    const err = await screen.findByTestId("feedback-error");
    expect(err.textContent).toContain("Failed to submit feedback");
    expect(screen.getByTestId("feedback-retry")).toBeInTheDocument();
    // input preserved
    expect((screen.getByTestId("feedback-description") as HTMLTextAreaElement).value).toBe(
      "重疾条款知识缺失",
    );
    expect((screen.getByTestId("feedback-cat-KNOWLEDGE_GAP").className)).toContain(
      "bg-slate-800",
    );
  });

  it("capture is gated on a Decision (undecided approval shows the gate, no form)", () => {
    render(<FeedbackPanel approval={approval()} />); // WAITING_HUMAN
    expect(screen.getByTestId("feedback-gate")).toBeInTheDocument();
    expect(screen.queryByTestId("feedback-submit")).not.toBeInTheDocument();
  });

  it("SAFETY: feedback submission performs NO HTTP calls and never mutates the approval", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    render(<FeedbackPanel approval={DECIDED} />);
    fireEvent.click(screen.getByTestId("feedback-cat-UX_ISSUE"));
    fireEvent.change(screen.getByTestId("feedback-description"), {
      target: { value: "报告缺少免责说明" },
    });
    fireEvent.click(screen.getByTestId("feedback-submit"));
    await waitFor(() =>
      expect(
        screen.getByTestId("feedback-list").querySelectorAll(
          '[data-testid^="feedback-record-"]',
        ).length,
      ).toBe(1),
    );
    // zero network traffic: no approval state change, no runtime trigger,
    // no artifact/skill mutation — feedback is inert local evidence
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(DECIDED.status).toBe("REJECTED");
    expect(DECIDED.decision).toBe("reject");
    // record itself is inert: status stays "captured"
    const stored = JSON.parse(
      localStorage.getItem("webui:feedback:v1") ?? "[]",
    ) as FeedbackRecord[];
    expect(stored).toHaveLength(1);
    expect(stored[0]?.status).toBe("captured");
    expect(stored[0]?.provenance).toBe("governance-ui");
  });
});
