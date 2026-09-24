/**
 * Pilot Dashboard (Phase 27.5-5) — READ-ONLY operational overview.
 *
 * Operational visibility only — NOT analytics. All numbers are
 * frontend aggregations over the EXISTING project-scoped approvals
 * endpoint; statuses are grouped by their EXACT backend string
 * (WAITING_HUMAN stays WAITING_HUMAN, unknown statuses get their
 * own card verbatim — never merged or renamed). A failed fetch
 * shows an error banner with Retry — never fake zeros. Waiting
 * durations are presentation arithmetic over backend created_at.
 *
 * GAP honored: no global approvals endpoint → project-scoped with
 * a persisted selector (shared with the Review Queue).
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { ApprovalRecord } from "../../types/approval";

const PROJECT_KEY = "webui:review-project";
const ACTIONABLE = new Set(["WAITING_HUMAN", "PENDING"]);

type LoadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; approvals: ApprovalRecord[] };

/** Group by EXACT status string; unknown statuses kept verbatim. */
export function countByStatus(approvals: ApprovalRecord[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const a of approvals) {
    counts.set(a.status, (counts.get(a.status) ?? 0) + 1);
  }
  return [...counts.entries()].sort((x, y) => y[1] - x[1]);
}

function waitingMinutes(a: ApprovalRecord): number {
  const t = Date.parse(a.created_at);
  return Number.isNaN(t) ? NaN : Math.max(0, (Date.now() - t) / 60000);
}

function fmtMins(m: number): string {
  if (Number.isNaN(m)) return "—";
  if (m < 60) return `${Math.round(m)} min`;
  return `${Math.floor(m / 60)} h ${Math.round(m % 60)} min`;
}

const CARD_STYLES: Record<string, string> = {
  WAITING_HUMAN: "border-amber-200 bg-amber-50 text-amber-700",
  PENDING: "border-slate-200 bg-slate-50 text-slate-600",
  APPROVED: "border-emerald-200 bg-emerald-50 text-emerald-700",
  REJECTED: "border-red-200 bg-red-50 text-red-700",
  EXPIRED: "border-slate-200 bg-slate-50 text-slate-400",
  RESUMED: "border-blue-200 bg-blue-50 text-blue-700",
};

