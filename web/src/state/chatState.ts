/**
 * Chat sessions state — pure reducer + localStorage persistence (V0.1).
 *
 * Persistence is deliberately a versioned envelope ({version, chats}) so a real
 * backend can adopt the same shape later. What is NOT persisted: live agent
 * activity (always re-derived from the runtime's event stream), because the
 * runtime — not the chat — owns execution state.
 */
import type { ChatSession, ChatStore, Message } from "../types/chat";

const STORAGE_KEY = "webui:chats:v1";

export const DEMO_CASES: { id: string; label: string; desc: string }[] = [
  { id: "bm-complete-001", label: "家庭基础分析", desc: "基准客户：35岁/已婚/1孩/房贷" },
  { id: "bm-complete-006-single-medical", label: "单需求·医疗", desc: "仅医疗保障需求" },
  { id: "bm-complete-007-single-accident", label: "单需求·意外", desc: "仅意外保障需求" },
  { id: "bm-highrisk-001", label: "高风险客户", desc: "健康风险较高" },
  { id: "bm-noev-001", label: "证据不足(失败演示)", desc: "空知识库 → NEEDS_REVIEW" },
];

/** prompt → demo case (Portfolio Demo Mode; UI-level metadata only). */
export function mapPromptToCase(text: string): string {
  const t = text.toLowerCase();
  const has = (...ws: string[]) => ws.some((w) => t.includes(w));
  if (has("意外", "磕碰", "摔")) return "bm-complete-007-single-accident";
  if (has("医疗", "百万医疗", "住院", "报销")) return "bm-complete-006-single-medical";
  if (has("高风险", "体检", "结节", "血压")) return "bm-highrisk-001";
  if (has("证据", "知识库", "检索失败")) return "bm-noev-001";
  // 重疾 / 孩子 / 家庭 / 缺口 / 一家三口 … → 基准家庭分析
  return "bm-complete-001";
}

export function newChatId(): string {
  return "chat_" + Math.random().toString(36).slice(2, 10);
}

function now(): string {
  return new Date().toISOString();
}

export function makeChat(caseId = "bm-complete-001", title = "新对话"): ChatSession {
  const t = now();
  return { id: newChatId(), title, caseId, runId: null, messages: [], createdAt: t, updatedAt: t };
}

/** First-load seed: a few demo conversations (transcripts only, no runs). */
export function seedChats(): ChatSession[] {
  const mk = (title: string, caseId: string, user: string, reply: string): ChatSession => {
    const c = makeChat(caseId, title);
    const at = new Date(Date.now() - 3600_000).toISOString();
    c.messages = [
      { kind: "user", id: "m1", at, text: user },
      { kind: "assistant", id: "m2", at, text: reply },
    ];
    return c;
  };
  return [
    mk("给孩子买重疾险", "bm-complete-001", "我想给4岁的孩子买一份重疾险。",
       "这需要先看清家庭整体责任与预算，再决定孩子的保障优先级。打开这段对话重新发送，我会跑一遍完整分析链路。"),
    mk("一家三口保障分析", "bm-complete-001", "一家三口需要哪些保险？",
       "一家三口的配置顺序通常是：先保障家庭经济支柱，再覆盖高额医疗与重疾责任。重新发送即可运行完整分析。"),
    mk("百万医疗险够不够", "bm-complete-006-single-medical", "我的百万医疗险够不够用？",
       "百万医疗险解决的是住院报销，不覆盖收入损失与康复费用。重新发送，我会针对医疗单需求跑一遍分析。"),
  ];
}

export function loadChats(): ChatSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return seedChats();
    const store = JSON.parse(raw) as ChatStore;
    if (store?.version !== 1 || !Array.isArray(store.chats)) return seedChats();
    return store.chats;
  } catch {
    return seedChats();
  }
}

export function saveChats(chats: ChatSession[]): void {
  try {
    const store: ChatStore = { version: 1, chats };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* storage unavailable — chat history degrades to in-memory */
  }
}

