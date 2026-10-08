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
import type {
  ApprovalDetailResponse,
  ApprovalsResponse,
  SupervisorState,
} from "../types/approval";
import type { ReviewCard } from "../types/reviewCard";

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

export const CONSUMER_KEY_STORAGE = "webui:consumer-key";

/** 28.G: the stored consumer credential — used ONLY as an
 *  authentication secret sent to the server; it is never an ownership
 *  source (ownership is decided server-side from the resolved subject). */
export function authHeaders(): Record<string, string> {
  let key = "";
  try {
    key = localStorage.getItem(CONSUMER_KEY_STORAGE) ?? "";
  } catch { /* storage unavailable */ }
  return key ? { Authorization: `Bearer ${key}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      headers: { "Content-Type": "application/json", ...authHeaders() },
      ...init,
    });
  } catch (cause) {
    throw new ApiError(0, null, `Cannot reach the runtime server (${String(cause)})`);
  }
  const text = await resp.text();
  const body: unknown = text ? safeJson(text) : null;
  if (!resp.ok) {
    if (resp.status === 401) {
      // let the shell surface the identity gate (28.G); callers still
      // receive the ApiError
      window.dispatchEvent(new CustomEvent("webui:unauthorized"));
    }
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

  /** Phase 27.7.6 v2: read-only Review Card projection (generated on demand). */
  reviewCard: (runId: string) =>
    request<ReviewCard>(`/api/runs/${runId}/review-card`),

  /** SSE endpoint URL with the resume cursor. EventSource cannot set the
   * Authorization header (browser API limitation), so the key rides as a
   * ?key= query parameter — the server checks it as an auth fallback. */
  streamUrl: (runId: string, afterEventId?: string) => {
    let key = "";
    try { key = localStorage.getItem(CONSUMER_KEY_STORAGE) ?? ""; } catch { /* */ }
    const params = new URLSearchParams();
    if (afterEventId) params.set("after_event_id", afterEventId);
    if (key) params.set("key", key);
    const qs = params.toString();
    return `/api/runs/${runId}/stream${qs ? `?${qs}` : ""}`;
  },
  // ---- 28.G consumer identity + opaque artifact references ----
  whoami: () => request<{ subject: string | null; role: string | null; mode: string }>(
    "/api/consumer/whoami"),
  issueArtifactRef: (runId: string, artifactType: string) =>
    request<{ ref: string }>(`/api/runs/${runId}/artifact-refs/${artifactType}`),
  artifactByRef: (ref: string) =>
    request<ArtifactDetail>(`/api/consumer/artifacts/${ref}`),

  // ---- Review Queue (Phase 27.5-2) — read-only approval projection ---- #
  /** Existing backend endpoint, project-scoped (no global list endpoint yet). */
  approvals: (projectId: string) =>
    request<ApprovalsResponse>(`/api/projects/${projectId}/approvals`),

  getApproval: (approvalId: string) =>
    request<ApprovalDetailResponse>(`/api/approvals/${approvalId}`),

  /** Phase 10 supervisor state (existing endpoint, previously unconsumed). */
  supervisor: (projectId: string) =>
    request<{ project_id: string; supervisor: SupervisorState }>(
      `/api/projects/${projectId}/supervisor`,
    ),

  // ---- Decision submission (Phase 27.5-4) — existing Phase 9 endpoints ---- #
  /** POST /api/approvals/{id}/approve (REVIEWER role; body {actor, reason}). */
  approveApproval: (approvalId: string, body: { actor: string; reason: string }) =>
    request<Record<string, unknown>>(
      `/api/approvals/${approvalId}/approve`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  /** POST /api/approvals/{id}/reject — reason is semantically required by the UI. */
  rejectApproval: (approvalId: string, body: { actor: string; reason: string }) =>
    request<Record<string, unknown>>(
      `/api/approvals/${approvalId}/reject`,
      { method: "POST", body: JSON.stringify(body) },
    ),
};
