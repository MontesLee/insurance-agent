/**
 * Step streaming output boxes — component tests.
 *
 * Fixed-height class, active cursor, sanitizer, and (28.K.28) segmented
 * reasoning/content rendering. 28.K.28 supersedes E-2: reasoning is now
 * displayed, but only inside its own de-emphasized segment.
 *
 * 28.K.29: each box is NESTED under the activity row its step produced
 * (instead of every box trailing at the bottom of the card) — the last
 * describe block below pins that placement.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentActivity } from "./AgentActivity";
import { initRunState, runReducer } from "../../state/runReducer";
import type { RuntimeEvent } from "../../types/runtime";

const ORDER = [
  { id: "client-intake", skill: "client-intake", produces: "client-profile" },
  { id: "requirement-analysis", skill: "requirement-analysis", produces: "requirement-analysis" },
];
function ev(type: string, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: Math.random().toString(36).slice(2), run_id: "r",
    timestamp: "t", event_type: type as RuntimeEvent["event_type"],
    stage: null, skill: null, status: null, case_id: null, artifact_id: null,
    eval_id: null, repair_attempt: null, message: null, data: {}, ...extra,
  } as never;
}
function build(events: RuntimeEvent[]) {
  return runReducer(initRunState("r", ORDER), { type: "events", events })!;
}

/** The activity ROW (glyph + label) whose text contains `fragment`. */
function rowFor(fragment: string): HTMLElement {
  const rows = Array.from(document.querySelectorAll("[data-activity-item]")) as HTMLElement[];
  const row = rows.find((el) => (el.textContent ?? "").includes(fragment));
  if (!row) throw new Error(`no activity row containing "${fragment}"`);
  return row;
}

/** Step-output boxes rendered inside that row's list item (28.K.29 nesting). */
function boxesUnder(fragment: string): HTMLElement[] {
  const li = rowFor(fragment).closest("li");
  return Array.from(
    li?.querySelectorAll('[data-testid="step-output-box"]') ?? [],
  ) as HTMLElement[];
}

/** The step-output box whose rendered text contains `fragment`. */
function boxFor(fragment: string): HTMLElement {
  const boxes = screen.getAllByTestId("step-output-box") as HTMLElement[];
  const box = boxes.find((el) => (el.textContent ?? "").includes(fragment));
  if (!box) throw new Error(`no step output box containing "${fragment}"`);
  return box;
}

/** A realistic planning turn: one step per milestone, in real SSE order. */
const PLANNING: RuntimeEvent[] = [
  ev("run_started"),
  ev("intent_classified", { data: { intent: "insurance_plan" } }),
  ev("agent_step_started", { data: { step: 1 } }),
  ev("agent_stream_delta", { data: { kind: "reasoning", text: "推理A：先看家庭结构" } }),
  ev("agent_decision", { data: { action: "call_tool", tool: "record_client_profile" } }),
  ev("tool_started", { data: { tool: "record_client_profile" } }),
  ev("stage_started", { stage: "client-intake" }),
  ev("stage_completed", { stage: "client-intake" }),
  ev("eval_started", { stage: "client-intake" }),
  ev("eval_passed", { stage: "client-intake" }),
  ev("agent_step_started", { data: { step: 2 } }),
  ev("agent_stream_delta", { data: { kind: "reasoning", text: "推理B：再看保障需求" } }),
  ev("agent_decision", { data: { action: "call_tool", tool: "record_requirement_analysis" } }),
  ev("stage_started", { stage: "requirement-analysis" }),
  ev("stage_completed", { stage: "requirement-analysis" }),
  ev("run_completed", { status: "completed" }),
];

