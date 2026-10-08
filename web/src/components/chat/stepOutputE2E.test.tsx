/**
 * Step streaming E2E — simulates the REAL SSE dispatch path
 * (singular "event" actions, exactly like useRunStream:129) and verifies
 * AgentActivity renders visible step output boxes with growing content.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentActivity } from "./AgentActivity";
import { initRunState, runReducer } from "../../state/runReducer";
import type { RuntimeEvent } from "../../types/runtime";

const ORDER = [
  { id: "client-intake", skill: "client-intake", produces: "client-profile" },
];
function ev(type: string, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: Math.random().toString(36).slice(2), run_id: "r",
    timestamp: "t", event_type: type as RuntimeEvent["event_type"],
    stage: null, skill: null, status: null, case_id: null, artifact_id: null,
    eval_id: null, repair_attempt: null, message: null, data: {}, ...extra,
  } as never;
}

describe("step streaming E2E — real SSE singular-dispatch path", () => {
  it("visible content grows incrementally as deltas arrive (T2 < T5)", () => {
    let s = initRunState("r", ORDER);

    // real SSE order: step_started → deltas → decision → step2 → deltas
    const feed = (events: RuntimeEvent[]) => {
      for (const e of events) s = runReducer(s, { type: "event", event: e })!;
    };

    // T1: step 1 starts
    feed([ev("run_started"), ev("agent_step_started", { data: { step: 1 } })]);
    const r1 = render(<AgentActivity state={s} streaming={false} />);
    // no box yet (no content)
    expect(screen.queryAllByTestId("step-output-box")).toHaveLength(0);

    // T2: first delta arrives → box becomes visible with content
    feed([ev("agent_stream_delta", { data: { kind: "content", text: "我正在分析" } })]);
    r1.rerender(<AgentActivity state={s} streaming={false} />);
    let boxes = screen.getAllByTestId("step-output-box");
    expect(boxes).toHaveLength(1);
    expect(boxes[0]!.textContent).toContain("我正在分析");

    // T3: more deltas grow the same box
    feed([ev("agent_stream_delta", { data: { kind: "content", text: "你的家庭结构" } })]);
    r1.rerender(<AgentActivity state={s} streaming={false} />);
    boxes = screen.getAllByTestId("step-output-box");
    expect(boxes[0]!.textContent).toContain("我正在分析你的家庭结构");

    // T4: step 1 decides → step 2 starts → NEW box
    feed([
      ev("agent_decision", { data: { action: "call_tool" } }),
      ev("agent_step_started", { data: { step: 2 } }),
      ev("agent_stream_delta", { data: { kind: "content", text: "检索资料中" } }),
    ]);
    r1.rerender(<AgentActivity state={s} streaming={false} />);
    boxes = screen.getAllByTestId("step-output-box");
    expect(boxes).toHaveLength(2);
    expect(boxes[0]!.textContent).toContain("我正在分析你的家庭结构"); // preserved
    expect(boxes[1]!.textContent).toContain("检索资料中"); // new step

    // T5: terminal — all boxes frozen, no new writes
    feed([
      ev("agent_stream_delta", { data: { kind: "content", text: "。" } }),
      ev("run_completed", { status: "completed" }),
      ev("agent_stream_delta", { data: { kind: "content", text: "迟到" } }),
    ]);
    r1.rerender(<AgentActivity state={s} streaming={false} />);
    boxes = screen.getAllByTestId("step-output-box");
    expect(boxes[1]!.textContent).toContain("检索资料中。"); // not 检索资料中。迟到
    expect(boxes[0]!.getAttribute("data-active")).toBe("0");
    expect(boxes[1]!.getAttribute("data-active")).toBe("0");
  });

  it("QA turn NOW shows a composing step box (live fix: auto-open on first content delta)", () => {
    let s = initRunState("r", ORDER);
    const feed = (events: RuntimeEvent[]) => {
      for (const e of events) s = runReducer(s, { type: "event", event: e })!;
    };
    feed([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      ev("agent_stream_delta", { data: { kind: "content", text: "答案" } }),
    ]);
    render(<AgentActivity state={s} streaming={false} />);
    expect(screen.getByTestId("step-output-box").textContent).toContain("答案");
    expect(s.stream?.text).toBe("答案"); // K.20 bubble ALSO preserved
  });
});
