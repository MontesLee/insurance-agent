import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewWorkspace } from "./ReviewWorkspace";
import type { ApprovalRecord } from "../../types/approval";
import type { RuntimeEvent } from "../../types/runtime";

// Approval WITHOUT a run in its context (legacy / unlinkable case).
// The linked run arrives via the backend's read-only `review_context`.
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

// Pre-27.7.6-C stored approvals may carry run_id only in raw context
// while the (older) backend returns no review_context key at all.
const LEGACY_APPROVAL: ApprovalRecord = {
  ...APPROVAL,
  context: { ...APPROVAL.context, run_id: "run-1" },
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

interface StubOpts {
  events?: typeof EVENTS;
  failEvents?: boolean;
  failEventsOnce?: boolean;
  failArtifacts?: boolean;
  failCard?: boolean;
  noCard?: boolean;
  cardLevel?: "AUTO_PASS" | "SUMMARY_REVIEW" | "DEEP_REVIEW";
  noRun?: boolean;
  legacy?: boolean;
  emptyRec?: boolean;
}

const CARD = (level: "AUTO_PASS" | "SUMMARY_REVIEW" | "DEEP_REVIEW" = "AUTO_PASS") => ({
  schema_version: "1.0",
  card_id: "HRC-de470378",
  case_id: "bm-x",
  run_id: "run-1",
  generated_at: "2026-09-24T12:14:52Z",
  generator: "test",
  source: { state_path: "tmp/x/case_state.json", trace_path: null, state_persisted: true },
  customer_summary: { age: "35", annual_income: "80万", unresolved: [] },
  agent_summary: {
    case_status: "COMPLETED",
    objective: ["REQ-MED · 医疗 (P1_HIGH)"],
    recommendation_status: "COMPLETE",
    primary: { candidate_id: "C001", product_id: "P001", product_name: "demo-医疗险A" },
    recommendation: ["demo-医疗险A"],
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
  risk_flags: [
    {
      type: "no_primary_recommendation",
      severity: "MEDIUM",
      message: "无主推荐",
      evidence_ref: "rec:status=NO_CANDIDATES",
    },
  ],
  review_action: {
    required: level !== "AUTO_PASS",
    level,
    reasons: ["MEDIUM flag: no_primary_recommendation"],
  },
  validation_status: "PASS",
  sampling: { rate: 0.1, triggered: false, seed: "bm-x:run-1" },
});

function stubAll(opts: StubOpts = {}) {
  const seen: string[] = [];
  let eventsCalls = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    seen.push(url);
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
    if (url.endsWith("/api/runs/run-1/review-card")) {
      if (opts.failCard)
        return Response.json({ error: "boom" }, { status: 500 });
      return Response.json(CARD(opts.cardLevel));
    }
    if (url.includes("/api/projects/proj-1/supervisor"))
      return Response.json({
        project_id: "proj-1",
        supervisor: { project_id: "proj-1", status: "RUNNING", risk_level: "LOW", active_alerts: [], pending_interventions: [], last_event_id: null, last_checkpoint_id: null, updated_at: "2026-09-24T09:33:00Z" },
      });
    if (url.includes("/api/runs/run-1/events")) {
      eventsCalls += 1;
      if (opts.failEvents || (opts.failEventsOnce && eventsCalls === 1))
        return Response.json({ error: "boom" }, { status: 500 });
      return Response.json({ run_id: "run-1", count: (opts.events ?? EVENTS).length, events: opts.events ?? EVENTS });
    }
    if (url.endsWith("/api/runs/run-1/artifacts/product-recommendation"))
      return Response.json(opts.emptyRec ? {} : REC_PAYLOAD);
    if (url.endsWith("/api/runs/run-1/artifacts/knowledge-evidence"))
      return Response.json(KEV_PAYLOAD);
    if (url.includes("/api/runs/run-1/artifacts")) {
      if (opts.failArtifacts) return Response.json({ error: "boom" }, { status: 500 });
      return Response.json({
        run_id: "run-1", count: 1,
        artifacts: [{ artifact_id: "art-1", artifact_type: "product-recommendation", producer_stage: "product-recommendation" }],
      });
    }
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
  render(
    <ReviewWorkspace projectId="proj-1" approvalId="apr_1" onBack={() => {}} />,
  );
  await screen.findByTestId("workspace-approval");
  return { seen, fetchMock };
}

describe("Review Workspace — Phase 27.5-3 (read-only sections)", () => {
  it("section A renders the approval summary with verbatim status and missing fields as —", async () => {
    await openWorkspace();
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
    await openWorkspace();
    const b = await screen.findByTestId("workspace-case");
    expect(b.textContent).toContain("RUNNING");
    expect(b.textContent).toContain("LOW");
    expect(b.textContent).toContain("—"); // customer/case fields unavailable
  });
});

describe("Review Workspace — Phase 27.7.6-C (approval context auto-link)", () => {
  it("auto-loads timeline/artifacts/evidence from review_context with no manual run-id input", async () => {
    await openWorkspace();
    // No manual run-id affordances remain anywhere in the workspace.
    expect(screen.queryByTestId("workspace-run-input")).toBeNull();
    expect(screen.queryByTestId("workspace-run-load")).toBeNull();
    // The linkage indicator names the auto-linked run.
    const linked = await screen.findByTestId("run-linked");
    expect(linked.textContent).toContain("run-1");
    // Sections C/D/E load automatically — zero user interaction.
    expect(await screen.findByTestId("workspace-timeline")).toBeInTheDocument();
    expect(await screen.findByTestId("workspace-artifacts")).toBeInTheDocument();
    expect(await screen.findByTestId("workspace-evidence")).toBeInTheDocument();
  });

  it("section D surfaces review_context.artifact_ids", async () => {
    await openWorkspace();
    const arts = await screen.findByTestId("review-context-artifacts");
    expect(arts.textContent).toContain("art-9");
  });

  it("falls back to the raw approval context run_id for legacy approvals (no review_context)", async () => {
    await openWorkspace({ legacy: true });
    const linked = await screen.findByTestId("run-linked");
    expect(linked.textContent).toContain("run-1");
    expect(await screen.findByTestId("workspace-timeline")).toBeInTheDocument();
  });

  it("missing run context shows 'Run information unavailable' and issues no run requests", async () => {
    const { seen } = await openWorkspace({ noRun: true });
    const unavailable = await screen.findByTestId("run-unavailable");
    expect(unavailable).toBeInTheDocument();
    expect(await screen.findByTestId("timeline-no-run")).toHaveTextContent(
      "Run information unavailable",
    );
    expect(screen.getByTestId("artifacts-no-run")).toHaveTextContent(
      "Run information unavailable",
    );
    expect(screen.getByTestId("evidence-no-run")).toHaveTextContent(
      "Run information unavailable",
    );
    // Reviewer is never asked for a run id and no run API is called.
    expect(seen.some((u) => u.includes("/api/runs"))).toBe(false);
    expect(screen.queryByTestId("workspace-run-input")).toBeNull();
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

  it("timeline error shows a Retry affordance; retry recovers without new input", async () => {
    await openWorkspace({ failEventsOnce: true });
    expect(await screen.findByText(/加载失败/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("workspace-timeline")).toBeInTheDocument();
  });

  it("artifacts loading error shows a Retry affordance, not a silent empty", async () => {
    await openWorkspace({ failArtifacts: true });
    // Section D's list fetch failed → error block with Retry, never blank.
    const err = await screen.findByText(/加载失败/);
    expect(err).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByTestId("workspace-artifacts")).toBeNull();
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

  it("evidence chain without provenance displays 'No evidence linked'", async () => {
    await openWorkspace({ emptyRec: true });
    const evSection = await screen.findByTestId("workspace-evidence");
    await waitFor(() =>
      expect(evSection.textContent).toContain("No evidence linked"),
    );
  });
});

describe("Review Workspace — Phase 27.7.6 v2 (Review Card section)", () => {
  it("A2 renders the backend card verbatim (level, validation chips, flags)", async () => {
    await openWorkspace({ cardLevel: "SUMMARY_REVIEW" });
    const detail = await screen.findByTestId("review-card-detail");
    expect(detail.textContent).toContain("SUMMARY_REVIEW");
    expect(detail.textContent).toContain("Schema PASS");
    expect(detail.textContent).toContain("无主推荐");
    // reasons render verbatim — the reviewer sees why this level
    expect(detail.textContent).toContain(
      "MEDIUM flag: no_primary_recommendation",
    );
  });

  it("card fetch failure is loud (加载失败 + Retry), never a silent gap", async () => {
    await openWorkspace({ failCard: true });
    expect(
      await screen.findAllByText(/加载失败:/).then((els) => els.length),
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("button", { name: "Retry" }).length,
    ).toBeGreaterThan(0);
  });

  it("no run context → A2 shows the no-card placeholder", async () => {
    await openWorkspace({ noRun: true });
    expect(await screen.findByTestId("run-unavailable")).toBeInTheDocument();
    expect(
      screen.getAllByText(/无 Review Card/).length,
    ).toBeGreaterThan(0);
  });
});

describe("Review Workspace — artifact JSON copy (section D)", () => {
  function stubClipboard(writeText: (t: string) => Promise<void>) {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
  }
  afterEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
    });
  });

  it("copy button on each artifact item writes the artifact JSON", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>(async () => {});
    stubClipboard(writeText);
    await openWorkspace();
    const btn = await screen.findByTestId(
      "workspace-artifact-copy-product-recommendation",
    );
    fireEvent.click(btn);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0]?.[0]).toBe(
      JSON.stringify(REC_PAYLOAD.artifact, null, 2),
    );
    expect(
      await screen.findByTestId("workspace-artifact-copy-product-recommendation"),
    ).toHaveTextContent("已复制");
  });

  it("copy failure surfaces '复制失败' instead of silently doing nothing", async () => {
    stubClipboard(async () => {
      throw new Error("denied");
    });
    await openWorkspace();
    const btn = await screen.findByTestId(
      "workspace-artifact-copy-product-recommendation",
    );
    fireEvent.click(btn);
    await waitFor(() =>
      expect(
        screen.getByTestId("workspace-artifact-copy-product-recommendation"),
      ).toHaveTextContent("复制失败"),
    );
  });
});
