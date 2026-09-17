/**
 * ChatLayout — the User-Mode main screen: chat history | conversation | agent
 * inspector. One runtime, one event stream: sending a message maps to a demo
 * case (Portfolio Demo Mode), calls the EXISTING POST /api/runs, and every
 * pixel of progress comes from the SSE RuntimeEvents of that single run.
 */
import { useEffect, useMemo, useReducer, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ConflictInfo } from "../../types/chat";
import { useRunMeta, useRunStream } from "../../hooks/useRunStream";
import {
  chatsReducer,
  loadChats,
  makeChat,
  saveChats,
} from "../../state/chatState";
import { ChatSidebar } from "./ChatSidebar";
import { Conversation } from "./Conversation";
import { Composer } from "./Composer";
import { AgentInspectorPanel } from "../inspector/AgentInspectorPanel";

const REPORT_STAGE = "report-generation";

export function ChatLayout({ onOpenDeveloperMode }: { onOpenDeveloperMode: () => void }) {
  const [chats, dispatch] = useReducer(chatsReducer, undefined, () => {
    const loaded = loadChats();
    return loaded.length > 0 ? loaded : [makeChat()];
  });
  const [activeId, setActiveId] = useState(() => null as string | null);
  const [chatMode, setChatMode] = useState<"agent" | "demo">(() => {
    try {
      return localStorage.getItem("webui:chatMode") === "demo" ? "demo" : "agent";
    } catch {
      return "agent";
    }
  });
  const [agentCfg, setAgentCfg] = useState<{ configured: boolean; provider: string | null } | null>(null);
  const [agentUnavailable, setAgentUnavailable] = useState<string | null>(null);
  useEffect(() => {
    try {
      localStorage.setItem("webui:chatMode", chatMode);
    } catch { /* ignore */ }
  }, [chatMode]);
  useEffect(() => {
    api.agentConfig().then(setAgentCfg).catch(() => setAgentCfg({ configured: false, provider: null }));
  }, []);
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
  const { meta, error: metaError } = useRunMeta(runId);

  const [draft, setDraft] = useState("");
  const [caseId, setCaseId] = useState(active?.caseId ?? "bm-complete-001");
  const [conflict, setConflict] = useState<ConflictInfo | null>(null);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);

  // finalize the transcript once the run reaches its terminal state (idempotent)
  useEffect(() => {
    if (!active || !state?.terminalEvent) return;
    if (state.runId !== active.runId) return;
    const artifactType =
      state.status === "completed"
        ? (state.stageOrder.find((s) => s.id === REPORT_STAGE)?.produces ?? "insurance-report")
        : null;
    if (active.serverChatId) {
      // Agent Mode: the final wording comes from the agent itself (server chat)
      let alive = true;
      void api.getChat(active.serverChatId).then((chat) => {
        if (!alive) return;
        const reply = [...chat.messages].reverse().find(
          (m) => m.role === "assistant" && m.run_id === active.runId,
        );
        dispatch({
          type: "finalizeAgent",
          chatId: active.id,
          runId: state.runId,
          status: state.status === "completed" || state.status === "needs_review"
            || state.status === "waiting" || state.status === "failed"
            ? state.status
            : "failed",
          text: reply?.content ?? "（本轮无回复）",
          artifactType,
          artifactTitle: "客户保险需求分析报告",
        });
      }).catch(() => {
        if (alive) {
          dispatch({ type: "finalizeAgent", chatId: active.id, runId: state.runId,
            status: "failed", text: "无法读取 Agent 回复。", artifactType: null,
            artifactTitle: "" });
        }
      });
      return () => { alive = false; };
    }
    dispatch({
      type: "finalize",
      chatId: active.id,
      runId: state.runId,
      status: state.status === "completed" || state.status === "needs_review"
        || state.status === "waiting" || state.status === "failed"
        ? state.status
        : "failed",
      artifactType,
      artifactTitle: "客户保险需求分析报告",
    });
  }, [active, state?.terminalEvent, state?.runId, state?.status, state?.stageOrder]);

  const send = async (text: string, cid: string) => {
    if (!active) return;
    setConflict(null);
    setAgentUnavailable(null);
    dispatch({ type: "send", chatId: active.id, text, caseId: cid });
    setSending(true);
    try {
      if (chatMode === "agent") {
        let serverChat = active.serverChatId ?? null;
        if (!serverChat) {
          serverChat = (await api.createChat()).chat_id;
          dispatch({ type: "setServerChat", chatId: active.id, serverChatId: serverChat, mode: "agent" });
        }
        const r = await api.postChatMessage(serverChat, text);
        dispatch({ type: "bindRun", chatId: active.id, runId: r.run_id });
      } else {
        const created = await api.createRun(cid);
        dispatch({ type: "bindRun", chatId: active.id, runId: created.run_id });
      }
    } catch (err) {
      const cf = err instanceof ApiError ? err.conflict : null;
      if (cf) {
        const owner = chats.find((c) => c.runId === cf.run_id) ?? null;
        setConflict({ caseId: cf.case_id, runId: cf.run_id, ownerChatId: owner?.id ?? null });
      } else if (err instanceof ApiError && err.status === 503) {
        // LLM provider not configured — fail CLOSED, never a silent demo fallback
        const detail = (err.body as { detail?: { message?: string } })?.detail?.message;
        setAgentUnavailable(detail ?? "LLM provider 未配置。请配置后端环境变量，或切换到演示模式。");
      } else if (err instanceof ApiError && err.status === 409) {
        dispatch({ type: "appendError", chatId: active.id, text: "这个对话已有一轮正在进行的分析，请等它结束后再发送。" });
      } else {
        dispatch({ type: "appendError", chatId: active.id, text: "无法启动分析（后端不可达）。请确认 `python -m runtime.server` 正在运行。" });
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
          <div className="ml-auto flex items-center gap-1.5">
            <div className="flex overflow-hidden rounded-lg border border-slate-200" data-testid="mode-toggle">
              <button
                type="button"
                onClick={() => setChatMode("agent")}
                className={`px-2.5 py-1 text-[11.5px] font-medium ${chatMode === "agent" ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-50"}`}
                data-testid="mode-agent"
              >
                Agent{agentCfg && !agentCfg.configured ? " ·未配置" : ""}
              </button>
              <button
                type="button"
                onClick={() => setChatMode("demo")}
                className={`px-2.5 py-1 text-[11.5px] font-medium ${chatMode === "demo" ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-50"}`}
                data-testid="mode-demo"
              >
                演示 Demo
              </button>
            </div>
            <button
              type="button"
              onClick={() => setInspectorOpen((v) => !v)}
              className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11.5px] font-medium text-slate-600 hover:bg-slate-50 xl:hidden"
              data-testid="toggle-inspector"
            >
              Agent {streaming ? "●" : "○"}
            </button>
            <button
              type="button"
              onClick={onOpenDeveloperMode}
              className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11.5px] font-medium text-slate-600 hover:bg-slate-50"
            >
              ⚙ Developer Mode
            </button>
          </div>
        </div>

        {active ? (
          <>
            {agentUnavailable && chatMode === "agent" ? (
              <div className="border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-[12px] text-amber-800" data-testid="agent-unavailable">
                <p className="font-semibold">Agent Mode 不可用：{agentUnavailable}</p>
                <button
                  type="button"
                  onClick={() => setChatMode("demo")}
                  className="mt-1 rounded border border-amber-300 bg-white px-2 py-0.5 text-[11px] font-medium hover:bg-amber-100"
                >
                  切换到演示模式
                </button>
              </div>
            ) : null}
            <Conversation
              chat={active}
              streamState={state?.runId === active.runId ? state : null}
              streaming={streaming}
              streamError={streamError ?? (metaError && runId ? "无法读取 Run 元数据。" : null)}
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
              mode={chatMode}
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

      {/* right inspector (drawer below xl) */}
      <div className="hidden w-[22rem] shrink-0 overflow-hidden xl:flex">
        {state ? (
          <AgentInspectorPanel meta={meta} state={state} streaming={streaming} error={streamError ?? metaError} />
        ) : (
          <aside className="flex w-full items-center justify-center border-l border-slate-200 bg-slate-50/70 px-6 text-center">
            <p className="text-[12px] text-slate-400">
              发送一个问题后，这里会实时显示 Agent 的运行状态、Pipeline、质量校验与事件轨迹。
            </p>
          </aside>
        )}
      </div>
      {inspectorOpen ? (
        <div className="fixed inset-0 z-40 bg-slate-900/20 xl:hidden" onClick={(e) => e.target === e.currentTarget && setInspectorOpen(false)}>
          <div className="ml-auto h-full w-[22rem] overflow-hidden border-l border-slate-200 bg-slate-50 shadow-xl">
            {state ? (
              <AgentInspectorPanel meta={meta} state={state} streaming={streaming} error={streamError ?? metaError} />
            ) : (
              <p className="p-6 text-[12px] text-slate-400">尚无运行中的 Agent。</p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
