import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentActivity } from "./AgentActivity";
import { initRunState, runReducer } from "../../state/runReducer";
import type { RuntimeEvent } from "../../types/runtime";

const ORDER = [
  { id: "client-intake", skill: "client-intake", produces: "client-profile" },
  { id: "requirement-analysis", skill: "requirement-analysis", produces: "requirement-analysis" },
  { id: "risk-analysis", skill: "risk-analysis", produces: "risk-assessment" },
  { id: "solution", skill: "solution", produces: "solution-plan" },
];

function ev(type: string, stage: string | null, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: `evt_${Math.random().toString(36).slice(2, 8)}`, run_id: "run_x",
    timestamp: "2026-09-16T07:00:00Z", event_type: type as RuntimeEvent["event_type"],
    stage, skill: null, status: null, case_id: "c1", artifact_id: null, eval_id: null,
    repair_attempt: null, message: null, data: {}, ...extra,
  };
}

/** Build activity-card state EXACTLY the way the app does: events → reducer. */
function build(events: RuntimeEvent[]) {
  let s = initRunState("run_x", ORDER);
  return runReducer(s, { type: "events", events })!;
}

describe("AgentActivity — derived purely from RuntimeEvents", () => {
  it("shows the work trajectory mid-run: done / running / pending stages", () => {
    const s = build([
      ev("run_started", null),
      ev("stage_started", "client-intake"),
      ev("stage_completed", "client-intake"),
      ev("stage_started", "requirement-analysis"),
      ev("stage_completed", "requirement-analysis"),
      ev("eval_passed", "requirement-analysis", { eval_id: "EVAL-002" }),
      ev("stage_started", "risk-analysis"),
    ]);
    const { container } = render(<AgentActivity state={s} caseId="bm-complete-001" streaming />);
    expect(screen.getByTestId("agent-activity").getAttribute("data-activity-status")).toBe("running");
    expect(screen.getByTestId("activity-header").textContent).toBe("Agent 正在工作");
    const statuses = Array.from(container.querySelectorAll("[data-activity-stage]")).map(
      (el) => `${el.getAttribute("data-activity-stage")}:${stageStatus(el)}`,
    );
    expect(statuses).toEqual([
      "client-intake:passed", "requirement-analysis:passed", "risk-analysis:running", "solution:pending",
    ]);
  });

  it("terminal: completed header + eval summary line", () => {
    const s = build([
      ev("run_started", null),
      ev("stage_started", "risk-analysis"),
      ev("eval_passed", "risk-analysis"),
      ev("stage_completed", "risk-analysis"),
      ev("run_completed", null, { status: "completed" }),
    ]);
    render(<AgentActivity state={s} caseId="bm-complete-001" streaming={false} />);
    expect(screen.getByTestId("activity-header").textContent).toBe("分析完成");
    expect(screen.getByTestId("activity-eval").textContent).toContain("1/1");
  });

  it("repair-exhausted trajectory is visible on the stage line", () => {
    const s = build([
      ev("stage_started", "solution"),
      ev("stage_failed", "solution"),
      ev("repair_started", "solution", { repair_attempt: 1 }),
      ev("repair_exhausted", "solution"),
    ]);
    render(<AgentActivity state={s} caseId="bm-noev-001" streaming={false} />);
    const list = screen.getByTestId("activity-stages");
    expect(list.textContent).toContain("修复 1");
    expect(screen.getByText(/产物已生成/)).toBeInTheDocument(); // artifact counter line
  });

  it("always discloses Portfolio Demo Mode + the case id", () => {
    const s = build([ev("run_started", null)]);
    const { container } = render(<AgentActivity state={s} caseId="bm-complete-001" streaming />);
    expect(container.textContent).toContain("Portfolio Demo Mode");
    expect(container.textContent).toContain("bm-complete-001");
  });
});

const GLYPHS: [string, string][] = [
  ["✓", "passed"], ["●", "running"], ["✕", "failed"], ["⚠", "needs_review"],
];
function stageStatus(el: Element): string {
  const t = el.textContent ?? "";
  return GLYPHS.find(([g]) => t.includes(g))?.[1] ?? "pending";
}
