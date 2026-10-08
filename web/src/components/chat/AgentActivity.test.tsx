import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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

function itemTexts(): string[] {
  return Array.from(document.querySelectorAll("[data-activity-item]")).map(
    (el) => el.textContent ?? "",
  );
}

describe("AgentActivity — renders the Consumer Activity DTO (28.E-3)", () => {
  it("planning run: stage milestones appear in real order, from events only", () => {
    const s = build([
      ev("run_started", null),
      ev("intent_classified", null),
      ev("stage_started", "client-intake"),
      ev("stage_completed", "client-intake"),
      ev("stage_started", "risk-analysis"),
      ev("eval_passed", "risk-analysis", { eval_id: "EVAL-002" }),
    ]);
    const { container } = render(<AgentActivity state={s} streaming />);
    expect(screen.getByTestId("agent-activity").getAttribute("data-activity-status")).toBe("running");
    expect(screen.getByTestId("activity-header").textContent).toBe("正在处理你的请求");
    const texts = itemTexts();
    expect(texts).toEqual([
      "✓已理解你的问题",
      "●正在为你分析进行中", // routing done → work underway (mid-run)
      "✓已了解家庭基本情况",
      "●正在识别家庭风险进行中", // active item carries the live badge
      // 28.K.13: the REAL eval_passed event now folds onto the verify
      // activity — one more event-backed row (was hidden before)
      "✓已完成信息核实",
      // 28.K.25: ○ upcoming workflow stages (real stage_order, shown
      // only after execution started on the spine) — requirement-analysis
      // and solution are pending in this fixture
      "○正在分析保障需求",
      "○正在设计保障方案",
    ]);
    expect(screen.getByTestId("activity-eval").textContent).toContain("1/1");
    expect(container.textContent).not.toContain("solution"); // unstarted stage NOT templated in
  });

  it("QA turn: honest milestones only — no planning-stage template, no fake materials", () => {
    const s = build([
      ev("run_started", null),
      ev("intent_classified", null, { data: { intent: "insurance_qa" } }),
      ev("agent_step_started", null),
      ev("qa_answered", null, { data: { grounding_status: "refused" } }),
      ev("run_completed", null, { status: "completed" }),
    ]);
    const { container } = render(<AgentActivity state={s} streaming={false} />);
    expect(itemTexts()).toEqual(["✓已理解你的问题", "✓已完成分析"]);
    expect(container.textContent).not.toContain("客户建档"); // no planning template
    expect(container.textContent).not.toContain("核对相关资料"); // no fabricated retrieval
    expect(screen.getByTestId("activity-header").textContent).toBe("已完成");
  });

  it("clarification turn shows the waiting milestone", () => {
    const s = build([
      ev("run_started", null),
      ev("intent_classified", null),
      ev("agent_step_started", null),
      ev("agent_decision", null, { data: { action: "ask_user" } }),
      ev("run_completed", null, { status: "waiting" }),
    ]);
    render(<AgentActivity state={s} streaming={false} />);
    expect(itemTexts().at(-1)).toContain("需要你补充一些信息");
    expect(screen.getByTestId("activity-header").textContent).toBe("需要你补充信息");
  });

  it("NEVER renders internals: ids, demo metadata, event names, counters (T4/T5/T6/T11)", () => {
    const s = build([
      ev("run_started", null),
      ev("totally_unknown_event_xyz" as RuntimeEvent["event_type"], null),
      ev("stage_started", "UNKNOWN_INTERNAL_STAGE_XYZ" as string),
      ev("intent_classified", null, {
        data: { intent: "insurance_qa", agent: "insurance-qa-agent", decision_source: "rule" },
      }),
      ev("tool_started", null, { data: { tool: "WeKnoraInternalTool", provider: "glm" } }),
      ev("run_completed", null, { status: "completed" }),
    ]);
    const { container } = render(<AgentActivity state={s} streaming={false} />);
    const text = container.textContent ?? "";
    for (const bad of [
      "Portfolio Demo Mode", "bm-", "caseId", "events", "run_started",
      "totally_unknown_event_xyz", "UNKNOWN_INTERNAL_STAGE_XYZ", "run_x",
      "insurance_qa", "insurance-qa-agent", "decision_source", "WeKnoraInternalTool",
      "provider", "glm", "router", "registry",
    ]) {
      expect(text.includes(bad), `consumer activity must not contain ${bad}`).toBe(false);
    }
    // DOM attributes stay semantic too (no internal keys/stages)
    const attrs = Array.from(container.querySelectorAll("[data-activity-item]")).flatMap((el) =>
      [el.getAttribute("data-status"), el.getAttribute("data-activity-item")],
    );
    expect(attrs.join(" ")).not.toMatch(/run_|client-intake|insurance|WeKnora/);
  });

  it("the activity card hosts NO stream text at all (28.K.20 moved it to the message bubble) — reasoning can never leak here", () => {
    const s = build([ev("run_started", null)]);
    const withStream = {
      ...s,
      stream: { text: "chain-of-thought leak candidate", kind: "reasoning" as const },
    };
    const { container } = render(<AgentActivity state={withStream} streaming />);
    expect(container.textContent).not.toContain("chain-of-thought leak candidate");
    expect(container.querySelector("[data-testid='stream-panel']")).toBeNull();
    const withContent = { ...s, stream: { text: "answer text", kind: "content" as const } };
    const c2 = render(<AgentActivity state={withContent} streaming />).container;
    expect(c2.querySelector("[data-testid='stream-message']")).toBeNull();
  });

  it("no fabricated progress: a bare run shows understanding only", () => {
    const s = build([ev("run_started", null)]);
    render(<AgentActivity state={s} streaming />);
    expect(itemTexts()).toEqual(["●正在理解你的问题进行中"]);
  });
});

