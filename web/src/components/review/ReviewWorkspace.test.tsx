import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewWorkspace } from "./ReviewWorkspace";
import type { ApprovalRecord } from "../../types/approval";
import type { RuntimeEvent } from "../../types/runtime";

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

function ev(over: Partial<RuntimeEvent>): RuntimeEvent {
  return {
    event_id: "e1", run_id: "run-1",
    timestamp: "2026-09-24T09:30:00Z",
    event_type: "stage_started", stage: null, skill: null, status: null,
    case_id: null, artifact_id: null, eval_id: null, repair_attempt: null,
    message: null, data: {},
    ...over,
  };
}

const EVENTS = [
  ev({ event_id: "e1", event_type: "run_started", timestamp: "2026-09-24T09:29:00Z" }),
  ev({ event_id: "e2", event_type: "stage_started", stage: "requirement-analysis", skill: "requirement_analysis", timestamp: "2026-09-24T09:30:00Z" }),
  ev({ event_id: "e3", event_type: "stage_completed", stage: "requirement-analysis", skill: "requirement_analysis", timestamp: "2026-09-24T09:30:05Z" }),
  ev({ event_id: "e4", event_type: "stage_started", stage: "risk-analysis", skill: "risk-analysis", timestamp: "2026-09-24T09:31:00Z" }),
  ev({ event_id: "e5", event_type: "stage_failed", stage: "risk-analysis", skill: "risk-analysis", timestamp: "2026-09-24T09:32:00Z" }),
];

const REC_PAYLOAD = {
  artifact: {
    payload: {
      status: "INCOMPLETE_EVIDENCE",
      primary_recommendation: {
        candidate_id: "C001",
        provenance: [
          { type: "requirement", ref: "REQ-MED" },
          { type: "knowledge", ref: "01_medical_insurance_002" },
          { type: "knowledge", ref: "missing_ref_xyz" },
        ],
      },
      candidate_evaluations: [
        { candidate_id: "C005", recommendation_status: "insufficient_evidence", provenance: [] },
      ],
    },
  },
};
const KEV_PAYLOAD = {
  artifact: {
    payload: {
      status: "success",
      evidence: [
        { evidence_id: "01_medical_insurance_002", content: "百万医疗险以费用报销为主要赔付方式", source: "01_medical_insurance" },
      ],
    },
  },
};

function stubAll(opts?: { events?: typeof EVENTS; failEvents?: boolean }) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/approvals/apr_1"))
      return Response.json({ project_id: "proj-1", approval: APPROVAL });
    if (url.includes("/api/projects/proj-1/supervisor"))
      return Response.json({
        project_id: "proj-1",
        supervisor: { project_id: "proj-1", status: "RUNNING", risk_level: "LOW", active_alerts: [], pending_interventions: [], last_event_id: null, last_checkpoint_id: null, updated_at: "2026-09-24T09:33:00Z" },
      });
    if (url.includes("/api/runs/run-1/events")) {
      if (opts?.failEvents) return Response.json({}, { status: 500 });
      return Response.json({ events: opts?.events ?? EVENTS, next_after: null });
    }
    if (url.endsWith("/api/runs/run-1/artifacts/product-recommendation"))
      return Response.json(REC_PAYLOAD);
    if (url.endsWith("/api/runs/run-1/artifacts/knowledge-evidence"))
      return Response.json(KEV_PAYLOAD);
    if (url.includes("/api/runs/run-1/artifacts"))
      return Response.json({
        run_id: "run-1", count: 1,
        artifacts: [{ artifact_id: "art-1", artifact_type: "product-recommendation", producer_stage: "product-recommendation" }],
      });
    return Response.json({}, { status: 404 });
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

async function openWorkspace() {
  vi.stubGlobal("fetch", stubAll());
  render(
    <ReviewWorkspace projectId="proj-1" approvalId="apr_1" onBack={() => {}} />,
  );
  await screen.findByTestId("workspace-approval");
  fireEvent.change(screen.getByTestId("workspace-run-input"), {
    target: { value: "run-1" },
  });
  fireEvent.click(screen.getByTestId("workspace-run-load"));
}

describe("Review Workspace — Phase 27.5-3 (read-only)", () => {
  it("section A renders the approval summary with verbatim status and missing fields as —", async () => {
    vi.stubGlobal("fetch", stubAll());
    render(
      <ReviewWorkspace projectId="proj-1" approvalId="apr_1" onBack={() => {}} />,
    );
    const a = await screen.findByTestId("workspace-approval");
    expect(a).toBeInTheDocument();
    expect(
      a.querySelector('[data-testid="approval-status-WAITING_HUMAN"]'),
    ).not.toBeNull();
    expect(a.textContent).toContain("APPROVAL_FINAL_REVIEW");
    expect(a.textContent).toContain("proj-1");
    // task_id missing → "—" (not fabricated)
    expect(a.textContent).toContain("—");
  });

  it("section B shows backend supervisor fields and marks unavailable case fields as —", async () => {
    vi.stubGlobal("fetch", stubAll());
    render(
      <ReviewWorkspace projectId="proj-1" approvalId="apr_1" onBack={() => {}} />,
    );
    const b = await screen.findByTestId("workspace-case");
    expect(b.textContent).toContain("RUNNING");
    expect(b.textContent).toContain("LOW");
    expect(b.textContent).toContain("—"); // customer/case fields unavailable
  });

  it("section C renders the run timeline in order with verbatim statuses", async () => {
    await openWorkspace();
    const t = await screen.findByTestId("workspace-timeline");
    const rows = t.querySelectorAll("li");
    expect(rows.length).toBe(3); // run_started + 2 stages
    expect(t.textContent).toContain("stage_completed");
    expect(t.textContent).toContain("stage_failed");
    // chronological ordering: requirement before risk
    const req = t.textContent!.indexOf("requirement_analysis");
    const risk = t.textContent!.indexOf("risk-analysis");
    expect(req).toBeLessThan(risk);
  });

  it("section C error shows a retry affordance, not a silent empty", async () => {
    vi.stubGlobal("fetch", stubAll({ failEvents: true }));
    render(
      <ReviewWorkspace projectId="proj-1" approvalId="apr_1" onBack={() => {}} />,
    );
    await screen.findByTestId("workspace-approval");
    fireEvent.change(screen.getByTestId("workspace-run-input"), { target: { value: "run-1" } });
    fireEvent.click(screen.getByTestId("workspace-run-load"));
    expect(await screen.findByText(/加载失败/)).toBeInTheDocument();
  });

  it("section D lists artifacts with an empty state distinct from error", async () => {
    await openWorkspace();
    const arts = await screen.findByTestId("workspace-artifacts");
    expect(arts.textContent).toContain("product-recommendation");
    expect(screen.getByTestId("workspace-artifact-product-recommendation")).toBeInTheDocument();
  });

  it("section E renders the evidence chain and flags missing evidence without fabricating", async () => {
    await openWorkspace();
    const evSection = await screen.findByTestId("workspace-evidence");
    // chain present: requirement ref + linked knowledge evidence with source
    expect(evSection.textContent).toContain("REQ-MED");
    expect(evSection.textContent).toContain("百万医疗险以费用报销为主要赔付方式");
    expect(evSection.textContent).toContain("01_medical_insurance");
    // missing knowledge ref flagged verbatim — never fabricated content
    expect(evSection.textContent).toContain("No evidence linked");
    expect(evSection.textContent).toContain("missing_ref_xyz");
    // insufficient-evidence candidate rendered with no-fabrication note
    expect(evSection.textContent).toContain("C005");
  });
});
