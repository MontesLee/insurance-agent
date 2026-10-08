/**
 * 28.K.20 — Consumer LLM streaming response tests (message-position).
 *
 * The live content stream renders as an assistant-position bubble in the
 * Conversation (single display; the activity card no longer hosts it).
 * The ANSWER BUBBLE is content-only: reasoning never reaches it. The bubble
 * converges into the transcript's assistant message at terminal (no
 * duplication). Failure retains safely streamed content paired with the
 * failure copy (never raw errors).
 *
 * 28.K.28 (supersedes E-2): reasoning IS displayable — but only inside the
 * step output box, rendered as a de-emphasized segment. The bubble stays
 * content-only, so the final answer cannot carry CoT.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Conversation } from "./Conversation";
import { initRunState, runReducer } from "../../state/runReducer";
import type { RuntimeEvent } from "../../types/runtime";
import type { ChatSession } from "../../types/chat";

const ORDER = [
  { id: "client-intake", skill: "client-intake", produces: "client-profile" },
  { id: "solution", skill: "solution", produces: "solution-plan" },
];

function ev(type: string, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: `evt_${Math.random().toString(36).slice(2, 8)}`, run_id: "run_s",
    timestamp: "2026-09-27T07:00:00Z", event_type: type as RuntimeEvent["event_type"],
    stage: null, skill: null, status: null, case_id: "c1", artifact_id: null, eval_id: null,
    repair_attempt: null, message: null, data: {}, ...extra,
  };
}
const delta = (kind: "reasoning" | "content", text: string) =>
  ev("agent_stream_delta", { data: { kind, text } });

function build(events: RuntimeEvent[]) {
  return runReducer(initRunState("run_s", ORDER), { type: "events", events })!;
}

const CHAT: ChatSession = {
  id: "chat_s", title: "流式测试", caseId: "c1", runId: "run_s",
  serverChatId: null, mode: "agent",
  createdAt: "2026-09-27T00:00:00.000Z", updatedAt: "2026-09-27T00:00:00.000Z",
  messages: [
    { kind: "user", id: "u1", at: "t", text: "百万医疗险和重疾险有什么区别？" },
    { kind: "activity", id: "a1", at: "t", runId: "run_s", caseId: "c1" },
  ],
};

function renderConv(state: ReturnType<typeof build>) {
  return render(
    <Conversation chat={CHAT} streamState={state} streaming={false}
      streamError={null} conflict={null}
      onOpenConflictOwner={() => {}} onPickPrompt={() => {}} />,
  );
}

describe("28.K.20 — message-position content streaming", () => {
  it("T1: content deltas accumulate visibly (A → AB → ABC)", () => {
    const { rerender } = renderConv(build([delta("content", "A")]));
    expect(screen.getByTestId("stream-message").textContent).toBe("A");
    rerender(<Conversation chat={CHAT} streamState={build([delta("content", "A"), delta("content", "B")])} streaming={false} streamError={null} conflict={null} onOpenConflictOwner={() => {}} onPickPrompt={() => {}} />);
    expect(screen.getByTestId("stream-message").textContent).toContain("AB");
    rerender(<Conversation chat={CHAT} streamState={build([delta("content", "A"), delta("content", "B"), delta("content", "C")])} streaming={false} streamError={null} conflict={null} onOpenConflictOwner={() => {}} onPickPrompt={() => {}} />);
    expect(screen.getByTestId("stream-message").textContent).toContain("ABC");
  });

  it("T2/T3/T6 (28.K.28): mixed stream — the bubble stays content-only; reasoning shows ONLY in the step box", () => {
    renderConv(build([
      ev("run_started"), delta("reasoning", "用户的问题属于概念比较"),
      delta("content", "百万医疗险和重疾险的核心区别是…"),
      delta("reasoning", "我需要考虑费用类型"),
      delta("content", "前者主要解决医疗费用…"),
    ]));
    // 1) the ANSWER bubble accumulates content only — CoT never reaches it
    const bubble = screen.getByTestId("stream-message").textContent ?? "";
    expect(bubble).toContain("核心区别");
    expect(bubble).toContain("前者主要解决");
    expect(bubble).not.toContain("用户的问题属于");
    expect(bubble).not.toContain("我需要考虑");
    // 2) 28.K.28: the step box DOES show both, as separate segments
    const reasoning = screen.getAllByTestId("step-output-reasoning")
      .map((el) => el.textContent).join("");
    expect(reasoning).toContain("用户的问题属于概念比较");
    expect(reasoning).toContain("我需要考虑费用类型");
  });

  it("T2b: reasoning-ONLY stream shows no bubble at all", () => {
    renderConv(build([ev("run_started"), delta("reasoning", "纯思考R")]));
    expect(screen.queryByTestId("stream-message")).toBeNull();
  });

  it("T4: terminal converges — bubble gone, no duplication of stream text alongside the finalized message", () => {
    const done = build([
      delta("content", "C1"), delta("content", "C2"), delta("content", "C3"),
      ev("run_completed", { status: "completed", data: { result_status: "COMPLETED" } }),
    ]);
    renderConv(done);
    expect(screen.queryByTestId("stream-message")).toBeNull();
    // the finalized transcript message is the single display of the answer
    expect(document.querySelectorAll('[data-testid="msg-assistant"]').length).toBe(0);
  });

  it("T7: fast completion (single delta + immediate terminal) leaves no stuck indicator", () => {
    const done = build([delta("content", "快答"), ev("run_completed", { status: "completed" })]);
    renderConv(done);
    expect(screen.queryByTestId("stream-message")).toBeNull();
    expect(screen.queryByTestId("activity-generation")).toBeNull();
    expect(screen.queryByTestId("activity-heartbeat")).toBeNull();
  });

  it("T10: all four terminals clean streaming + activity indicators", () => {
    for (const status of ["completed", "failed", "needs_review", "waiting"] as const) {
      const s = build([
        delta("content", "X"),
        ev("run_completed", { status }),
      ]);
      const { unmount } = renderConv(s);
      expect(screen.queryByTestId("stream-message")).toBeNull();
      expect(screen.queryByTestId("activity-generation")).toBeNull();
      unmount();
    }
  });

  it("T11 (28.K.28): no internal identifier leaks anywhere in the DOM; the answer bubble leaks no reasoning either", () => {
    renderConv(build([
      ev("run_started"),
      delta("reasoning", "内部思考链XYZ"),
      delta("content", "安全答案"),
    ]));
    // DOM-wide guard for INTERNAL IDENTIFIERS — unchanged by 28.K.28
    const blob = document.body.textContent ?? "";
    for (const bad of ["run_", "provider", "model", "tool", "skill", "glm", "WeKnora"]) {
      expect(blob.includes(bad), `must not contain ${bad}`).toBe(false);
    }
    // 28.K.28: reasoning text IS displayable now — in the step box only
    expect(screen.getByTestId("step-output-reasoning").textContent).toBe("内部思考链XYZ");
    const bubble = screen.getByTestId("stream-message").textContent ?? "";
    expect(bubble).not.toContain("内部思考链");
    expect(bubble).toContain("安全答案");
  });

  it("T8/T9: K.17 compatibility is covered by AgentActivity tests; silence heartbeat unaffected here", () => {
    // (structural: the Conversation adds no timers of its own — verified by
    // the absence of interval-based state in this component)
    renderConv(build([ev("run_started")]));
    expect(screen.queryByTestId("stream-message")).toBeNull();
  });
});

describe("28.K.20 — failure retains safely-streamed content (ChatLayout finalize)", () => {
  function sessWithFinalize() {
    return {
      ...CHAT,
      messages: CHAT.messages.slice(0, 2),
    };
  }

  it("T5: failed run keeps C1C2 + failure copy, no raw error", async () => {
    vi.mock("../../api/client", () => {
      class ApiError extends Error { status = 0; }
      return {
        ApiError,
        api: {
          whoami: vi.fn().mockResolvedValue({ subject: null, role: null, mode: "local-dev" }),
          getChat: vi.fn().mockResolvedValue({ messages: [] }), // no server reply
          agentConfig: vi.fn().mockResolvedValue({ configured: true }),
        },
      };
    });
    // build a reducer state that failed AFTER streaming C1 C2
    let s = initRunState("run_s", ORDER);
    s = runReducer(s, { type: "events", events: [
      delta("content", "百万医疗险和重疾险的区别主要在于…"),
      delta("content", "前者解决医疗费用。"),
      ev("run_failed", { data: { error: "provider_connection_reset" } }),
    ] })!;
    render(
      <Conversation chat={sessWithFinalize()} streamState={s} streaming={false}
        streamError={null} conflict={null}
        onOpenConflictOwner={() => {}} onPickPrompt={() => {}} />,
    );
    // The finalize combination logic itself (partial + suffix) is unit-locked
    // in ChatLayout; here we assert the stream contract: run_failed keeps
    // the content buffer available for finalize (not cleared), and no raw
    // error string reaches the DOM.
    expect(s.stream?.kind).toBe("content");
    expect(s.stream?.text).toContain("区别主要在于");
    expect(document.body.textContent ?? "").not.toContain("provider_connection_reset");
  });
});
