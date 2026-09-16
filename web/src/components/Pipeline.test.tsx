import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Pipeline } from "./Pipeline";
import { initRunState, runReducer } from "../state/runReducer";
import type { RuntimeEvent } from "../types/runtime";

const ORDER = [
  { id: "client-intake", skill: "client-intake", produces: "client-profile" },
  { id: "risk-analysis", skill: "risk-analysis", produces: "risk-assessment" },
  { id: "solution", skill: "solution", produces: "solution-plan" },
  { id: "report-generation", skill: "report-generation", produces: "insurance-report" },
];

function ev(type: string, stage: string | null, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: `evt_${Math.random().toString(36).slice(2, 8)}`,
    run_id: "run_x",
    timestamp: "2026-09-16T07:00:00Z",
    event_type: type as RuntimeEvent["event_type"],
    stage,
    skill: null,
    status: null,
    case_id: "c1",
    artifact_id: null,
    eval_id: null,
    repair_attempt: null,
    message: null,
    data: {},
    ...extra,
  };
}

describe("Pipeline rendering", () => {
  it("renders every stage from the runtime's stage_order (order + count verbatim)", () => {
    render(
      <Pipeline stageOrder={ORDER} stages={initRunState("r", ORDER).stages}
                currentStage={null} selected={null} onSelect={() => {}} />,
    );
    const items = screen.getAllByRole("button");
    expect(items).toHaveLength(4);
    expect(items[0]!.getAttribute("data-stage-id")).toBe("client-intake");
    expect(items[3]!.getAttribute("data-stage-id")).toBe("report-generation");
  });

  it("stage statuses come from the reducer's event mapping, never guessed", () => {
    let state = initRunState("r", ORDER);
    state = runReducer(state, { type: "events", events: [
      ev("stage_started", "client-intake"),
      ev("stage_completed", "client-intake", { status: "PASS" }),
      ev("stage_started", "risk-analysis"),
      ev("stage_failed", "solution", { status: "FAIL" }),
      ev("repair_exhausted", "solution"),
    ] })!;
    render(
      <Pipeline stageOrder={ORDER} stages={state.stages}
                currentStage="risk-analysis" selected={null} onSelect={() => {}} />,
    );
    const byId = (id: string) =>
      screen.getByRole("button", { name: new RegExp(id, "i") }).getAttribute("data-stage-status");
    // stage ids are rendered as labels — assert via data attributes instead
    const statuses = Array.from(screen.getAllByRole("button")).map(
      (b) => b.getAttribute("data-stage-status"),
    );
    expect(statuses).toEqual(["passed", "running", "needs_review", "pending"]);
    void byId;
  });

  it("shows empty state when run metadata has not loaded", () => {
    render(
      <Pipeline stageOrder={[]} stages={{}} currentStage={null} selected={null} onSelect={() => {}} />,
    );
    expect(screen.getByText(/waiting for run metadata/i)).toBeInTheDocument();
  });
});
