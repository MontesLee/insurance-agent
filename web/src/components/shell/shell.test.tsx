/**
 * Three-space application shell (Phase 28.E-1).
 *
 * Covers: consumer default entry, consumer isolation (no internal
 * entries / no runtime inspector in the consumer surface), direct-URL
 * access to internal spaces, hash back/forward navigation, retirement
 * of the legacy localStorage mode key, and conversation persistence
 * across remount (refresh).
 *
 * The API client is mocked: these tests exercise the SHELL boundary,
 * not the runtime (runtime reuse is covered by the reducer/SSE suites
 * and the env-gated E2E chat-flow test).
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { navigate, ROUTES } from "../../app/route";

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
      approvals: vi.fn().mockResolvedValue({ approvals: [] }),
      reviewCard: vi.fn().mockRejectedValue(new Error("not loaded")),
      createChat: vi.fn().mockResolvedValue({ chat_id: "chat_shell_t1" }),
      postChatMessage: vi.fn().mockResolvedValue({ run_id: "run_shell_t1" }),
      getChat: vi.fn().mockResolvedValue({ messages: [] }),
      cases: vi.fn().mockResolvedValue({ cases: [] }),
    },
  };
});

const go = (hash: string) => {
  act(() => {
    window.location.hash = hash;
  });
};

describe("App three-space shell (28.E-1)", () => {
  beforeEach(() => {
    window.location.hash = "";
    localStorage.clear();
  });

  it("default entry (no hash / root / /chat) is the CONSUMER shell", async () => {
    const { unmount } = render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-layout")).toBeInTheDocument());
    unmount();

    go(`#${ROUTES.consumerChat}`);
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-layout")).toBeInTheDocument());
  });

  it("consumer shell exposes NO internal entries and NO runtime inspector", () => {
    render(<App />);
    // no internal navigation
    expect(screen.queryByTestId("nav-internal-review")).toBeNull();
    expect(screen.queryByTestId("nav-internal-dashboard")).toBeNull();
    expect(screen.queryByTestId("nav-internal-console")).toBeNull();
    expect(screen.queryByText("审核队列")).toBeNull();
    expect(screen.queryByText("Dashboard")).toBeNull();
    expect(screen.queryByText("Developer Mode")).toBeNull();
    // no embedded RuntimeInspector (the run_id/case_id/Trace panel)
    expect(screen.queryByText("run_id")).toBeNull();
    expect(screen.queryByText(/Pipeline/)).toBeNull();
    // no demo-mode affordances
    expect(screen.queryByTestId("mode-toggle")).toBeNull();
    expect(screen.queryByText("演示 Demo")).toBeNull();
  });

  it("the legacy localStorage mode key no longer selects a space", async () => {
    localStorage.setItem("webui:mode", "developer");
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-layout")).toBeInTheDocument());
    expect(screen.queryByTestId("nav-internal-console")).toBeNull();
  });

  it("unknown routes fall back to the consumer space (never internal)", async () => {
    go("#/developer/inspector");
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-layout")).toBeInTheDocument());
    expect(screen.queryByText("内部工作台")).toBeNull();
  });

  it("direct #/operator/review opens the internal operator surface", async () => {
    go(`#${ROUTES.operatorReview}`);
    render(<App />);
    expect(screen.getByText(/内部工作台/)).toBeVisible();
    expect(screen.getByTestId("nav-back-consumer")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("project-input")).toBeInTheDocument();
    });
  });

  it("direct #/developer/dashboard and #/developer/console open developer surfaces", async () => {
    go(`#${ROUTES.developerDashboard}`);
    const { unmount } = render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("dash-project-input")).toBeInTheDocument();
    });
    unmount();

    go(`#${ROUTES.developerConsole}`);
    render(<App />);
    // the Phase-2 runtime console (its own back control) is mounted
    expect(screen.getByTestId("back-to-chat")).toBeInTheDocument();
    expect(screen.queryByText("保险顾问助手")).toBeNull();
  });

  it("hash navigation switches spaces (browser back/forward equivalent)", async () => {
    go(`#${ROUTES.developerConsole}`);
    render(<App />);
    expect(screen.getByTestId("back-to-chat")).toBeInTheDocument();

    go(`#${ROUTES.consumerChat}`); // "back" to the consumer space
    await waitFor(() => {
      expect(screen.getByText("保险顾问助手")).toBeVisible();
    });

    go(`#${ROUTES.developerConsole}`); // "forward" again
    await waitFor(() => {
      expect(screen.getByText(/内部工作台/)).toBeVisible();
    });
  });

  it("internal nav buttons switch within the internal space", async () => {
    go(`#${ROUTES.operatorReview}`);
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("project-input")).toBeInTheDocument();
    });
    act(() => {
      screen.getByTestId("nav-internal-dashboard").click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("dash-project-input")).toBeInTheDocument();
    });
  });

  it("consumer conversations persist across remount (refresh equivalent)", async () => {
    const { unmount } = render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-layout")).toBeInTheDocument());
    act(() => {
      screen.getByText("＋ 新对话").click();
    });
    unmount();

    render(<App />);
    await waitFor(() => expect(screen.getByTestId("chat-layout")).toBeInTheDocument());
    // the chat created before the "refresh" is still listed in the sidebar
    expect(screen.getAllByText("新对话").length).toBeGreaterThan(0);
  });

  it("navigate() drives the hash (programmatic boundary transitions)", () => {
    act(() => {
      navigate(ROUTES.developerDashboard);
    });
    expect(window.location.hash).toBe(`#${ROUTES.developerDashboard}`);
  });
});