export function clearStoredChats(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

// --------------------------------------------------------------------------- #
// reducer
// --------------------------------------------------------------------------- #
export type ChatAction =
  | { type: "create"; chat: ChatSession }
  | { type: "delete"; chatId: string }
  | { type: "rename"; chatId: string; title: string }
  | { type: "send"; chatId: string; text: string; caseId: string }
  | { type: "bindRun"; chatId: string; runId: string }
  | { type: "setServerChat"; chatId: string; serverChatId: string; mode: "agent" | "demo" }
  | {
      type: "finalize";
      chatId: string;
      runId: string;
      status: "completed" | "needs_review" | "waiting" | "failed";
      artifactType: string | null;
      artifactTitle: string;
    }
  | {
      /** Agent Mode: the final assistant text comes from the agent itself. */
      type: "finalizeAgent";
      chatId: string;
      runId: string;
      status: "completed" | "needs_review" | "waiting" | "failed";
      text: string;
      artifactType: string | null;
      artifactTitle: string;
    }
  | { type: "appendError"; chatId: string; text: string };

export function chatsReducer(chats: ChatSession[], action: ChatAction): ChatSession[] {
  const touch = (c: ChatSession): ChatSession => ({ ...c, updatedAt: now() });
  const mapChat = (id: string, fn: (c: ChatSession) => ChatSession): ChatSession[] =>
    chats.map((c) => (c.id === id ? touch(fn(c)) : c));

  switch (action.type) {
    case "create":
      return [action.chat, ...chats];
    case "delete":
      return chats.filter((c) => c.id !== action.chatId);
    case "rename":
      return mapChat(action.chatId, (c) => ({ ...c, title: action.title }));
    case "send": {
      const msg: Message = { kind: "user", id: "u" + Date.now() + Math.random().toString(36).slice(2, 6), at: now(), text: action.text };
      return mapChat(action.chatId, (c) => ({
        ...c,
        caseId: action.caseId,
        runId: null, // a new request supersedes any previous run reference
        title: c.messages.length === 0 ? action.text.slice(0, 24) : c.title,
        messages: [...c.messages, msg],
      }));
    }
    case "bindRun": {
      const msg: Message = {
        kind: "activity", id: "act-" + action.runId, at: now(),
        runId: action.runId, caseId: chats.find((c) => c.id === action.chatId)?.caseId ?? "",
      };
      return mapChat(action.chatId, (c) => ({
        ...c,
        runId: action.runId,
        messages: [...c.messages, msg],
      }));
    }
    case "setServerChat":
      return mapChat(action.chatId, (c) => ({
        ...c, serverChatId: action.serverChatId, mode: action.mode,
      }));
    case "finalizeAgent": {
      const chat = chats.find((c) => c.id === action.chatId);
      if (!chat) return chats;
      if (chat.messages.some((m) => m.id === "fin-" + action.runId)) return chats;
      const msgs: Message[] = [
        { kind: "assistant", id: "fin-" + action.runId, at: now(), text: action.text },
      ];
      if (action.artifactType) {
        msgs.push({
          kind: "artifact", id: "art-" + action.runId, at: now(),
          runId: action.runId, artifactType: action.artifactType,
          title: action.artifactTitle,
        });
      }
      return mapChat(action.chatId, (c) => ({ ...c, messages: [...c.messages, ...msgs] }));
    }
    case "finalize": {
      const chat = chats.find((c) => c.id === action.chatId);
      if (!chat) return chats;
      // idempotent: finalizing the same run twice must not duplicate messages
      if (chat.messages.some((m) => m.id === "fin-" + action.runId)) return chats;
      const finalText = finalAssistantText(action.status);
      const msgs: Message[] = [
        { kind: "assistant", id: "fin-" + action.runId, at: now(), text: finalText },
      ];
      if (action.artifactType) {
        msgs.push({
          kind: "artifact", id: "art-" + action.runId, at: now(),
          runId: action.runId, artifactType: action.artifactType, title: action.artifactTitle,
        });
      }
      return mapChat(action.chatId, (c) => ({ ...c, messages: [...c.messages, ...msgs] }));
    }
    case "appendError":
      return mapChat(action.chatId, (c) => ({
        ...c,
        messages: [...c.messages, { kind: "assistant", id: "err" + Date.now(), at: now(), text: action.text }],
      }));
    default:
      return chats;
  }
}

/** Honest final replies — no invented analysis, status comes from the runtime. */
export function finalAssistantText(status: "completed" | "needs_review" | "waiting" | "failed"): string {
  switch (status) {
    case "completed":
      return "分析完成。我整理了一份《客户保险需求分析报告》——结论、依据与证据来源都在报告里，可以直接查看。";
    case "needs_review":
      return "这次分析没有得出可以放心交付的结论：自动修复仍未通过质量校验，我已停止并标记为**需要人工复核**。没有把握的推荐不会出现在结果里。";
    case "waiting":
      return "当前资料还不足以继续：关键客户信息缺失或存在冲突。请补充信息后再发起一次分析。";
    case "failed":
      return "本次运行失败了。可以在 Developer Mode 中查看完整事件轨迹定位原因。";
  }
}