describe("step streaming output boxes", () => {
  it("renders one box per step with accumulated (sanitized) text", () => {
    const s = build([
      ev("run_started"),
      ev("agent_step_started", { data: { step: 1 } }),
      ev("agent_stream_delta", { data: { kind: "content", text: "分析开始。见 ART-009。" } }),
      ev("agent_decision", { data: { action: "call_tool" } }),
      ev("agent_step_started", { data: { step: 2 } }),
      ev("agent_stream_delta", { data: { kind: "content", text: "检索结果。" } }),
    ]);
    render(<AgentActivity state={s} streaming={false} />);
    const boxes = screen.getAllByTestId("step-output-box");
    expect(boxes).toHaveLength(2);
    expect(boxes[0]!.textContent).not.toContain("ART-009"); // sanitized
    expect(boxes[0]!.textContent).toContain("分析开始");
    expect(boxes[1]!.textContent).toContain("检索结果");
  });

  it("active (last live) box carries the cursor + data-active=1; others 0", () => {
    const s = build([
      ev("run_started"),
      ev("agent_step_started", { data: { step: 1 } }),
      ev("agent_stream_delta", { data: { kind: "content", text: "完成。" } }),
      ev("agent_decision", { data: { action: "call_tool" } }),
      ev("agent_step_started", { data: { step: 2 } }),
      ev("agent_stream_delta", { data: { kind: "content", text: "进行中" } }),
    ]);
    render(<AgentActivity state={s} streaming={false} />);
    const boxes = screen.getAllByTestId("step-output-box");
    expect(boxes[0]!.getAttribute("data-active")).toBe("0");
    expect(boxes[1]!.getAttribute("data-active")).toBe("1");
  });

  it("fixed-height class present (bounded container)", () => {
    const s = build([
      ev("agent_step_started", { data: { step: 1 } }),
      ev("agent_stream_delta", { data: { kind: "content", text: "x".repeat(500) } }),
    ]);
    render(<AgentActivity state={s} streaming={false} />);
    const box = screen.getByTestId("step-output-box");
    expect(box.className).toContain("max-h-40");
    expect(box.className).toContain("overflow-y-auto");
  });

  it("28.K.28: reasoning renders in a de-emphasized segment, content separately", () => {
    const s = build([
      ev("agent_step_started", { data: { step: 1 } }),
      ev("agent_stream_delta", { data: { kind: "reasoning", text: "内部思考" } }),
      ev("agent_stream_delta", { data: { kind: "content", text: "可见。" } }),
    ]);
    const { container } = render(<AgentActivity state={s} streaming={false} />);
    expect(container.textContent).toContain("内部思考");
    expect(container.textContent).toContain("可见。");
    // the two kinds stay separately addressable in the DOM
    expect(screen.getByTestId("step-output-reasoning").textContent).toBe("内部思考");
    expect(screen.getByTestId("step-output-content").textContent).toBe("可见。");
    expect(screen.getByTestId("step-output-reasoning").className).toContain("italic");
  });

  it("28.K.28: reasoning segments are sanitized too (render-time hygiene)", () => {
    const s = build([
      ev("agent_step_started", { data: { step: 1 } }),
      ev("agent_stream_delta", {
        data: { kind: "reasoning", text: "见 run_abcdef12345678 与 ART-009" },
      }),
    ]);
    const { container } = render(<AgentActivity state={s} streaming={false} />);
    expect(container.textContent).not.toContain("ART-009");
    expect(container.textContent).not.toContain("run_abcdef12345678");
    // the surrounding prose survives — only the ids are rewritten
    expect(container.textContent).toContain("见");
  });

  it("QA turns NOW show a composing step box (fix: auto-open on first delta)", () => {
    const s = build([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      ev("agent_stream_delta", { data: { kind: "content", text: "答案" } }),
    ]);
    render(<AgentActivity state={s} streaming={false} />);
    const box = screen.getByTestId("step-output-box");
    expect(box.textContent).toContain("答案");
  });

  // 28.K.27 — regression: an ALWAYS-THINKING model (glm-5.3) streams only
  // `reasoning` deltas for its whole first phase; before that fix the active
  // step rendered NO box at all and the user saw a silent page (measured in
  // production: 4418 reasoning deltas / 90s, zero content).
  // 28.K.28 — those reasoning deltas now FILL the box (segmented).
  it("28.K.28: a reasoning-only live step SHOWS the reasoning (chip + muted segment)", () => {
    const s = build([
      ev("run_started"),
      ev("agent_step_started", { data: { step: 1 } }),
      ev("agent_stream_delta", { data: { kind: "reasoning", text: "内部推理X" } }),
    ]);
    const { container } = render(<AgentActivity state={s} streaming={false} />);
    const box = screen.getByTestId("step-output-box");
    expect(box.textContent).toContain("内部推理X");
    expect(screen.getByTestId("step-output-reasoning-chip").textContent).toBe("思考");
    // there IS text now, so the empty-phase placeholder must not appear
    expect(screen.queryByTestId("step-output-thinking")).toBeNull();
    expect(container.textContent).toContain("内部推理X");
  });

  it("28.K.27: a step that has NOT streamed yet renders no box (no templating)", () => {
    const s = build([
      ev("run_started"),
      ev("agent_step_started", { data: { step: 1 } }),
    ]);
    render(<AgentActivity state={s} streaming={false} />);
    expect(screen.queryAllByTestId("step-output-box")).toHaveLength(0);
  });

  it("28.K.28: a mixed step keeps reasoning and content in separate segments", () => {
    const s = build([
      ev("agent_step_started", { data: { step: 1 } }),
      ev("agent_stream_delta", { data: { kind: "reasoning", text: "想一想" } }),
      ev("agent_stream_delta", { data: { kind: "content", text: "分析结果。" } }),
    ]);
    render(<AgentActivity state={s} streaming={false} />);
    expect(screen.queryByTestId("step-output-thinking")).toBeNull();
    expect(screen.getByTestId("step-output-reasoning").textContent).toBe("想一想");
    expect(screen.getByTestId("step-output-content").textContent).toBe("分析结果。");
    expect(screen.getByTestId("step-output-box").textContent).toContain("分析结果。");
  });
});

