/**
 * Consumer DOM leakage test (28.E-2 §22).
 *
 * Renders the CONSUMER route (#/chat) with poisoned state: a chat whose
 * messages carry internal identifiers (run ids in artifact/activity
 * metadata, a case id), then asserts the final DOM text contains NONE of
 * the forbidden internal strings. Internal surfaces are out of scope —
 * they may keep showing internals.
 */
import { render, waitFor } from "@testing-library/react";
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
      createChat: vi.fn().mockResolvedValue({ chat_id: "chat_dom_t1" }),
      postChatMessage: vi.fn().mockResolvedValue({ run_id: "run_dom_t1" }),
      streamUrl: vi.fn(() => "/api/runs/run_dom_t1/stream"),
      getArtifact: vi.fn().mockResolvedValue({
        artifact: { payload: { rendered_report: "# 客户保险需求分析报告\n\n内容" } },
      }),
    },
  };
});

const FORBIDDEN = [
  "run_leak", "run_dom", "bm-leak", "case_id", "run_id", "artifact_id",
  "eval_id", "approval_id", "trace_id", "agent_id", "workflow_id",
  "event_type", "insurance-report", "Portfolio Demo Mode", "QA_REFUSED",
  "Developer", "Inspector", "Dashboard", "Trace", "Eval", "Debug",
  "provider", "glm", "prompt",
  // 28.E-3 §26: agent/tool/skill/router/registry/internals
  "insurance_qa", "product_qa", "insurance-planning-agent",
  "router", "registry", "registry_lookup", "decision_source",
  "knowledge-search", "client-intake", "requirement_analysis",
  "risk-analysis", "recommendation", "report-generation",
  "KnowledgeService", "WeKnora", "LLMGateway",
  "WAITING_USER", "authority", "slice", "runtime",
  // 28.K.1 (P2-①): needs_review internal stage/tool leakage family
  "product_candidate_provider", "unknown_internal_stage",
  "did not pass evaluation", "needs human review", "eval_failed_after_repair",
];

describe("consumer DOM leakage (#/chat)", () => {
  beforeEach(() => {
    window.location.hash = "#/chat";
    localStorage.clear();
    // jsdom has no EventSource — stub it so chats carrying a run attach
    // their stream view without unhandled rejections (browser-only API)
    vi.stubGlobal(
      "EventSource",
      class {
        close() {}
        addEventListener() {}
        removeEventListener() {}
      },
    );
  });

  it("poisoned chat metadata never reaches the consumer DOM", async () => {
    localStorage.setItem(
      chatStorageKey(),
      JSON.stringify({
        version: 1,
        chats: [
          {
            id: "chat_local1",
            title: "帮我看看家庭保障",
            caseId: "bm-leak-001",
            runId: "run_leak5678",
            serverChatId: null,
            mode: "agent",
            createdAt: "2026-09-26T00:00:00.000Z",
            updatedAt: "2026-09-26T00:00:00.000Z",
            messages: [
              { kind: "user", id: "u1", at: "t", text: "帮我看看家庭保障有没有明显缺口" },
              { kind: "assistant", id: "a1", at: "t", text: "我先了解一下你的家庭情况。" },
              {
                kind: "activity",
                id: "act1",
                at: "t",
                runId: "run_leak5678",
                caseId: "bm-leak-001",
              },
              {
                kind: "artifact",
                id: "art1",
                at: "t",
                runId: "run_leak1234",
                artifactType: "insurance-report",
                title: "客户保险需求分析报告",
              },
            ],
          },
        ],
      }),
    );
    render(<App />);
    await waitFor(() => expect(document.querySelector('[data-testid="chat-layout"]')).not.toBeNull());
    const text = document.body.textContent ?? "";
    for (const s of FORBIDDEN) {
      expect(text.includes(s), `consumer DOM must not contain ${s}`).toBe(false);
    }
    // the real artifact card IS still there (title + CTA, no ids/types)
    expect(text.includes("客户保险需求分析报告")).toBe(true);
    expect(text.includes("查看完整报告")).toBe(true);
  });

  it("the artifact modal renders report CONTENT without ids/types", async () => {
    localStorage.setItem(
      chatStorageKey(),
      JSON.stringify({
        version: 1,
        chats: [
          {
            id: "chat_local2",
            title: "家庭方案",
            caseId: "bm-leak-002",
            runId: "run_leak9999",
            serverChatId: null,
            mode: "agent",
            createdAt: "2026-09-26T00:00:00.000Z",
            updatedAt: "2026-09-26T00:00:00.000Z",
            messages: [
              { kind: "user", id: "u1", at: "t", text: "帮我整理方案" },
              {
                kind: "artifact",
                id: "art1",
                at: "t",
                runId: "run_leak9999",
                artifactType: "insurance-report",
                title: "客户保险需求分析报告",
              },
            ],
          },
        ],
      }),
    );
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector('[data-testid="open-report"]')).not.toBeNull());
    const btn = container.querySelector('[data-testid="open-report"]') as HTMLElement;
    btn.click();
    // modal appears (async fetch resolves to the mocked markdown)
    await (async () => {
      for (let i = 0; i < 40 && !document.querySelector('[data-testid="report-modal"]'); i++) {
        await new Promise((r) => setTimeout(r, 25));
      }
    })();
    const modal = document.querySelector('[data-testid="report-modal"]');
    expect(modal).not.toBeNull();
    const text = modal?.textContent ?? "";
    expect(text).toContain("客户保险需求分析报告");
    for (const s of FORBIDDEN) {
      expect(text.includes(s), `modal must not contain ${s}`).toBe(false);
    }
  });

  it("K.1 (P2-①): needs_review terminal renders natural-language copy — internal stage/tool names never reach the DOM", async () => {
    // Post-fix world: the finalized transcript carries the MAPPED consumer
    // copy (28.K.1 — needs_review is a system state, server template text
    // is mapped away); internal summaries exist only in run/event metadata,
    // which the DTO boundary never renders.
    localStorage.setItem(
      chatStorageKey(),
      JSON.stringify({
        version: 1,
        chats: [
          {
            id: "chat_k1",
            title: "给孩子规划保险",
            caseId: "bm-k1-001",
            runId: "run_leakK1",
            serverChatId: null,
            mode: "agent",
            createdAt: "2026-09-26T00:00:00.000Z",
            updatedAt: "2026-09-26T00:00:00.000Z",
            messages: [
              { kind: "user", id: "u1", at: "t", text: "我想给孩子重新规划一下保险。" },
              {
                kind: "activity",
                id: "act1",
                at: "t",
                runId: "run_leakK1",
                caseId: "bm-k1-001",
              },
              {
                kind: "assistant",
                id: "a1",
                at: "t",
                text: "这个结果需要进一步人工核实，确认后我会继续处理。",
              },
            ],
          },
        ],
      }),
    );
    render(<App />);
    await waitFor(() => expect(document.querySelector('[data-testid="chat-layout"]')).not.toBeNull());
    const text = document.body.textContent ?? "";
    // natural-language terminal copy IS shown
    expect(text).toContain("这个结果需要进一步人工核实");
    // the K.1 leakage family is absent from the whole DOM (FORBIDDEN
    // now includes product_candidate_provider / unknown_internal_stage /
    // "did not pass evaluation" / "needs human review")
    for (const s of FORBIDDEN) {
      expect(text.includes(s), `consumer DOM must not contain ${s}`).toBe(false);
    }
  });
});
