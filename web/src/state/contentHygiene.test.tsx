/**
 * 28.K.25-S1 — frontend render-time hygiene (split-chunk safe, JSX).
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Conversation } from "../components/chat/Conversation";
import { sanitizeConsumerText } from "./contentHygiene";
import { initRunState, runReducer } from "./runReducer";
import type { RuntimeEvent } from "../types/runtime";
import type { ChatSession } from "../types/chat";

const ORDER = [
  { id: "client-intake", skill: "client-intake", produces: "client-profile" },
];
function ev(type: string, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: Math.random().toString(36).slice(2), run_id: "run_s",
    timestamp: "t", event_type: type as RuntimeEvent["event_type"],
    stage: null, skill: null, status: null, case_id: null, artifact_id: null, eval_id: null,
    repair_attempt: null, message: null, data: {}, ...extra,
  };
}
const delta = (kind: "reasoning" | "content", text: string) =>
  ev("agent_stream_delta", { data: { kind, text } });
function build(events: RuntimeEvent[]) {
  return runReducer(initRunState("run_s", ORDER), { type: "events", events })!;
}
const CHAT: ChatSession = {
  id: "chat_s", title: "S1", caseId: "c1", runId: "run_s",
  serverChatId: null, mode: "agent",
  createdAt: "t", updatedAt: "t",
  messages: [
    { kind: "user", id: "u1", at: "t", text: "问题" },
    { kind: "activity", id: "a1", at: "t", runId: "run_s", caseId: "c1" },
  ],
};

describe("28.K.25-S1 — frontend render-time hygiene (split-chunk safe)", () => {
  it("sanitizes accumulated stream text; ids split across chunks caught at render", () => {
    expect(sanitizeConsumerText("（ART-009）已生成")).not.toContain("ART");
    expect(sanitizeConsumerText("ART-009 done")).not.toContain("ART-009");
    expect(sanitizeConsumerText("P001 保额50万 SMART-1")).toBe("P001 保额50万 SMART-1");
  });

  it("Conversation stream-message renders sanitized text", () => {
    const state = build([delta("content", "报告见 ART-009。")]);
    render(<Conversation chat={CHAT} streamState={state} streaming={false}
      streamError={null} conflict={null}
      onOpenConflictOwner={() => {}} onPickPrompt={() => {}} />);
    expect(screen.getByTestId("stream-message").textContent).not.toContain("ART-009");
  });

  it("MessageView sanitizes final assistant text", async () => {
    const mod = await import("../components/chat/Message");
    const { container } = render(
      mod.MessageView({ message: { kind: "assistant", id: "a", at: "t", text: "报告（ART-009）" } }));
    expect(container.textContent).not.toContain("ART-009");
  });
});