// --------------------------------------------------------------------------- #
// 28.K.29 — per-step nesting
// --------------------------------------------------------------------------- #

describe("28.K.29 — each step's output box sits UNDER its own milestone", () => {
  it("step 1's text is nested in the client-intake row, step 2's in the requirement row", () => {
    const s = build(PLANNING);
    render(<AgentActivity state={s} streaming={false} />);

    // the rows themselves are untouched by nesting
    expect(rowFor("已了解家庭基本情况").textContent).toBe("✓已了解家庭基本情况");
    expect(rowFor("已分析保障需求").textContent).toBe("✓已分析保障需求");

    const first = boxesUnder("已了解家庭基本情况");
    expect(first).toHaveLength(1);
    expect(first[0]!.textContent).toContain("推理A");

    const second = boxesUnder("已分析保障需求");
    expect(second).toHaveLength(1);
    expect(second[0]!.textContent).toContain("推理B");

    // …and NOT anywhere else (no duplicate, no trailing stack)
    expect(boxesUnder("已完成分析")).toHaveLength(0);
    expect(boxesUnder("已完成信息核实")).toHaveLength(0);
    expect(screen.queryByTestId("step-outputs")).toBeNull(); // no orphans
    expect(screen.getAllByTestId("step-output-box")).toHaveLength(2);
  });

  it("boxes keep the order of their rows (not the order they happened to mount)", () => {
    const s = build(PLANNING);
    render(<AgentActivity state={s} streaming={false} />);
    const all = screen.getAllByTestId("step-output-box");
    expect(all[0]!.textContent).toContain("推理A");
    expect(all[1]!.textContent).toContain("推理B");
    // DOM order really follows the activity list order
    const rows = Array.from(document.querySelectorAll("[data-activity-item]")) as HTMLElement[];
    const owner = rows.find((r) => r.closest("li")?.contains(all[0]!));
    expect(owner?.textContent).toContain("已了解家庭基本情况");
  });

  it("the box is a SIBLING of the row element, never inside it (row text stays clean)", () => {
    const s = build(PLANNING);
    render(<AgentActivity state={s} streaming={false} />);
    const row = rowFor("已了解家庭基本情况");
    expect(row.querySelector('[data-testid="step-output-box"]')).toBeNull();
    expect(row.closest("li")!.querySelector('[data-testid="step-output-box"]')).not.toBeNull();
  });

  it("only the LIVE step's box carries the cursor, wherever it is nested", () => {
    // feed the run up to the start of step 2 only (run stays LIVE)
    const live = PLANNING.slice(0, 11).concat([
      ev("agent_stream_delta", { data: { kind: "reasoning", text: "推理B：在看需求" } }),
    ]);
    const s = build(live);
    render(<AgentActivity state={s} streaming />);
    const boxes = screen.getAllByTestId("step-output-box");
    const a = boxes.find((el) => (el.textContent ?? "").includes("推理A"))!;
    const b = boxes.find((el) => (el.textContent ?? "").includes("推理B"))!;
    expect(a.getAttribute("data-active")).toBe("0");
    expect(b.getAttribute("data-active")).toBe("1");
  });

  it("an unattributable bucket is not dropped — it renders in the trailing container", () => {
    // no mapped activity event at all → no row to own the bucket
    const s = build([
      ev("agent_stream_delta", { data: { kind: "content", text: "孤立输出" } }),
    ]);
    render(<AgentActivity state={s} streaming={false} />);
    expect(document.querySelectorAll("[data-activity-item]")).toHaveLength(0);
    const trailing = screen.getByTestId("step-outputs");
    expect(trailing.textContent).toContain("孤立输出");
  });

  it("indentation + left rule are present on the nested container (visual ownership)", () => {
    const s = build(PLANNING);
    render(<AgentActivity state={s} streaming={false} />);
    const nested = screen.getAllByTestId("activity-step-outputs");
    expect(nested).toHaveLength(2);
    expect(nested[0]!.className).toContain("ml-5");
    expect(nested[0]!.className).toContain("border-l-2");
  });
});

