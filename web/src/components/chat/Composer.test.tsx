import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";
import { WelcomeScreen, DEMO_PROMPTS } from "./WelcomeScreen";
import { Conversation } from "./Conversation";
import { ChatSidebar } from "./ChatSidebar";
import { makeChat } from "../../state/chatState";
import { initRunState, runReducer } from "../../state/runReducer";
import type { Message } from "../../types/chat";
import type { RuntimeEvent } from "../../types/runtime";

function setup(over: Partial<Parameters<typeof Composer>[0]> = {}) {
  const onSend = vi.fn();
  const setDraft = vi.fn();
  const utils = render(
    <Composer
      disabled={false} streaming={false} viewStopped={false}
      onStopViewing={() => {}} onResumeViewing={() => {}}
      onSend={onSend} draft="" setDraft={setDraft}
      caseId="bm-complete-001" setCaseId={() => {}}
      {...over}
    />,
  );
  return { onSend, setDraft, ...utils };
}

describe("Composer (§22)", () => {
  it("Enter sends the trimmed draft with the mapped case id", () => {
    const { onSend } = setup({ draft: "给孩子配置重疾险" });
    fireEvent.keyDown(screen.getByTestId("composer-input"), { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("给孩子配置重疾险", "bm-complete-001");
  });

  it("Shift+Enter inserts a newline instead of sending", () => {
    const { onSend } = setup({ draft: "多行\n输入" });
    fireEvent.keyDown(screen.getByTestId("composer-input"), { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("cannot send while the agent is running (disabled state)", () => {
    const { onSend } = setup({ disabled: true, draft: "还想再问" });
    const btn = screen.getByTestId("send") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.keyDown(screen.getByTestId("composer-input"), { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("while streaming offers 停止查看 (view disconnect), not a fake cancel", () => {
    const onStop = vi.fn();
    setup({ streaming: true, onStopViewing: onStop });
    fireEvent.click(screen.getByTestId("stop-viewing"));
    expect(onStop).toHaveBeenCalled();
  });

  it("after stop, offers 重新连接 to re-attach the stream", () => {
    const onResume = vi.fn();
    setup({ streaming: false, viewStopped: true, onResumeViewing: onResume });
    fireEvent.click(screen.getByTestId("resume-viewing"));
    expect(onResume).toHaveBeenCalled();
  });
});

describe("Welcome screen (§23)", () => {
  it("demo prompts FILL the composer draft — click does not auto-send", () => {
    const onPick = vi.fn();
    render(<WelcomeScreen onPick={onPick} />);
    const prompts = screen.getAllByTestId("demo-prompt");
    expect(prompts.length).toBeGreaterThanOrEqual(4);
    fireEvent.click(prompts[0]!);
    expect(onPick).toHaveBeenCalledWith(DEMO_PROMPTS[0]!.text);
    expect(onPick).toHaveBeenCalledTimes(1); // fill only, never auto-send
  });

  it("discloses the honest limitation (structured Client State upstream)", () => {
    const { container } = render(<WelcomeScreen onPick={() => {}} />);
    expect(container.textContent).toContain("Portfolio Demo Mode");
    expect(container.textContent).toContain("结构化 Client State");
  });
});

describe("Conversation transcript", () => {
  const chat = makeChat("bm-complete-001", "t");
  const msgs: Message[] = [
    { kind: "user", id: "u1", at: "t", text: "我想给4岁的孩子买一份重疾险。" },
    { kind: "activity", id: "a1", at: "t", runId: "run_x", caseId: "bm-complete-001" },
    { kind: "assistant", id: "f1", at: "t", text: "分析完成。我整理了**报告**。" },
    { kind: "artifact", id: "r1", at: "t", runId: "run_x", artifactType: "insurance-report", title: "客户保险需求分析报告" },
  ];

  it("renders user / assistant / live activity / artifact card together", () => {
    const state = buildState([
      rEv("run_started"), rEv("stage_started", "client-intake"),
      rEv("stage_completed", "client-intake"), rEv("run_completed", null, { status: "completed" }),
    ]);
    render(
      <Conversation
        chat={{ ...chat, runId: "run_x", messages: msgs }}
        streamState={state} streaming={false} streamError={null}
        conflict={null} onOpenConflictOwner={() => {}} onPickPrompt={() => {}}
      />,
    );
    expect(screen.getByTestId("msg-user").textContent).toContain("重疾险");
    expect(screen.getByTestId("msg-assistant").textContent).toContain("报告");
    expect(screen.getByTestId("agent-activity")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-card").textContent).toContain("客户保险需求分析报告");
  });

  it("409 conflict banner offers to open the owning conversation", () => {
    const onOpen = vi.fn();
    render(
      <Conversation
        chat={{ ...chat, messages: msgs.slice(0, 1) }} streamState={null} streaming={false}
        streamError={null}
        conflict={{ caseId: "bm-complete-001", runId: "run_busy", ownerChatId: "chat_2" }}
        onOpenConflictOwner={onOpen} onPickPrompt={() => {}}
      />,
    );
    const banner = screen.getByTestId("chat-conflict");
    expect(banner.textContent).toContain("run_busy");
    fireEvent.click(screen.getByRole("button", { name: /打开正在分析的对话/ }));
    expect(onOpen).toHaveBeenCalledWith("chat_2");
  });

  it("stale run (server restart) degrades to an honest note, not a fake timeline", () => {
    render(
      <Conversation
        chat={{ ...chat, runId: "run_x", messages: msgs }} streamState={null}
        streaming={false} streamError={null} conflict={null}
        onOpenConflictOwner={() => {}} onPickPrompt={() => {}}
      />,
    );
    expect(screen.getByTestId("stale-activity").textContent).toContain("历史运行已结束");
  });
});

function buildState(events: ReturnType<typeof rEv>[]) {
  let s = initRunState("run_x", [
    { id: "client-intake", skill: "client-intake", produces: "client-profile" },
  ]);
  return runReducer(s, { type: "events", events })!;
}

function rEv(type: string, stage: string | null = null, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: `evt_${Math.random().toString(36).slice(2, 8)}`, run_id: "run_x",
    timestamp: "t", event_type: type as RuntimeEvent["event_type"], stage, skill: null,
    status: null, case_id: "c", artifact_id: null, eval_id: null, repair_attempt: null,
    message: null, data: {}, ...extra,
  };
}

describe("ChatSidebar delete (two-step confirm)", () => {
  it("delete button is always visible; requires confirmation; removes the chat", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ cases: [] })));
    const onDelete = vi.fn();
    const onSelect = vi.fn();
    const { makeChat } = await import("../../state/chatState");
    const a = makeChat("bm-complete-001", "对话A");
    a.messages = [{ kind: "user", id: "u1", at: "t", text: "你好" }];
    const { container } = render(
      <ChatSidebar chats={[a]} activeId={a.id} onSelect={onSelect}
                    onNew={() => {}} onDelete={onDelete} />,
    );
    await waitFor(() => expect(screen.getByText("对话A")).toBeInTheDocument());

    // step 1: ✕ arms confirmation (no deletion yet)
    const del = container.querySelector('[data-testid="delete-chat"]') as HTMLButtonElement;
    expect(del).not.toBeNull();
    fireEvent.click(del);
    expect(onDelete).not.toHaveBeenCalled();
    const confirmBtn = await waitFor(() => screen.getByTestId("confirm-delete-chat"));

    // step 2: confirm deletes
    fireEvent.click(confirmBtn);
    expect(onDelete).toHaveBeenCalledWith(a.id);
  });
});
