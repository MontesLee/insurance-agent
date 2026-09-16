import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Conversation } from "./Conversation";
import { initRunState, runReducer } from "../state/runReducer";
import type { RuntimeEvent } from "../types/runtime";

/** Regression: the report block must fetch by ARTIFACT TYPE (insurance-report),
 *  not by stage id (report-generation) — wiring these up 1:1 404s forever. */
describe("Conversation report block", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("fetches /artifacts/insurance-report once the report stage passed", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        urls.push(url);
        if (url.includes("/artifacts/insurance-report")) {
          return Response.json({
            artifact_id: "ART-009",
            artifact: { payload: { status: "success", rendered_report: "# 客户保险需求分析报告\n\n- **年龄**：35" } },
          });
        }
        throw new Error("unexpected fetch " + url);
      }),
    );

    const order = [{ id: "report-generation", skill: "report-generation", produces: "insurance-report" }];
    let state = initRunState("run_r", order);
    state = runReducer(state, {
      type: "events",
      events: [
        ev("stage_started", "report-generation"),
        ev("stage_completed", "report-generation"),
        ev("run_completed", null, { status: "completed" }),
      ],
    })!;

    render(
      <Conversation state={state} reportStageId="report-generation" reportArtifactType="insurance-report" />,
    );

    await waitFor(() =>
      expect(screen.getByTestId("report")).toHaveTextContent("客户保险需求分析报告"),
    );
    expect(urls[0]).toContain("/api/runs/run_r/artifacts/insurance-report");
    expect(urls[0]).not.toContain("report-generation");
    expect(screen.getByText("年龄")).toBeInTheDocument(); // markdown rendered, not raw
    expect(screen.queryByText(/could not be loaded/i)).toBeNull();
  });
});

function ev(type: string, stage: string | null, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: `evt_${Math.random().toString(36).slice(2, 8)}`,
    run_id: "run_r",
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