/**
 * 28.K.30 — auto-follow regression.
 *
 * The box froze after one screenful because the old guard tested
 * "am I within 24px of the bottom?" AFTER the content grew. jsdom has no
 * layout engine, so the geometry is pinned by hand: scrollHeight /
 * clientHeight are fixed values and scrollTop becomes an observable
 * property, which is exactly what the component writes and reads.
 */
describe("StepOutputBox — auto-follow (28.K.30)", () => {
  function pin(el: HTMLElement, scrollHeight: number, clientHeight: number) {
    Object.defineProperty(el, "scrollHeight", { value: scrollHeight, configurable: true });
    Object.defineProperty(el, "clientHeight", { value: clientHeight, configurable: true });
    if (!Object.getOwnPropertyDescriptor(el, "scrollTop")) {
      let top = 0;
      Object.defineProperty(el, "scrollTop", {
        get: () => top,
        set: (v: number) => { top = v; },
        configurable: true,
      });
    }
  }

  function stepState(text: string) {
    return build([
      ev("agent_step_started", { data: { step: 1 } }),
      ev("agent_stream_delta", { data: { kind: "reasoning", text } }),
    ]);
  }

  it("stays pinned to the newest text even when one delta is taller than the old 24px slack", () => {
    const { rerender } = render(<AgentActivity state={stepState("开始")} streaming />);
    const box = screen.getByTestId("step-output-box");
    pin(box, 200, 160);

    // one delta adds 40px of content — the exact case the old guard gave up on
    rerender(<AgentActivity state={stepState("开始" + "接着往下分析。".repeat(40))} streaming />);
    expect(box.scrollTop).toBe(200);

    pin(box, 500, 160);
    rerender(<AgentActivity state={stepState("开始" + "继续。".repeat(120))} streaming />);
    expect(box.scrollTop).toBe(500);
  });

  it("stops stealing the view once the user scrolls up, and resumes at the bottom", () => {
    const { rerender } = render(<AgentActivity state={stepState("开始")} streaming />);
    const box = screen.getByTestId("step-output-box");
    pin(box, 400, 160);
    rerender(<AgentActivity state={stepState("开始" + "一段很长的推理文本。".repeat(20))} streaming />);
    expect(box.scrollTop).toBe(400);

    // user drags the scrollbar up to re-read the beginning
    box.scrollTop = 0;
    box.dispatchEvent(new Event("scroll"));
    pin(box, 800, 160);
    rerender(<AgentActivity state={stepState("开始" + "又一段很长的推理文本。".repeat(40))} streaming />);
    expect(box.scrollTop).toBe(0); // their position is respected

    // user returns to the bottom → following resumes
    box.scrollTop = 640; // 800 - 160
    box.dispatchEvent(new Event("scroll"));
    pin(box, 1200, 160);
    rerender(<AgentActivity state={stepState("开始" + "再一段很长的推理文本。".repeat(60))} streaming />);
    expect(box.scrollTop).toBe(1200);
  });

  it("does not scroll a box that is no longer the active step", () => {
    const s = build([
      ev("agent_step_started", { data: { step: 1 } }),
      ev("agent_stream_delta", { data: { kind: "reasoning", text: "第一步输出" } }),
      ev("agent_decision", { data: { action: "call_tool", tool: "record_client_profile" } }),
      ev("tool_started", { data: { tool: "record_client_profile" } }),
      ev("stage_started", { stage: "client-intake" }),
      ev("stage_completed", { stage: "client-intake" }),
      ev("tool_completed", { data: { tool: "record_client_profile" } }),
      ev("agent_step_started", { data: { step: 2 } }),
      ev("agent_stream_delta", { data: { kind: "reasoning", text: "第二步输出" } }),
    ]);
    render(<AgentActivity state={s} streaming />);
    const done = boxFor("第一步输出");
    pin(done, 900, 160);
    expect(done.getAttribute("data-active")).toBe("0");
    expect(done.scrollTop).toBe(0);
  });
});

