/**
 * Central API layer — the ONLY place that talks HTTP to the runtime server.
 * Components never fetch() directly.
 */
import type {
  ArtifactDetail,
  ArtifactSummary,
  CaseAlreadyRunning,
  CaseInfo,
  EventsResponse,
  Run,
} from "../types/runtime";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
    message?: string,
  ) {
    super(message ?? `API error ${status}`);
    this.name = "ApiError";
  }

  /** The 409 case_already_running contract (Phase 1.1). */
  get conflict(): CaseAlreadyRunning | null {
    if (this.status === 409) {
      const b = this.body as Partial<CaseAlreadyRunning>;
      if (b && b.error === "case_already_running" && typeof b.run_id === "string") {
        return { error: "case_already_running", run_id: b.run_id, case_id: b.case_id ?? "" };
      }
    }
    return null;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (cause) {
    throw new ApiError(0, null, `Cannot reach the runtime server (${String(cause)})`);
  }
  const text = await resp.text();
  const body: unknown = text ? safeJson(text) : null;
  if (!resp.ok) {
    throw new ApiError(resp.status, body);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  cases: () => request<{ cases: CaseInfo[] }>("/api/cases"),

  // ---- Agent Mode (Phase 2.6) — the frontend never sees the LLM provider ---- #
  agentConfig: () =>
    request<{ configured: boolean; provider: string | null; model: string | null }>(
      "/api/agent/config"),
  createChat: () => request<{ chat_id: string }>("/api/chats", { method: "POST" }),
  getChat: (chatId: string) =>
    request<{
      chat_id: string;
      messages: { role: string; content: string; kind?: string; run_id?: string }[];
      runs: string[];
    }>(`/api/chats/${chatId}`),
  postChatMessage: (chatId: string, text: string) =>
    request<{ chat_id: string; run_id: string; status: string }>(
      `/api/chats/${chatId}/messages`,
      { method: "POST", body: JSON.stringify({ text }) },
    ),

  createRun: (caseId: string) =>
    request<{ run_id: string; case_id: string; status: string }>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId }),
    }),

  getRun: (runId: string) => request<Run>(`/api/runs/${runId}`),

  getEvents: (runId: string, afterEventId?: string) =>
    request<EventsResponse>(
      `/api/runs/${runId}/events${afterEventId ? `?after_event_id=${afterEventId}` : ""}`,
    ),

  getArtifacts: (runId: string) =>
    request<{ run_id: string; count: number; artifacts: ArtifactSummary[] }>(
      `/api/runs/${runId}/artifacts`,
    ),

  getArtifact: (runId: string, artifactType: string) =>
    request<ArtifactDetail>(`/api/runs/${runId}/artifacts/${artifactType}`),

  /** SSE endpoint URL with the resume cursor (EventSource cannot set headers). */
  streamUrl: (runId: string, afterEventId?: string) =>
    `/api/runs/${runId}/stream${afterEventId ? `?after_event_id=${afterEventId}` : ""}`,
};
