/**
 * B-03 regression (28.F-1): a NEW consumer must NEVER be fabricated a
 * conversation history — no seeded chats, no fake artifacts/preview
 * chrome — while existing real conversations persist, and the developer
 * demo capability (seedChats export) stays intact outside the consumer
 * path.
 *
 * Case A new consumer / Case B existing user / Case C demo capability
 * preserved / Case D refresh / Case E reopen.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { chatStorageKey } from "../../state/chatState";

vi.mock("../../api/client", () => {
  class ApiError extends Error {
    status = 0;
    body: unknown = null;
    conflict: unknown = null;
  }
  return {
    ApiError,
    api: {
      agentConfig: vi.fn().mockResolvedValue({ configured: true, provider: "glm" }),
      whoami: vi.fn().mockResolvedValue({ subject: null, role: null, mode: "local-dev" }),
      getChat: vi.fn().mockResolvedValue({ messages: [] }),
      approvals: vi.fn().mockResolvedValue({ approvals: [] }),
      streamUrl: vi.fn(() => "/api/runs/x/stream"),
    },
  };
});

const SEED_TITLES = ["给孩子买重疾险", "一家三口保障分析", "百万医疗险够不够"];

describe("B-03 — no fabricated history for new consumers (28.F-1)", () => {
  beforeEach(() => {
    window.location.hash = "#/chat";
    localStorage.clear();
    vi.stubGlobal(
      "EventSource",
      class {
        close() {}
        addEventListener() {}
        removeEventListener() {}
      },
    );
  });

  it("Case A: a brand-new consumer sees an EMPTY history — zero seeded chats, zero fake previews", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-layout")).toBeInTheDocument());
    for (const title of SEED_TITLES) {
      expect(screen.queryByText(new RegExp(title))).toBeNull();
    }
    expect(container.textContent).not.toContain("重新发送即可再次运行完整分析链路"); // seeded canned reply
    expect(screen.queryAllByText("删除对话").length).toBe(0); // nothing listed to delete
    // the empty-state conversation canvas is present (welcome, not history)
    expect(screen.getByTestId("chat-layout")).toBeInTheDocument();
  });

  it("Case B: an EXISTING user's real conversations are preserved", async () => {
    localStorage.setItem(
      chatStorageKey(),
      JSON.stringify({
        version: 1,
        chats: [
          {
            id: "chat_real_1",
            title: "我的真实提问",
            caseId: "bm-complete-001",
            runId: null,
            serverChatId: null,
            mode: "agent",
            createdAt: "2026-09-26T00:00:00.000Z",
            updatedAt: "2026-09-26T00:00:00.000Z",
            messages: [
              { kind: "user", id: "u1", at: "t", text: "我的真实提问内容" },
              { kind: "assistant", id: "a1", at: "t", text: "真实回答" },
            ],
          },
        ],
      }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getAllByText("我的真实提问").length).toBeGreaterThan(0));
    expect(screen.getAllByText("真实回答").length).toBeGreaterThan(0);
  });

  it("Case C: the developer demo capability (seedChats) still exists — outside the consumer path", async () => {
    const { seedChats } = await import("../../state/chatState");
    const demo = seedChats();
    expect(demo.length).toBeGreaterThanOrEqual(3); // capability preserved
    // ...but the consumer loader never calls it (source-level guarantee)
    const { loadChats } = await import("../../state/chatState");
    expect(loadChats.toString().includes("seedChats")).toBe(false);
  });

  it("Case D: refresh does not conjure history (remount keeps new-user empty)", async () => {
    const first = render(<App />);
    expect(screen.queryByText(SEED_TITLES[0]!)).toBeNull();
    first.unmount();

    render(<App />); // refresh equivalent
    for (const title of SEED_TITLES) {
      expect(screen.queryByText(new RegExp(title))).toBeNull();
    }
  });

  it("Case E: close + reopen still shows no fabricated history", async () => {
    const first = render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-layout")).toBeInTheDocument());
    fireEvent.click(screen.getByText("＋ 新对话")); // user interacts with a real empty chat
    first.unmount();

    render(<App />);
    await waitFor(() => expect(screen.getAllByText("新对话").length).toBeGreaterThan(0));
    for (const title of SEED_TITLES) {
      expect(screen.queryByText(new RegExp(title))).toBeNull();
    }
  });
});