describe("28.K.13 — waiting heartbeat (UI liveness only, no fabricated progress)", () => {
  it("appears after the silence threshold while live, clears on new events", async () => {
    vi.useFakeTimers();
    try {
      const base = [
        ev("run_started", null),
        ev("intent_classified", null),
      ];
      const { rerender } = render(<AgentActivity state={build(base)} streaming={false} />);
      expect(screen.queryByTestId("activity-heartbeat")).toBeNull();
      act(() => { vi.advanceTimersByTime(13_000); });
      const hb = screen.getByTestId("activity-heartbeat");
      expect(hb.textContent).toContain("这一步需要一些时间，请稍候");
      // a REAL event arriving clears the waiting line
      rerender(<AgentActivity state={build([...base, ev("agent_step_started", null)])} streaming={false} />);
      expect(screen.queryByTestId("activity-heartbeat")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("never shows on terminal states (completed/needs_review/failed)", () => {
    vi.useFakeTimers();
    try {
      const done = build([
        ev("run_started", null),
        ev("intent_classified", null),
        ev("run_completed", null, { status: "completed" }),
      ]);
      render(<AgentActivity state={done} streaming={false} />);
      act(() => { vi.advanceTimersByTime(30_000); });
      expect(screen.queryByTestId("activity-heartbeat")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("heartbeat copy claims no backend operation (deterministic string)", () => {
    vi.useFakeTimers();
    try {
      render(<AgentActivity state={build([ev("run_started", null)])} streaming={false} />);
      act(() => { vi.advanceTimersByTime(13_000); });
      expect(screen.getByTestId("activity-heartbeat").textContent)
        .toBe("这一步需要一些时间，请稍候");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("28.K.17 — live LLM delta activity (arrival-driven, never fabricated)", () => {
  beforeAll(() => {
    // jsdom lacks Element.scrollTo (StreamPanel autoscroll)
    Element.prototype.scrollTo = () => {};
  });
  function delta(kind: "reasoning" | "content", text: string): RuntimeEvent {
    return ev("agent_stream_delta", null, { data: { kind, text } });
  }
  const BASE = () => [ev("run_started", null), ev("intent_classified", null)];

  it("T1: a delta activates the live generation row with exact safe copy", () => {
    render(<AgentActivity state={build([...BASE(), delta("reasoning", "内部推理X")])} streaming={false} />);
    expect(screen.getByTestId("activity-generation").textContent).toBe("正在生成回答");
  });

  it("T2: fresh delta suppresses the heartbeat (Case A beats Case C)", () => {
    vi.useFakeTimers();
    try {
      render(<AgentActivity state={build([...BASE(), delta("content", "答")])} streaming={false} />);
      act(() => { vi.advanceTimersByTime(1_500); });
      expect(screen.getByTestId("activity-generation")).toBeTruthy();
      expect(screen.queryByTestId("activity-heartbeat")).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it("T3: delta activity expires after 2s; true silence >=12s shows the K.13 heartbeat", () => {
    vi.useFakeTimers();
    try {
      render(<AgentActivity state={build([...BASE(), delta("content", "答")])} streaming={false} />);
      act(() => { vi.advanceTimersByTime(3_000); });
      expect(screen.queryByTestId("activity-generation")).toBeNull();
      act(() => { vi.advanceTimersByTime(10_000); }); // 13s total, no events
      expect(screen.getByTestId("activity-heartbeat").textContent)
        .toContain("这一步需要一些时间，请稍候");
      expect(screen.queryByTestId("activity-generation")).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it("T4: a new normal event keeps existing activity and resets silence (Case B)", () => {
    vi.useFakeTimers();
    try {
      const { rerender } = render(<AgentActivity state={build(BASE())} streaming={false} />);
      act(() => { vi.advanceTimersByTime(11_000); });
      rerender(<AgentActivity state={build([...BASE(), ev("agent_step_started", null)])} streaming={false} />);
      act(() => { vi.advanceTimersByTime(3_000); });
      expect(screen.queryByTestId("activity-heartbeat")).toBeNull();
      expect(screen.queryByTestId("activity-generation")).toBeNull();
      expect(itemTexts().length).toBeGreaterThan(0);
    } finally { vi.useRealTimers(); }
  });

  it("T5: terminal states show neither generation row nor heartbeat", () => {
    for (const status of ["completed", "failed", "needs_review", "waiting"] as const) {
      const s = build([...BASE(), delta("content", "答"), ev("run_completed", null, { status })]);
      const { unmount } = render(<AgentActivity state={s} streaming={false} />);
      expect(screen.queryByTestId("activity-generation")).toBeNull();
      expect(screen.queryByTestId("activity-heartbeat")).toBeNull();
      unmount();
    }
  });

  it("T6 (28.K.28): a reasoning delta keeps the activity LIST free of stream text — the text goes to the STEP BOX", () => {
    render(<AgentActivity state={build([...BASE(), delta("reasoning", "内部推理CONTENT9")])} streaming={false} />);
    expect(screen.getByTestId("activity-generation").textContent).toBe("正在生成回答");
    // the activity row list carries no stream text at all ...
    const activityText = Array.from(document.querySelectorAll("[data-activity-item]"))
      .map((el) => el.textContent).join(" ");
    expect(activityText).not.toContain("内部推理CONTENT9");
    // ... while the step box (28.K.28) now shows it, muted + chipped
    expect(screen.getByTestId("step-output-reasoning").textContent).toBe("内部推理CONTENT9");
    expect(screen.queryByTestId("stream-panel")).toBeNull();
  });

  it("T7/T8 (28.K.28): the live row is activity-only; stream text lives in the step box, never the card's stream panel", () => {
    render(<AgentActivity state={build([
      ...BASE(), delta("reasoning", "思考R"), delta("content", "可见答案"),
    ])} streaming={false} />);
    expect(screen.getByTestId("activity-generation").textContent).toBe("正在生成回答");
    expect(screen.getByTestId("step-output-reasoning").textContent).toBe("思考R");
    expect(screen.getByTestId("step-output-content").textContent).toBe("可见答案");
    expect(screen.queryByTestId("stream-message")).toBeNull(); // not in the card
  });
});
