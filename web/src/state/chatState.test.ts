import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  chatsReducer,
  clearStoredChats,
  finalAssistantText,
  loadChats,
  makeChat,
  mapPromptToCase,
  saveChats,
} from "./chatState";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});
afterEach(() => clearStoredChats());

describe("prompt → demo case mapping (Portfolio Demo Mode)", () => {
  it("maps family/child/critical-illness prompts to the baseline family case", () => {
    expect(mapPromptToCase("给孩子配置重疾险前，我应该先考虑什么？")).toBe("bm-complete-001");
    expect(mapPromptToCase("一家三口需要哪些保险？")).toBe("bm-complete-001");
    expect(mapPromptToCase("帮我看看家庭保障有没有明显缺口")).toBe("bm-complete-001");
  });
  it("maps medical / accident / high-risk / evidence prompts to their cases", () => {
    expect(mapPromptToCase("我的百万医疗险和重疾险有什么区别？")).toBe("bm-complete-006-single-medical");
    expect(mapPromptToCase("老人意外磕碰怎么保？")).toBe("bm-complete-007-single-accident");
    expect(mapPromptToCase("体检查出结节，还能买吗")).toBe("bm-highrisk-001");
    expect(mapPromptToCase("知识库检索失败会怎样")).toBe("bm-noev-001");
  });
});

describe("chats reducer", () => {
  it("send: appends user message, sets title from the first message, resets runId", () => {
    const c = makeChat("bm-complete-001", "新对话");
    let chats = [c];
    chats = chatsReducer(chats, { type: "send", chatId: c.id, text: "我想给4岁的孩子买一份重疾险。", caseId: "bm-complete-001" });
    const chat = chats[0]!;
    expect(chat.messages).toHaveLength(1);
    expect(chat.messages[0]).toMatchObject({ kind: "user", text: "我想给4岁的孩子买一份重疾险。" });
    expect(chat.title).toBe("我想给4岁的孩子买一份重疾险。".slice(0, 24));
    expect(chat.caseId).toBe("bm-complete-001");
    // second send keeps the original title
    chats = chatsReducer(chats, { type: "send", chatId: c.id, text: "第二个问题", caseId: "bm-complete-001" });
    expect(chats[0]!.title).toBe("我想给4岁的孩子买一份重疾险。".slice(0, 24));
    expect(chats[0]!.messages).toHaveLength(2);
  });

  it("bindRun appends the live activity message and points the chat at the run", () => {
    const c = makeChat();
    let chats = [c];
    chats = chatsReducer(chats, { type: "send", chatId: c.id, text: "hi", caseId: "bm-complete-001" });
    chats = chatsReducer(chats, { type: "bindRun", chatId: c.id, runId: "run_abc" });
    expect(chats[0]!.runId).toBe("run_abc");
    expect(chats[0]!.messages[1]).toMatchObject({ kind: "activity", runId: "run_abc" });
  });

  it("finalize appends the final assistant message + artifact card, idempotently", () => {
    const c = makeChat();
    let chats = [c];
    const fin = {
      type: "finalize" as const,
      chatId: c.id,
      runId: "run_abc",
      status: "completed" as const,
      artifactType: "insurance-report",
      artifactTitle: "客户保险需求分析报告",
    };
    chats = chatsReducer(chats, fin);
    const m = chats[0]!.messages;
    expect(m).toHaveLength(2);
    expect(m[0]).toMatchObject({ kind: "assistant", id: "fin-run_abc" });
    expect(m[1]).toMatchObject({ kind: "artifact", artifactType: "insurance-report" });
    // replaying the same finalize (e.g. after refresh) must not duplicate
    chats = chatsReducer(chats, fin);
    expect(chats[0]!.messages).toHaveLength(2);
  });

  it("finalize for needs_review / waiting / failed carries honest wording, no artifact", () => {
    for (const status of ["needs_review", "waiting", "failed"] as const) {
      const c = makeChat();
      const chats = chatsReducer([c], {
        type: "finalize", chatId: c.id, runId: "r1", status, artifactType: null, artifactTitle: "",
      });
      expect(chats[0]!.messages).toHaveLength(1);
      expect(chats[0]!.messages[0]!.kind).toBe("assistant");
    }
    expect(finalAssistantText("needs_review")).toContain("需要人工复核");
    expect(finalAssistantText("completed")).toContain("报告");
  });

  it("delete removes the chat; appendError adds an assistant message", () => {
    const a = makeChat(), b = makeChat();
    let chats = [a, b];
    chats = chatsReducer(chats, { type: "delete", chatId: a.id });
    expect(chats.map((c) => c.id)).toEqual([b.id]);
    chats = chatsReducer(chats, { type: "appendError", chatId: b.id, text: "后端不可达" });
    expect(chats[0]!.messages.at(-1)).toMatchObject({ kind: "assistant", text: "后端不可达" });
  });
});

describe("local persistence (V0.1, backend-shaped envelope)", () => {
  it("seeds demo conversations on first load", () => {
    const seeded = loadChats();
    expect(seeded.length).toBeGreaterThanOrEqual(3);
    expect(seeded[0]!.title.length).toBeGreaterThan(0);
  });
  it("round-trips through the versioned envelope", () => {
    const c = makeChat();
    c.messages = [{ kind: "user", id: "u1", at: "t", text: "round trip" }];
    saveChats([c]);
    const loaded = loadChats();
    expect(loaded).toHaveLength(1);
    expect(loaded[0]!.messages[0]).toMatchObject({ kind: "user", text: "round trip" });
  });
  it("falls back to seeds on corrupted storage", () => {
    localStorage.setItem("webui:chats:v1", "{not json");
    expect(loadChats().length).toBeGreaterThanOrEqual(3);
  });
});