/**
 * 28.K.30 — the placeholder is a claim, so it needs a real boundary.
 *
 * "正在思考…" is only truthful while a generation is in flight. Once the model
 * has returned, the remaining silence belongs to tool/stage execution (the
 * stages are deterministic Python with no model running), so an empty box is
 * not mounted at all.
 */
describe("StepOutputBox — the thinking placeholder is bounded by the model (28.K.30)", () => {
  /** step 1 streamed + ran its tool; step 2 has just started. */
  const upToStep2 = (extra: RuntimeEvent[] = []) =>
    build([
      ev("run_started"),
      ev("agent_step_started", { data: { step: 1 } }),
      ev("agent_stream_delta", { data: { kind: "reasoning", text: "第一步推理" } }),
      ev("agent_decision", { data: { step: 1, action: "call_tool", tool: "knowledge_search" } }),
      ev("tool_started", { data: { step: 1, tool: "knowledge_search" } }),
      ev("tool_completed", { data: { step: 1, tool: "knowledge_search" } }),
      ev("agent_step_started", { data: { step: 2 } }),
      ...extra,
    ]);

  it("shows the placeholder while the model is still generating", () => {
    render(<AgentActivity state={upToStep2()} streaming />);
    expect(screen.getByTestId("step-output-thinking")).toBeTruthy();
  });

  it("drops the placeholder (and the whole empty box) once the model has returned", () => {
    // the tool starting proves the generation finished — the wait is over
    render(
      <AgentActivity
        state={upToStep2([ev("tool_started", { data: { step: 2, tool: "record_risk_assessment" } })])}
        streaming
      />,
    );
    expect(screen.queryByTestId("step-output-thinking")).toBeNull();
    // no empty frame is left dangling under the milestone either
    expect(screen.getAllByTestId("step-output-box")).toHaveLength(1);
    // step 1's real text is untouched
    expect(boxFor("第一步推理")).toBeTruthy();
  });

  it("keeps the box for a step that DID stream, whatever the model is doing now", () => {
    render(
      <AgentActivity
        state={upToStep2([
          ev("agent_stream_delta", { data: { kind: "reasoning", text: "开始处理" } }),
          ev("tool_started", { data: { step: 2, tool: "record_risk_assessment" } }),
        ])}
        streaming
      />,
    );
    expect(screen.queryByTestId("step-output-thinking")).toBeNull();
    expect(boxFor("开始处理")).toBeTruthy();
  });
});
