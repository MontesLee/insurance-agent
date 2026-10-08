/**
 * 28.G consumer identity & isolation — frontend boundary tests.
 *
 * * 401 (keys mode, no/invalid credential) surfaces the identity gate
 * * a valid credential resolves the SERVER subject and enters the chat
 * * conversations are stored PER SUBJECT — switching identity never
 *   shows another subject's local transcripts (no cross-user residue)
 * * the deep link #/report/{opaque-ref} renders via the ownership-checked
 *   consumer endpoint (never a raw run id)
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { CONSUMER_KEY_STORAGE } from "../../api/client";
import {
  chatStorageKey,
  clearStoredChats,
  loadChats,
  saveChats,
  setChatStorageScope,
} from "../../state/chatState";

const { whoami, artifactByRef } = vi.hoisted(() => ({
  whoami: vi.fn(),
  artifactByRef: vi.fn(),
}));
vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    api: { ...actual.api, whoami, artifactByRef },
  };
});

describe("consumer identity gate (28.G)", () => {
  beforeEach(() => {
    window.location.hash = "#/chat";
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("an unauthenticated visitor (keys mode) meets the gate, not the chat", async () => {
    whoami.mockImplementationOnce(
      () =>
        new Promise<never>((_, reject) => {
          // mirror the real client: the 401 event fires asynchronously,
          // AFTER the hook has registered its listener
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent("webui:unauthorized"));
            reject(new Error("401"));
          }, 0);
        }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("identity-gate")).toBeInTheDocument());
    expect(screen.queryByTestId("chat-layout")).toBeNull();
  });

  it("a valid credential resolves the SERVER subject and enters the chat", async () => {
    localStorage.setItem(CONSUMER_KEY_STORAGE, "kkkkkkkkkkkkkkkk");
    whoami.mockResolvedValue({
      subject: "consumer:alice", role: "CONSUMER", mode: "authenticated",
    });
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-layout")).toBeInTheDocument());
    expect(screen.getByTestId("sign-out")).toBeInTheDocument(); // subject present
  });

  it("storage is scoped per subject — switching identity shows nothing of the previous user", () => {
    // alice has a local transcript…
    setChatStorageScope("consumer:alice");
    saveChats([
      { id: "c1", title: "alice 的对话", caseId: "x", runId: null,
        serverChatId: null, mode: "agent",
        createdAt: "t", updatedAt: "t", messages: [] },
    ]);
    expect(localStorage.getItem(chatStorageKey("consumer:alice"))).toContain("alice 的对话");

    // …bob's scope does NOT contain it
    setChatStorageScope("consumer:bob");
    expect(loadChats()).toEqual([]);
    expect(localStorage.getItem(chatStorageKey("consumer:bob"))).toBeNull();

    // back to alice — her transcript is intact; sign-out clears only hers
    setChatStorageScope("consumer:alice");
    expect(loadChats()[0]!.title).toBe("alice 的对话");
    clearStoredChats();
    expect(loadChats()).toEqual([]);
    setChatStorageScope("local");
  });

  it("local-dev mode (no keys) renders the chat with no gate", async () => {
    whoami.mockResolvedValue({ subject: null, role: null, mode: "local-dev" });
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-layout")).toBeInTheDocument());
    expect(screen.queryByTestId("identity-gate")).toBeNull();
  });
});

describe("consumer deep link #/report/{ref} (D-05′)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    whoami.mockResolvedValue({
      subject: "consumer:alice", role: "CONSUMER", mode: "authenticated",
    });
  });

  it("renders an opaque-ref report via the ownership-checked endpoint", async () => {
    artifactByRef.mockResolvedValue({
      artifact: {
        artifact_type: "insurance-report",
        payload: { rendered_report: "# 客户保险需求分析报告\n\n- 深链结论" },
      },
    });
    window.location.hash = "#/report/ar_abc123def456";
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("ref-report")).toBeInTheDocument());
    expect(await screen.findByText(/深链结论/)).toBeInTheDocument();
    expect(artifactByRef).toHaveBeenCalledWith("ar_abc123def456");
    // the URL carries ONLY the opaque ref — never a run id
    expect(window.location.hash).not.toMatch(/run_/);
  });

  it("a non-owning/invalid ref shows a consumer-safe refusal", async () => {
    artifactByRef.mockRejectedValue(new Error("404"));
    window.location.hash = "#/report/ar_notyours";
    render(<App />);
    await waitFor(() => expect(screen.getByText(/无法打开这份报告/)).toBeInTheDocument());
  });
});