export function PilotDashboard({
  onOpenQueue,
}: {
  onOpenQueue: () => void;
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
      setState({ kind: "ready", approvals: res.approvals });
    } catch (e) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
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

  const waiting =
    state.kind === "ready"
      ? state.approvals.filter((a) => ACTIONABLE.has(a.status))
      : [];
  const waitingMins = waiting.map(waitingMinutes).filter((m) => !Number.isNaN(m));
  const oldest =
    state.kind === "ready" && waiting.length > 0
      ? waiting.reduce((o, a) => (a.created_at < o.created_at ? a : o))
      : null;
  const recent =
    state.kind === "ready"
      ? state.approvals
          .filter((a) => a.resolved_at)
          .sort((x, y) => (x.resolved_at! < y.resolved_at! ? 1 : -1))
          .slice(0, 5)
      : [];

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-4xl flex-col gap-3 overflow-y-auto p-4">
      <div className="shrink-0">
        <h2 className="text-[15px] font-semibold tracking-tight">Pilot Dashboard</h2>
        <p className="mt-0.5 text-[12px] text-slate-400">
          运营总览(只读)—— 数字来自后端审批记录的前端聚合,非分析系统。
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <input
          data-testid="dash-project-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="项目 ID(project_id)"
          className="w-64 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[12.5px] text-slate-700 outline-none focus:border-slate-400"
        />
        <button
          data-testid="dash-project-load"
          onClick={submit}
          className="rounded-md bg-slate-800 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-slate-700"
        >
          加载
        </button>
        <span className="text-[11px] text-slate-400">
          无全局审批端点(API GAP)—— 按项目聚合
        </span>
      </div>

      {state.kind === "idle" ? (
        <p className="py-8 text-center text-[13px] text-slate-400">
          输入项目 ID 并点击「加载」查看总览。
        </p>
      ) : null}
      {state.kind === "loading" ? (
        <p data-testid="dash-loading" className="py-8 text-center text-[13px] text-slate-400">
          Loading dashboard...
        </p>
      ) : null}
      {state.kind === "error" ? (
        <div data-testid="dash-error" className="rounded-lg border border-red-200 bg-red-50 p-4 text-center">
          <p className="text-[13px] font-medium text-red-700">Unable to load dashboard data</p>
          <p className="mt-1 font-mono text-[12px] text-red-500">{state.message}</p>
          <button
            data-testid="dash-retry"
            onClick={() => projectId && void load(projectId)}
            className="mt-2 rounded-md border border-red-300 bg-white px-3 py-1 text-[12px] font-medium text-red-600 hover:bg-red-100"
          >
            Retry
          </button>
        </div>
      ) : null}

      {state.kind === "ready" ? (
        <>
          {state.approvals.length === 0 ? (
            <p data-testid="dash-empty" className="rounded-lg border border-dashed border-slate-200 bg-white p-6 text-center text-[13px] text-slate-400">
              No approval records available
            </p>
          ) : null}

          {/* A — Approval Overview */}
          <section className="rounded-lg border border-slate-200 bg-white p-4" data-testid="dash-overview">
            <h3 className="text-[13.5px] font-semibold tracking-tight text-slate-700">A · 审批总览</h3>
            <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {countByStatus(state.approvals).map(([status, n]) => (
                <div
                  key={status}
                  data-testid={`dash-card-${status}`}
                  className={`rounded-lg border p-3 ${CARD_STYLES[status] ?? "border-slate-200 bg-slate-50 text-slate-500"}`}
                >
                  <p className="text-[22px] font-semibold leading-none">{n}</p>
                  <p className="mt-1 truncate font-mono text-[11px] tracking-wide" title={status}>
                    {status}
                  </p>
                </div>
              ))}
            </div>
          </section>

          {/* B — Review Queue Snapshot */}
          <section className="rounded-lg border border-slate-200 bg-white p-4" data-testid="dash-snapshot">
            <h3 className="text-[13.5px] font-semibold tracking-tight text-slate-700">B · 等待快照</h3>
            <dl className="mt-2 grid grid-cols-3 gap-3 text-[12.5px]">
              <div className="rounded-md bg-slate-50 p-2.5">
                <dt className="text-slate-400">Waiting Human</dt>
                <dd data-testid="dash-waiting-count" className="mt-0.5 text-[18px] font-semibold text-slate-700">
                  {state.approvals.filter((a) => a.status === "WAITING_HUMAN").length}
                </dd>
              </div>
              <div className="rounded-md bg-slate-50 p-2.5">
                <dt className="text-slate-400">Oldest Waiting</dt>
                <dd className="mt-0.5 text-slate-700">
                  {oldest ? oldest.created_at.replace("T", " ").slice(0, 16) : "—"}
                </dd>
              </div>
              <div className="rounded-md bg-slate-50 p-2.5">
                <dt className="text-slate-400">Average Waiting</dt>
                <dd className="mt-0.5 text-slate-700">
                  {waitingMins.length > 0
                    ? fmtMins(waitingMins.reduce((s, m) => s + m, 0) / waitingMins.length)
                    : "—"}
                </dd>
              </div>
            </dl>
          </section>

          {/* C — Recent Decisions */}
          <section className="rounded-lg border border-slate-200 bg-white p-4" data-testid="dash-recent">
            <h3 className="text-[13.5px] font-semibold tracking-tight text-slate-700">C · 最近决定</h3>
            {recent.length === 0 ? (
              <p className="mt-2 text-[12.5px] text-slate-400">—(暂无已决定记录)</p>
            ) : (
              <ul className="mt-2 flex flex-col gap-1.5">
                {recent.map((a) => (
                  <li key={a.approval_id} className="flex items-center gap-2 rounded-md border border-slate-100 px-2.5 py-1.5 text-[12.5px]">
                    <span className="w-32 shrink-0 font-mono text-slate-400">
                      {a.resolved_at?.replace("T", " ").slice(5, 16)}
                    </span>
                    <span className={`w-20 shrink-0 font-mono text-[11px] font-semibold ${a.decision === "approve" ? "text-emerald-600" : "text-red-600"}`}>
                      {a.decision ?? "—"}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-mono text-slate-500">{a.approval_id}</span>
                    <span className="shrink-0 text-slate-400">{a.resolved_by ?? "—"}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* D — Quick Actions */}
          <section className="rounded-lg border border-slate-200 bg-white p-4" data-testid="dash-actions">
            <h3 className="text-[13.5px] font-semibold tracking-tight text-slate-700">D · 快速入口</h3>
            <div className="mt-2 flex gap-2">
              <button
                data-testid="dash-open-queue"
                onClick={onOpenQueue}
                className="rounded-md bg-slate-800 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-slate-700"
              >
                Open Review Queue →
              </button>
              <button
                data-testid="dash-open-pending"
                onClick={onOpenQueue}
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-600 hover:bg-slate-50"
              >
                Open Pending Reviews →
              </button>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
