/**
 * Consumer Artifact Delivery (28.E-4).
 *
 * E4-T1 real artifact → visible + viewable
 * E4-T2 completion without artifact → no card
 * E4-T3 unknown artifact type → hidden (fail closed)
 * E4-T4 internal ids → 0 in card/modal DOM
 * E4-T6 content rendered (markdown)
 * E4-T7 remount (refresh) behavior
 * E4-T8 poisoning / fetch failure → consumer-safe
 * E4-T9 internal artifact types → not consumer visible
 * (E4-T5 route boundary lives in app/route.test.ts)
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ArtifactCard } from "./ArtifactCard";
import { Conversation } from "./Conversation";
import { makeChat } from "../../state/chatState";
import type { Message } from "../../types/chat";

const { api } = vi.hoisted(() => ({ api: { getArtifact: vi.fn() } }));
vi.mock("../../api/client", () => ({
  ApiError: class extends Error {
    status = 0;
    body: unknown = null;
    conflict: unknown = null;
  },
  api,
}));

const FORBIDDEN = [
  "run_", "case_", "artifact_id", "insurance-report", "version",
  "schema", "provider", "eval", "approval", "trace",
];

const REAL_MD = "# 客户保险需求分析报告\n\n- **年龄**：35\n- 结论：先补齐医疗保障缺口";

function artifactMessage(over: Partial<Extract<Message, { kind: "artifact" }>> = {}): Message {
  return {
    kind: "artifact",
    id: "art1",
    at: "2026-09-26T00:00:00.000Z",
    runId: "run_art_internal_1234",
    artifactType: "insurance-report",
    title: "客户保险需求分析报告",
    ...over,
  };
}

describe("ArtifactCard — consumer delivery (allowlist-gated)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.location.hash = "#/chat";
  });

  it("E4-T1/T6: a REAL report artifact renders a card, opens, and shows content", async () => {
    api.getArtifact.mockResolvedValue({
      artifact: { payload: { rendered_report: REAL_MD } },
    });
    const { container } = render(
      <ArtifactCard runId="run_x" artifactType="insurance-report" />,
    );
    expect(screen.getByTestId("artifact-card").textContent).toContain("客户保险需求分析报告");
    fireEvent.click(screen.getByTestId("open-report"));
    await waitFor(() => {
      expect(screen.getByTestId("report-modal").textContent).toContain("年龄");
    });
    // E4-T4: no internal ids/types anywhere in card or modal
    const text = container.textContent ?? "";
    for (const s of FORBIDDEN) {
      expect(text.includes(s), `artifact DOM must not contain ${s}`).toBe(false);
    }
  });

  it("E4-T1: download becomes available once content is loaded (consumer-safe name)", async () => {
    api.getArtifact.mockResolvedValue({
      artifact: { payload: { rendered_report: REAL_MD } },
    });
    const createObjectURL = vi.fn(() => "blob:mock");
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL: vi.fn() });
    render(<ArtifactCard runId="run_x" artifactType="insurance-report" />);
    fireEvent.click(screen.getByTestId("open-report"));
    const btn = await waitFor(() => {
      const b = screen.getByTestId("download-report") as HTMLButtonElement;
      expect(b.disabled).toBe(false);
      return b;
    });
    expect(() => fireEvent.click(btn)).not.toThrow();
    expect(createObjectURL).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("E4-T3/T9: unknown or internal artifact types render NOTHING (fail closed)", () => {
    const { container } = render(
      <>
        <ArtifactCard runId="run_x" artifactType="knowledge-evidence" />
        <ArtifactCard runId="run_x" artifactType="client-profile" />
        <ArtifactCard runId="run_x" artifactType="some-future-type" />
      </>,
    );
    expect(container.querySelector('[data-testid="artifact-card"]')).toBeNull();
    expect(container.textContent).not.toContain("knowledge-evidence");
  });

  it("E4-T7: remount (refresh equivalent) keeps the card and reopens the modal", async () => {
    api.getArtifact.mockResolvedValue({
      artifact: { payload: { rendered_report: REAL_MD } },
    });
    const first = render(<ArtifactCard runId="run_x" artifactType="insurance-report" />);
    expect(screen.getByTestId("artifact-card")).toBeInTheDocument();
    first.unmount();

    render(<ArtifactCard runId="run_x" artifactType="insurance-report" />);
    fireEvent.click(screen.getByTestId("open-report"));
    await waitFor(() => {
      expect(screen.getByTestId("report-modal").textContent).toContain("年龄");
    });
  });

  it("E4-T8: fetch failure degrades to consumer-safe copy (no internals)", async () => {
    api.getArtifact.mockRejectedValue(new Error("connect ECONNREFUSED 127.0.0.1:8000 / trace_xyz"));
    const { container } = render(<ArtifactCard runId="run_x" artifactType="insurance-report" />);
    fireEvent.click(screen.getByTestId("open-report"));
    await waitFor(
      () => {
        expect(container.textContent).toContain("报告加载失败。");
      },
      { timeout: 12_000 },
    );
    expect(container.textContent).not.toContain("ECONNREFUSED");
    expect(container.textContent).not.toContain("trace_xyz");
    expect(container.textContent).not.toContain("run_x");
  }, 15_000);
});

describe("Conversation artifact placement (E4-T2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.location.hash = "#/chat";
  });

  it("a completed turn WITHOUT an artifact message shows NO card", () => {
    const chat = makeChat("bm-complete-001", "问答");
    chat.messages = [
      { kind: "user", id: "u1", at: "t", text: "百万医疗险是什么？" },
      { kind: "assistant", id: "a1", at: "t", text: "答案是……" },
    ];
    const { container } = render(
      <Conversation
        chat={chat}
        streamState={null}
        streaming={false}
        streamError={null}
        conflict={null}
        onOpenConflictOwner={() => {}}
        onPickPrompt={() => {}}
      />,
    );
    expect(container.querySelector('[data-testid="artifact-card"]')).toBeNull();
    expect(container.querySelector('[data-testid="open-report"]')).toBeNull();
  });

  it("a chat WITH a real artifact message renders exactly one card", () => {
    const chat = makeChat("bm-complete-001", "规划");
    chat.messages = [
      { kind: "user", id: "u1", at: "t", text: "帮我做规划" },
      artifactMessage(),
    ];
    const { container } = render(
      <Conversation
        chat={chat}
        streamState={null}
        streaming={false}
        streamError={null}
        conflict={null}
        onOpenConflictOwner={() => {}}
        onPickPrompt={() => {}}
      />,
    );
    expect(container.querySelectorAll('[data-testid="artifact-card"]')).toHaveLength(1);
  });
});
