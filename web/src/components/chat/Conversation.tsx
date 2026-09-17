import { useEffect, useRef } from "react";
import type { ChatSession, ConflictInfo } from "../../types/chat";
import type { RunUiState } from "../../state/runReducer";
import { MessageView } from "./Message";
import { AgentActivity } from "./AgentActivity";
import { ArtifactCard } from "./ArtifactCard";
import { WelcomeScreen } from "./WelcomeScreen";

/**
 * CONVERSATION — the main chat area: stored transcript (user / assistant /
 * artifact) + the LIVE activity card for the current run. The activity card is
 * never persisted: it is re-derived from the runtime's event stream on attach,
 * so a page refresh rebuilds it identically.
 */
export function Conversation({
  chat,
  streamState,
  streaming,
  streamError,
  conflict,
  onOpenConflictOwner,
  onPickPrompt,
}: {
  chat: ChatSession;
  streamState: RunUiState | null;
  streaming: boolean;
  streamError: string | null;
  conflict: ConflictInfo | null;
  onOpenConflictOwner: (chatId: string) => void;
  onPickPrompt: (text: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const eventCount = streamState?.events.length ?? 0;

  useEffect(() => {
    // jsdom does not implement scrollIntoView — guard instead of crash in tests
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ block: "end" });
    }
  }, [chat.messages.length, eventCount, streaming]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto" data-testid="chat-conversation">
      {chat.messages.length === 0 ? (
        <WelcomeScreen onPick={onPickPrompt} />
      ) : (
        <div className="mx-auto max-w-3xl space-y-1 px-4 py-5">
          {conflict ? (
            <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-800" data-testid="chat-conflict">
              <p className="font-semibold">这个演示 case 已有正在进行的运行。</p>
              <p className="mt-0.5 font-mono text-[10.5px]">Run: {conflict.runId}</p>
              {conflict.ownerChatId !== null ? (
                <button
                  type="button"
                  onClick={() => onOpenConflictOwner(conflict.ownerChatId as string)}
                  className="mt-1.5 rounded border border-amber-300 bg-white px-2.5 py-1 text-[11.5px] font-medium hover:bg-amber-100"
                >
                  打开正在分析的对话
                </button>
              ) : (
                <p className="mt-1 text-[11px] opacity-80">它由当前后端会话中的其他入口启动（可在 Developer Mode 查看）。</p>
              )}
            </div>
          ) : null}

          {chat.messages.map((m) => {
            if (m.kind === "activity") {
              const isLive = streamState != null && m.runId === chat.runId;
              if (isLive) {
                return <AgentActivity key={m.id} state={streamState} caseId={m.caseId} streaming={streaming} />;
              }
              return (
                <div key={m.id} className="my-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[12px] text-slate-400" data-testid="stale-activity">
                  ✦ 此对话的历史运行已结束（或属于已重启的后端会话）。重新发送即可再次运行完整分析。
                </div>
              );
            }
            if (m.kind === "artifact") {
              return <ArtifactCard key={m.id} runId={m.runId} artifactType={m.artifactType} title={m.title} />;
            }
            return <MessageView key={m.id} message={m} />;
          })}

          {streamError ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-[12.5px] text-red-700" data-testid="stream-error">
              {streamError}
            </div>
          ) : null}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
