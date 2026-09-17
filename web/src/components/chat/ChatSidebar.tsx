import { useEffect, useRef, useState } from "react";
import type { ChatSession } from "../../types/chat";

/**
 * CHAT HISTORY — the left rail (§5). Local persistence V0.1; the session shape
 * is the same one a future backend would own.
 *
 * Delete is a TWO-STEP inline confirm (✕ → 确认删除) so one mis-click can never
 * destroy a whole conversation.
 */
export function ChatSidebar({
  chats,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: {
  chats: ChatSession[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const todayChats = chats.filter((c) => c.updatedAt.slice(0, 10) === today);
  const earlier = chats.filter((c) => c.updatedAt.slice(0, 10) !== today);

  return (
    <div className="flex h-full w-full min-w-0 flex-col" data-testid="chat-sidebar">
      <div className="px-3 py-2.5">
        <button
          type="button"
          onClick={onNew}
          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
          data-testid="new-chat"
        >
          ＋ 新对话
        </button>
      </div>
      <div className="min-h-0 w-full min-w-0 flex-1 overflow-y-auto overflow-x-hidden px-2 pb-3">
        <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
          今天
        </p>
        {todayChats.map((c) => (
          <ChatItem key={c.id} chat={c} active={c.id === activeId}
                    onSelect={onSelect} onDelete={onDelete} />
        ))}
        {earlier.length > 0 ? (
          <>
            <p className="mt-3 px-2 py-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
              更早
            </p>
            {earlier.map((c) => (
              <ChatItem key={c.id} chat={c} active={c.id === activeId}
                        onSelect={onSelect} onDelete={onDelete} />
            ))}
          </>
        ) : null}
        {chats.length === 0 ? (
          <p className="px-2 py-2 text-[11.5px] text-slate-400">还没有对话</p>
        ) : null}
      </div>
    </div>
  );
}

function ChatItem({
  chat: c,
  active,
  onSelect,
  onDelete,
}: {
  chat: ChatSession;
  active: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const armConfirm = () => {
    setConfirming(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setConfirming(false), 3000); // auto-cancel
  };

  return (
    <div
      className={`mb-1 flex min-w-0 items-start gap-1 rounded-lg px-2 py-1.5 ${
        active ? "bg-slate-100" : "hover:bg-slate-50"
      }`}
    >
      <button
        type="button"
        onClick={() => onSelect(c.id)}
        className="min-w-0 flex-1 basis-0 text-left"
        data-testid="chat-item"
        data-active={active}
      >
        <span className="block truncate text-[12.5px] font-medium text-slate-700">{c.title}</span>
        <span className="block truncate text-[11px] text-slate-400">{previewOf(c)}</span>
        <span className="mt-0.5 block font-mono text-[9.5px] text-slate-300">
          {clockOf(c.updatedAt)}
        </span>
      </button>
      {confirming ? (
        <button
          type="button"
          onClick={() => {
            if (timer.current) clearTimeout(timer.current);
            onDelete(c.id);
          }}
          className="mt-1 shrink-0 rounded border border-red-300 bg-red-50 px-1.5 py-0.5 text-[10.5px] font-medium text-red-600 hover:bg-red-100"
          data-testid="confirm-delete-chat"
        >
          确认删除
        </button>
      ) : (
        <button
          type="button"
          onClick={armConfirm}
          className="mt-0.5 shrink-0 rounded px-1 text-[11px] text-slate-300 opacity-60 transition-opacity hover:text-red-500 hover:opacity-100 focus:opacity-100"
          aria-label="删除对话"
          title="删除对话"
          data-testid="delete-chat"
        >
          ✕
        </button>
      )}
    </div>
  );
}

function previewOf(c: ChatSession): string {
  const last = c.messages[c.messages.length - 1];
  if (!last) return "新对话";
  if (last.kind === "user" || last.kind === "assistant") return last.text.replace(/[#*`>|-]/g, "").slice(0, 30);
  if (last.kind === "artifact") return "📄 " + last.title;
  return "Agent 运行";
}

function clockOf(iso: string): string {
  const t = iso.indexOf("T");
  return t >= 0 ? iso.slice(0, 10) + " " + iso.slice(t + 1, t + 6) : iso;
}
