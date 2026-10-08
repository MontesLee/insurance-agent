/**
 * Step-scoped streaming tests — per-step LLM output buckets.
 *
 * agent_step_started opens a bucket; deltas append to the CURRENT bucket
 * tagged by kind; a new step opens a new bucket (isolation).
 *
 * 28.K.28 (supersedes E-2): `reasoning` deltas DO enter the bucket now — as
 * `kind:"reasoning"` segments kept distinct from `content` — because
 * glm-5.3 streams reasoning for its entire first phase. They still never
 * enter the answer bubble, and QA-slice turns (no steps) keep the global
 * content-only message bubble.
 */
import { describe, expect, it } from "vitest";
import { bucketText, initRunState, runReducer } from "./runReducer";
import type { RuntimeEvent } from "../types/runtime";

const ORDER = [
  { id: "client-intake", skill: "client-intake", produces: "client-profile" },
];
function ev(type: string, extra: Record<string, unknown> = {}): RuntimeEvent {
  return {
    event_id: Math.random().toString(36).slice(2), run_id: "r",
    timestamp: "t", event_type: type as RuntimeEvent["event_type"],
    stage: null, skill: null, status: null, case_id: null, artifact_id: null,
    eval_id: null, repair_attempt: null, message: null, data: {}, ...extra,
  } as never;
}
const step = (n: number) => ev("agent_step_started", { data: { step: n } });
const delta = (kind: "reasoning" | "content", text: string) =>
  ev("agent_stream_delta", { data: { kind, text } });

function build(events: RuntimeEvent[]) {
  return runReducer(initRunState("r", ORDER), { type: "events", events })!;
}

describe("step-scoped streaming buckets", () => {
  it("Case B: multi-step isolation — step 2 content NEVER enters step 1", () => {
    const s = build([
      step(1), delta("content", "分析A"), delta("content", "。"),
      ev("agent_decision", { data: { action: "call_tool" } }),
      step(2), delta("content", "检索B"), delta("content", "。"),
    ]);
    expect(s.stepOutputs).toHaveLength(2);
    expect(s.stepOutputs[0]!.key).toBe("step-1");
    expect(bucketText(s.stepOutputs[0]!)).toBe("分析A。");
    expect(s.stepOutputs[1]!.key).toBe("step-2");
    expect(bucketText(s.stepOutputs[1]!)).toBe("检索B。");
    // global message bubble NOT used during agent-loop steps
    expect(s.stream).toBeNull();
  });

  it("Case A: single step — accumulates progressively, completes at terminal", () => {
    const s1 = build([step(1), delta("content", "我先分析")]);
    expect(bucketText(s1.stepOutputs[0]!)).toBe("我先分析");
    const s2 = build([
      step(1), delta("content", "我先分析"), delta("content", "家庭结构。"),
      ev("run_completed", { status: "completed" }),
    ]);
    expect(s2.currentStepKey).toBeNull(); // frozen
    expect(bucketText(s2.stepOutputs[0]!)).toBe("我先分析家庭结构。");
  });

  // 28.K.28 — Owner decision: reasoning is displayable in the step box.
  it("28.K.28: reasoning ENTERS the bucket as a segment distinct from content", () => {
    const s = build([
      step(1), delta("reasoning", "内部思考"), delta("content", "可见"),
      delta("reasoning", "更多思考"),
    ]);
    expect(s.stepOutputs[0]!.segments).toEqual([
      { kind: "reasoning", text: "内部思考" },
      { kind: "content", text: "可见" },
      { kind: "reasoning", text: "更多思考" },
    ]);
    expect(bucketText(s.stepOutputs[0]!)).toBe("内部思考可见更多思考");
  });

  it("28.K.28: adjacent same-kind deltas merge into ONE segment (R,C,R,C -> 3)", () => {
    const s = build([
      step(1),
      delta("reasoning", "甲"), delta("reasoning", "乙"),
      delta("content", "丙"), delta("content", "丁"),
    ]);
    expect(s.stepOutputs[0]!.segments).toEqual([
      { kind: "reasoning", text: "甲乙" },
      { kind: "content", text: "丙丁" },
    ]);
  });

  it("28.K.28: the answer bubble stays content-only (CoT never reaches the final answer)", () => {
    const s = build([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      delta("reasoning", "内部推理"),
      delta("content", "答案"),
    ]);
    expect(bucketText(s.stepOutputs[0]!)).toBe("内部推理答案"); // box: both kinds
    expect(s.stream?.text).toBe("答案"); // bubble: content only
    expect(s.stream?.kind).toBe("content");
  });

  it("QA-slice turn (no agent_step) NOW auto-opens a composing bucket AND keeps the K.20 bubble", () => {
    const s = build([
      ev("run_started"),
      ev("intent_classified", { data: { intent: "insurance_qa" } }),
      delta("content", "已验证答案"),
    ]);
    expect(s.stepOutputs).toHaveLength(1);
    expect(s.stepOutputs[0]!.key).toBe("qa-composing");
    expect(bucketText(s.stepOutputs[0]!)).toBe("已验证答案");
    // K.20 message bubble unchanged — both views coexist
    expect(s.stream?.text).toBe("已验证答案");
  });

  it("deltas AFTER agent_decision are not mis-attributed to the prior step", () => {
    const s = build([
      step(1), delta("content", "一"),
      ev("agent_decision", { data: { action: "call_tool" } }),
      // a delta between decision and the next step has NO open bucket —
      // it goes to the global buffer, which the next agent_step_started
      // clears (step boundary); it NEVER lands in step-1's bucket
      delta("content", "边界"),
      step(2), delta("content", "二"),
    ]);
    expect(bucketText(s.stepOutputs[0]!)).toBe("一"); // not "一边界"
    expect(bucketText(s.stepOutputs[1]!)).toBe("二");
  });

  it("Case D: terminal freezes buckets — no post-terminal writes", () => {
    const s = build([
      step(1), delta("content", "工作"),
      ev("run_completed", { status: "completed" }),
      delta("content", "迟到"),
    ]);
    expect(bucketText(s.stepOutputs[0]!)).toBe("工作");
  });

  it("bucket text tail-capped at 4000 chars (long-output safety)", () => {
    const big = "x".repeat(4500);
    const s = build([step(1), delta("content", big)]);
    expect(bucketText(s.stepOutputs[0]!).length).toBe(4000);
    expect(bucketText(s.stepOutputs[0]!)).toBe("x".repeat(4000));
  });

  it("28.K.28: the 4000-char cap spans segments — oldest text drops first", () => {
    const s = build([
      step(1),
      delta("reasoning", "R".repeat(3000)),
      delta("content", "C".repeat(2000)),
    ]);
    const b = s.stepOutputs[0]!;
    expect(b.segments.map((x) => x.kind)).toEqual(["reasoning", "content"]);
    // 5000 -> 4000: the leading reasoning segment is trimmed by 1000
    expect(bucketText(b)).toBe("R".repeat(2000) + "C".repeat(2000));
  });

  it("28.K.28: an empty-text delta changes nothing (no empty segment)", () => {
    const s = build([step(1), delta("reasoning", ""), delta("content", "x")]);
    expect(s.stepOutputs[0]!.segments).toEqual([{ kind: "content", text: "x" }]);
  });
});

