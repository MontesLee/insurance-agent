/**
 * ChatLayout — the CONSUMER chat screen (Phase 28.E-1): chat history |
 * conversation | composer. One runtime, one event stream: the agent path
 * posts the user's text to the EXISTING chat API and every pixel of
 * progress comes from the SSE RuntimeEvents of that single run.
 *
 * Consumer-space composition: no runtime inspector, no Agent/Demo mode
 * toggle, no developer entry (those live behind internal routes now —
 * see app/route.ts + shell/). Demo-case execution remains available in
 * the developer console only.
 */
import { useEffect, useMemo, useReducer, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ConflictInfo } from "../../types/chat";
import { useRunStream } from "../../hooks/useRunStream";
import {
  chatsReducer,
  loadChats,
  makeChat,
  saveChats,
} from "../../state/chatState";
import { ChatSidebar } from "./ChatSidebar";
import { Conversation } from "./Conversation";
import { Composer } from "./Composer";
import { consumerFallbackText, consumerFinalizeArtifact, consumerTerminalView } from "../../state/consumerView";
import { markSubmit } from "../../perf/chatPerf";

export function ChatLayout() {
  const [chats, dispatch] = useReducer(chatsReducer, undefined, () => {
    const loaded = loadChats();
    return loaded.length > 0 ? loaded : [makeChat()];
  });
  const [activeId, setActiveId] = useState(() => null as string | null);
  const [agentUnavailable, setAgentUnavailable] = useState<string | null>(null);
  const active = useMemo(
    () => chats.find((c) => c.id === activeId) ?? chats[0] ?? null,
    [chats, activeId],
  );
  useEffect(() => {
    if (!activeId && active) setActiveId(active.id);
  }, [activeId, active]);
  useEffect(() => saveChats(chats), [chats]);

  const runId = active?.runId ?? null;
  const { state, error: streamError, streaming, viewStopped, stop, resume } = useRunStream(runId);

  const [draft, setDraft] = useState("");
  const [caseId, setCaseId] = useState(active?.caseId ?? "bm-complete-001");
  const [conflict, setConflict] = useState<ConflictInfo | null>(null);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // finalize the transcript once the run reaches its terminal state (idempotent)
  useEffect(() => {
    if (!active || !state?.terminalEvent) return;
    if (state.runId !== active.runId) return;
    // 28.E-2: Completion ≠ Artifact — the card requires a REAL report
    // artifact in this run (artifact_created for the report stage), never
    // a terminal status alone. QA turns have none → no report card.
    const artifact = consumerFinalizeArtifact(state);
    // 28.E-5: deterministic terminal presentation — the final wording is
    // the agent's own text when safe, else a conservative fallback; the
    // internal result_status classifies answer vs honest refusal.
    const status = state.status === "completed" || state.status === "needs_review"
      || state.status === "waiting" || state.status === "failed"
      ? state.status
      : "failed";
    const resultStatus = (state.terminalEvent?.data?.["result_status"] as string | undefined) ?? null;
    // 28.K.20 (T5): if the run FAILED mid-stream, any safely-streamed
    // content is retained and paired with the failure copy — never raw
    // errors. run_failed does not clear the stream buffer, so the partial
    // content survives to this point by construction. (needs_review keeps
    // its K.1 fixed copy — that contract deliberately maps system
    // templates away; not altered here.)
    const PARTIAL_FAILURE_SUFFIX = "这次回答没有完整生成，请稍后重试。";
    const partialStream = state.stream?.kind === "content"
      ? (state.stream.text || "").trim() : "";
    const finalizeWith = (replyText: string | null | undefined) => {
      let text = replyText;
      if (!text && status === "failed" && partialStream) {
        text = partialStream + "\n\n" + PARTIAL_FAILURE_SUFFIX;
      }
      return consumerTerminalView(status, resultStatus, text, artifact !== null);
    };
    if (active.serverChatId) {
      // Agent Mode: the final wording comes from the agent itself (server chat)
      let alive = true;
      void api.getChat(active.serverChatId).then((chat) => {
        if (!alive) return;
        const reply = [...chat.messages].reverse().find(
          (m) => m.role === "assistant" && m.run_id === active.runId,
        );
        const terminal = finalizeWith(reply?.content);
        dispatch({
          type: "finalizeAgent",
          chatId: active.id,
          runId: state.runId,
          status,
          text: terminal.message,
          artifactType: artifact?.artifactType ?? null,
          artifactTitle: artifact?.title ?? "",
        });
      }).catch(() => {
        if (alive) {
          dispatch({ type: "finalizeAgent", chatId: active.id, runId: state.runId,
            status: "failed", text: consumerFallbackText("error"), artifactType: null,
            artifactTitle: "" });
        }
      });
      return () => { alive = false; };
    }
    dispatch({
      type: "finalize",
      chatId: active.id,
      runId: state.runId,
      status,
      artifactType: artifact?.artifactType ?? null,
      artifactTitle: artifact?.title ?? "",
    });
  }, [active, state?.terminalEvent, state?.runId, state?.status, state?.stageOrder]);

  const send = async (text: string, cid: string) => {
    if (!active) return;
    markSubmit(); // 28.K.28 perf mark (passive, T0)
    setConflict(null);
    setAgentUnavailable(null);
    dispatch({ type: "send", chatId: active.id, text, caseId: cid });
    setSending(true);
    try {
      let serverChat = active.serverChatId ?? null;
      if (!serverChat) {
        serverChat = (await api.createChat()).chat_id;
        dispatch({ type: "setServerChat", chatId: active.id, serverChatId: serverChat, mode: "agent" });
      }
      const r = await api.postChatMessage(serverChat, text);
      dispatch({ type: "bindRun", chatId: active.id, runId: r.run_id });
    } catch (err) {
      const cf = err instanceof ApiError ? err.conflict : null;
      if (cf) {
        const owner = chats.find((c) => c.runId === cf.run_id) ?? null;
        setConflict({ caseId: cf.case_id, runId: cf.run_id, ownerChatId: owner?.id ?? null });
      } else if (err instanceof ApiError && err.status === 503) {
        // LLM provider not configured — fail CLOSED, never a silent
        // fallback. Consumer copy ONLY (28.E-7 Journey F): the backend
        // detail names env vars/provider internals and must not render.
        setAgentUnavailable("智能服务暂时不可用，请稍后再试。");
      } else if (err instanceof ApiError && err.status === 409) {
        dispatch({ type: "appendError", chatId: active.id, text: "这个对话已有一轮正在进行的分析，请等它结束后再发送。" });
      } else {
        dispatch({ type: "appendError", chatId: active.id, text: "暂时无法连接服务，请稍后再试。" });
      }
    } finally {
      setSending(false);
    }
  };

  const newChat = () => {
    const c = makeChat(caseId);
    dispatch({ type: "create", chat: c });
    setActiveId(c.id);
    setDraft("");
    setConflict(null);
    setSidebarOpen(false);
  };

  const busy = sending || streaming || (state != null && (state.status === "running" || state.status === "queued"));

  return (
    <div className="flex h-full min-h-0" data-testid="chat-layout">
      {/* left rail (drawer below lg) */}
      <div className="hidden w-60 shrink-0 overflow-hidden border-r border-slate-200 bg-slate-50/70 lg:flex">
        <ChatSidebar
          chats={chats}
          activeId={active?.id ?? null}
          onSelect={(id) => setActiveId(id)}
          onNew={newChat}
          onDelete={(id) => dispatch({ type: "delete", chatId: id })}
        />
      </div>
      {sidebarOpen ? (
        <div className="fixed inset-0 z-40 bg-slate-900/20 lg:hidden" onClick={(e) => e.target === e.currentTarget && setSidebarOpen(false)}>
          <div className="h-full w-64 overflow-hidden border-r border-slate-200 bg-slate-50 shadow-xl">
            <ChatSidebar
              chats={chats}
              activeId={active?.id ?? null}
              onSelect={(id) => { setActiveId(id); setSidebarOpen(false); }}
              onNew={newChat}
              onDelete={(id) => dispatch({ type: "delete", chatId: id })}
            />
          </div>
        </div>
      ) : null}

      {/* center column */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-2">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-100 lg:hidden"
            aria-label="对话列表"
          >
            ☰
          </button>
          <p className="truncate text-[13px] font-semibold text-slate-700">
            {active?.title ?? "新对话"}
          </p>
          {streaming ? (
            <span className="flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[10.5px] font-medium text-blue-600">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
              Agent 运行中
            </span>
          ) : null}
          <div className="ml-auto" />
        </div>

        {active ? (
          <>
            {agentUnavailable ? (
              <div className="border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-[12px] text-amber-800" data-testid="agent-unavailable">
                <p className="font-semibold">暂时无法回答：{agentUnavailable}</p>
              </div>
            ) : null}
            <Conversation
              chat={active}
              streamState={state?.runId === active.runId ? state : null}
              streaming={streaming}
              streamError={streamError}
              conflict={conflict}
              onOpenConflictOwner={(id) => { setActiveId(id); setConflict(null); }}
              onPickPrompt={(text) => setDraft(text)}
            />
            <Composer
              disabled={busy}
              streaming={streaming}
              viewStopped={viewStopped}
              onStopViewing={stop}
              onResumeViewing={resume}
              onSend={(text, cid) => void send(text, cid)}
              draft={draft}
              setDraft={setDraft}
              caseId={caseId}
              setCaseId={setCaseId}
              mode="agent"
            />
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <button type="button" onClick={newChat} className="rounded-lg bg-slate-800 px-4 py-2 text-[13px] font-medium text-white">
              开始新对话
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
