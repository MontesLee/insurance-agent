/**
 * Review Queue (Phase 27.5-2) — the Reviewer's entry point.
 *
 * UI-observes-only: this page is a pure projection of the backend
 * approval store (GET /api/projects/{id}/approvals). It does not
 * decide, derive, or mutate anything. Statuses are verbatim
 * backend values. The waiting duration is presentation arithmetic
 * over the backend `created_at`, not a business state.
 *
 * KNOWN API GAP (recorded in phase27.5-2-review-queue-result.md):
 * there is no global/project-list endpoint, so the queue is
 * project-scoped with a persisted project-id selector. Adding
 * GET /api/approvals (global) would be a minimal backend change —
 * deliberately NOT done in this phase.
 */
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ApprovalRecord } from "../../types/approval";
import { ApprovalStatusBadge } from "./ApprovalStatusBadge";

const PROJECT_KEY = "webui:review-project";
const ACTIVE = new Set(["PENDING", "WAITING_HUMAN"]);

function waitingSince(createdAt: string): string {
  const t = Date.parse(createdAt);
  if (Number.isNaN(t)) return "UNKNOWN";
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  return `${h} h ${mins % 60} min`;
}

function contextField(a: ApprovalRecord, key: string): string {
  const v = (a.context ?? {})[key];
  return typeof v === "string" && v ? v : "—";
}

type LoadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; approvals: ApprovalRecord[] };

export function ReviewQueue({
  onOpenApproval,
}: {
  onOpenApproval: (approvalId: string) => void;
}) {
  const [projectId, setProjectId] = useState(() => {
    try {
      return localStorage.getItem(PROJECT_KEY) ?? "";
    } catch {
      return "";
    }
  });
  const [draft, setDraft] = useState(projectId);
  const [state, setState] = useState<LoadState>({ kind: "idle" });

  const load = useCallback(async (pid: string) => {
    setState({ kind: "loading" });
    try {
      const res = await api.approvals(pid);
      // Presentation-only ordering: actionable first, then newest.
      const sorted = [...res.approvals].sort((a, b) => {
        const aa = ACTIVE.has(a.status) ? 0 : 1;
        const ab = ACTIVE.has(b.status) ? 0 : 1;
        if (aa !== ab) return aa - ab;
        return Date.parse(b.created_at) - Date.parse(a.created_at);
      });
      setState({ kind: "ready", approvals: sorted });
    } catch (e) {
      const message =
        e instanceof ApiError && e.status === 404
          ? `项目 ${pid} 不存在（404）`
          : `无法加载审核队列（${e instanceof Error ? e.message : String(e)}）`;
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    if (projectId) void load(projectId);
  }, [projectId, load]);

  const submit = () => {
    const pid = draft.trim();
    if (!pid) return;
    try {
      localStorage.setItem(PROJECT_KEY, pid);
    } catch {
      /* ignore */
    }
    setProjectId(pid);
  };

  const pendingCount =
    state.kind === "ready"
      ? state.approvals.filter((a) => ACTIVE.has(a.status)).length
      : 0;

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-4xl flex-col gap-3 p-4">
      <div className="shrink-0">
        <h2 className="text-[15px] font-semibold tracking-tight">审核队列 Review Queue</h2>
        <p className="mt-0.5 text-[12px] text-slate-400">
          人工审核入口 —— 数据来自后端 approval 存储，本页只读。
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <input
          data-testid="project-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="项目 ID（project_id）"
          className="w-64 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[12.5px] text-slate-700 outline-none focus:border-slate-400"
        />
        <button
          data-testid="project-load"
          onClick={submit}
          className="rounded-md bg-slate-800 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-slate-700"
        >
          加载
        </button>
        {state.kind === "ready" ? (
          <span data-testid="queue-count" className="ml-auto text-[12px] text-slate-400">
            待处理 {pendingCount} / 共 {state.approvals.length} 条
          </span>
        ) : null}
      </div>

      {state.kind === "idle" ? (
        <EmptyHint text="输入项目 ID 并点击「加载」查看该项目的审核任务。" />
      ) : null}
      {state.kind === "loading" ? (
        <p data-testid="queue-loading" className="p-6 text-center text-[13px] text-slate-400">
          正在加载审核队列...
        </p>
      ) : null}
      {state.kind === "error" ? (
        <div data-testid="queue-error" className="rounded-lg border border-red-200 bg-red-50 p-4 text-center">
          <p className="text-[13px] font-medium text-red-700">审核队列加载失败</p>
          <p className="mt-1 text-[12px] text-red-500">{state.message}</p>
          <button
            data-testid="queue-retry"
            onClick={() => projectId && void load(projectId)}
            className="mt-2 rounded-md border border-red-300 bg-white px-3 py-1 text-[12px] font-medium text-red-600 hover:bg-red-100"
          >
            Retry
          </button>
        </div>
      ) : null}
      {state.kind === "ready" && state.approvals.length === 0 ? (
        <div data-testid="queue-empty" className="rounded-lg border border-slate-200 bg-white p-8 text-center">
          <p className="text-[13px] font-medium text-slate-500">当前没有待审核事项</p>
          <p className="mt-1 text-[12px] text-slate-400">所有 AI 推荐均已处理</p>
        </div>
      ) : null}
      {state.kind === "ready" && state.approvals.length > 0 ? (
        <ul data-testid="queue-list" className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
          {state.approvals.map((a) => (
            <li key={a.approval_id}>
              <button
                data-testid={`queue-item-${a.approval_id}`}
                onClick={() => onOpenApproval(a.approval_id)}
                className="w-full rounded-lg border border-slate-200 bg-white p-3 text-left transition hover:border-slate-300 hover:bg-slate-50"
              >
                <div className="flex items-center gap-2">
                  <ApprovalStatusBadge status={a.status} />
                  <span className="truncate text-[13px] font-medium text-slate-700">
                    {contextField(a, "client_name") !== "—"
                      ? contextField(a, "client_name")
                      : a.reason.slice(0, 40) || a.approval_id}
                  </span>
                  <span className="ml-auto shrink-0 font-mono text-[11px] text-slate-400">
                    {a.approval_id}
                  </span>
                </div>
                <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11.5px] text-slate-500 sm:grid-cols-4">
                  <span>项目: <span className="font-mono">{a.project_id}</span></span>
                  <span>Task: <span className="font-mono">{a.task_id || "—"}</span></span>
                  <span>类型: {a.request_type}</span>
                  <span>Stage: {contextField(a, "stage")}</span>
                  <span>创建: {a.created_at?.slice(0, 16).replace("T", " ") || "—"}</span>
                  <span>等待: {ACTIVE.has(a.status) ? waitingSince(a.created_at) : "—"}</span>
                  <span>请求方: {a.requested_by}</span>
                  <span>决定: {a.decision ?? "—"}</span>
                </div>
                {a.reason ? (
                  <p className="mt-1.5 line-clamp-2 text-[12px] text-slate-500">{a.reason}</p>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-white p-8 text-center">
      <p className="text-[13px] text-slate-400">{text}</p>
    </div>
  );
}
