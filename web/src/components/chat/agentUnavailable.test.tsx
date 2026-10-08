/**
 * 28.E-7 Journey F regression: the agent-unavailable banner is CONSUMER
 * COPY ONLY. The backend 503 detail names env vars / provider internals
 * ("LLM_PROVIDER / LLM_MODEL / LLM_API_KEY", "Demo Mode") and must never
 * render on the consumer surface.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatLayout } from "./ChatLayout";

const { api, ApiErrorCtor } = vi.hoisted(() => {
  class ApiError extends Error {
    status: number;
    body: unknown;
    conflict: unknown;
    constructor(status: number, body: unknown) {
      super("api error");
      this.status = status;
      this.body = body;
    }
  }
  return { api: { createChat: vi.fn(), postChatMessage: vi.fn(), getChat: vi.fn() }, ApiErrorCtor: ApiError };
});
vi.mock("../../api/client", () => ({ ApiError: ApiErrorCtor, api }));

describe("agent-unavailable banner (consumer copy only)", () => {
  beforeEach(() => {
    window.location.hash = "#/chat";
    localStorage.clear();
    vi.clearAllMocks();
    api.createChat.mockResolvedValue({ chat_id: "chat_f_t1" });
  });

  it("a poisoned 503 detail never reaches the consumer DOM", async () => {
    api.postChatMessage.mockRejectedValue(
      new ApiErrorCtor(503, {
        detail: {
          message:
            "LLM provider is not configured. Please configure the provider (LLM_PROVIDER / LLM_MODEL / LLM_API_KEY) or switch to Demo Mode.",
        },
      }),
    );
    render(<ChatLayout />);
    const box = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "帮我看看重疾险怎么选" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: false });
    await waitFor(() => {
      expect(screen.getByTestId("agent-unavailable")).toBeInTheDocument();
    });
    const text = screen.getByTestId("agent-unavailable").textContent ?? "";
    expect(text).toContain("暂时无法回答");
    expect(text).toContain("智能服务暂时不可用，请稍后再试。");
    for (const bad of ["LLM", "provider", "LLM_PROVIDER", "API_KEY", "Demo Mode", "503"]) {
      expect(text.includes(bad), `banner must not contain ${bad}`).toBe(false);
    }
  });
});
