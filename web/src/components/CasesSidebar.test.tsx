import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CasesSidebar } from "./CasesSidebar";
import type { CaseInfo, Run } from "../types/runtime";

const CASES: CaseInfo[] = [
  { id: "bm-complete-001", category: "complete", desc: "基准客户", kb: null },
  { id: "bm-noev-001", category: "insufficient_evidence", desc: "空知识库", kb: "empty" },
];

const RUN: Run = {
  run_id: "run_active", case_id: "bm-complete-001", status: "running",
  started_at: null, completed_at: null, current_stage: "solution", event_count: 3,
  result_status: null, reasons: [], stage_order: [],
};

function stubCases() {
  return vi.fn(async (input: RequestInfo | URL) => {
    if (String(input).endsWith("/api/cases")) {
      return Response.json({ cases: CASES });
    }
    return Response.json({}, { status: 404 });
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("Cases sidebar — 409 case_already_running handling", () => {
  it("shows the conflict banner with the active run id and an 'open' action", async () => {
    vi.stubGlobal("fetch", stubCases());
    const onSelectRun = vi.fn();
    render(
      <CasesSidebar runs={[]} onSelectRun={onSelectRun} onStartRun={() => {}}
        conflict={{ caseId: "bm-complete-001", runId: "run_active" }} />,
    );
    const banner = await screen.findByTestId("conflict-banner");
    expect(banner).toHaveTextContent(/already running/i);
    expect(banner).toHaveTextContent(/run_active/);

    fireEvent.click(screen.getByRole("button", { name: /open active run/i }));
    expect(onSelectRun).toHaveBeenCalledWith("run_active");
  });

  it("no conflict -> no banner; case cards offer Run and the latest run", async () => {
    vi.stubGlobal("fetch", stubCases());
    const onStartRun = vi.fn();
    const onSelectRun = vi.fn();
    const { container } = render(
      <CasesSidebar runs={[RUN]} onSelectRun={onSelectRun} onStartRun={onStartRun} conflict={null} />,
    );
    await waitFor(() => expect(screen.getByText("基准客户")).toBeInTheDocument());
    expect(screen.queryByTestId("conflict-banner")).toBeNull();

    const runBtn = container.querySelector("[data-start-case='bm-complete-001']");
    expect(runBtn).not.toBeNull();
    fireEvent.click(runBtn!);
    expect(onStartRun).toHaveBeenCalledWith("bm-complete-001");

    fireEvent.click(screen.getByTestId("open-latest-run"));
    expect(onSelectRun).toHaveBeenCalledWith("run_active");
  });
});