describe("28.K.29-A — answer-channel deltas (final answer streaming)", () => {
  const answer = (text: string, extra: Record<string, unknown> = {}) =>
    ev("agent_stream_delta",
       { data: { kind: "content", channel: "answer", text, ...extra } });

  it("answer deltas route to the message bubble, never into a step bucket", () => {
    const s = build([
      step(1),
      delta("reasoning", "思考"),
      answer("最终答案第一段。"),
      answer("第二段。"),
    ]);
    // the bubble receives the streamed answer (message position)
    expect(s.stream?.kind).toBe("content");
    expect(s.stream?.text).toBe("最终答案第一段。第二段。");
    // the step bucket keeps ONLY the reasoning segment — no duplication
    expect(s.stepOutputs[0]!.segments).toEqual([{ kind: "reasoning", text: "思考" }]);
  });

  it("reset marker discards the partial answer (retry convergence)", () => {
    const s = build([
      step(1),
      answer("第一次的部分"),
      answer("", { reset: true }),
      answer("第二次的完整回答。"),
    ]);
    expect(s.stream?.text).toBe("第二次的完整回答。");
  });

  it("an answer stream is NOT interrupted by step boundaries (message position)", () => {
    const s = build([
      step(1),
      answer("答前半"),
      ev("agent_decision", { data: { step: 1, action: "call_tool", reason: "r" } }),
      step(2),
      answer("答后半"),
    ]);
    expect(s.stream?.text).toBe("答前半答后半");
    expect(s.stepOutputs[0]!.segments).toEqual([]);
    expect(s.stepOutputs[1]!.segments).toEqual([]);
  });

  it("channel-less content keeps the pre-K.29 behavior (regression)", () => {
    const s = build([step(1), delta("content", "过程文本")]);
    // agent-loop channel-less content: bucket ONLY (no bubble duplication)
    expect(s.stepOutputs[0]!.segments).toEqual([{ kind: "content", text: "过程文本" }]);
    expect(s.stream).toBeNull();
  });

  it("answer stream survives to terminal; transcript finalize owns the bubble end", () => {
    const s = build([
      step(1),
      answer("流式答案"),
      ev("run_completed", { status: "completed" }),
    ]);
    // the reducer keeps the stream for the terminal render gate; the
    // Conversation component hides it once terminalEvent lands and the
    // transcript message takes over (K.20 contract, unchanged)
    expect(s.terminalEvent?.event_type).toBe("run_completed");
    expect(s.stepOutputs[0]!.segments).toEqual([]);
  });
});
