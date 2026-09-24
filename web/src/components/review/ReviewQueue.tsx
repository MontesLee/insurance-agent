/**
 * Review Queue (Phase 27.5-2 + 27.7.6 v2) — the Reviewer's entry point.
 *
 * UI-observes-only: this page is a pure projection of the backend
 * approval store (GET /api/projects/{id}/approvals) plus, since
 * Phase 27.7.6 v2, the backend-generated Review Cards
 * (GET /api/runs/{run_id}/review-card) for approvals whose context
 * carries a run_id. Cards render VERBATIM (level / validation /
 * flags) — the queue never re-derives risk. An approval without run
 * context shows "无 Review Card"; a failed card fetch degrades to a
 * hint, never blocking the approval list.
 *
 * KNOWN API GAP (recorded in phase27.5-2-review-queue-result.md):
 * there is no global/project-list endpoint, so the queue is
 * project-scoped with a persisted project-id selector.
 */
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ApprovalRecord } from "../../types/approval";
import type { ReviewCard } from "../../types/reviewCard";
import { ApprovalStatusBadge } from "./ApprovalStatusBadge";
import { RiskLevelBadge, ValidationChips, topIssue } from "./ReviewCardView";

const PROJECT_KEY = "webui:review-project";
const ACTIVE = new Set(["PENDING", "WAITING_HUMAN"]);

type Filter = "all" | "high" | "need" | "audit";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All 全部" },
  { key: "high", label: "High Risk 高风险" },
  { key: "need", label: "Need Review 待审" },
  { key: "audit", label: "Random Audit 抽审" },
];

function waitingSince(createdAt: string): string {
  const t = Date.parse(createdAt);
  if (Number.isNaN(t)) return "UNKNOWN";
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)} h ${mins % 60} min`;
}

function contextField(a: ApprovalRecord, key: string): string {
  const v = (a.context ?? {})[key];
  return typeof v === "string" && v ? v : "—";
}

function runIdOf(a: ApprovalRecord): string | null {
  const v = (a.context ?? {})["run_id"];
  return typeof v === "string" && v ? v : null;
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
  const [cards, setCards] = useState<Record<string, ReviewCard | null>>({});
  const [filter, setFilter] = useState<Filter>("all");

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
      // Phase 27.7.6 v2: fetch Review Cards for linkable runs. Each
      // fetch settles independently — one failure never blocks the list.
      setCards({});
      const linkable = sorted.filter((a) => runIdOf(a));
      const results = await Promise.allSettled(
        linkable.map((a) => api.reviewCard(runIdOf(a) as string)),
      );
      const byApproval: Record<string, ReviewCard | null> = {};
      linkable.forEach((a, i) => {
        const r = results[i];
        byApproval[a.approval_id] =
          r && r.status === "fulfilled" ? r.value : null;
      });
      setCards(byApproval);
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

  const cardOf = (a: ApprovalRecord): ReviewCard | null | undefined =>
    cards[a.approval_id];

  const matches = (a: ApprovalRecord): boolean => {
    if (filter === "all") return true;
    if (filter === "need") return ACTIVE.has(a.status);
    const card = cardOf(a);
    if (!card) return false;
    if (filter === "high")
      return (
        card.review_action.level === "DEEP_REVIEW" ||
        card.risk_flags.some((f) => f.severity === "HIGH")
      );
    return card.sampling.triggered; // audit
  };

  const visible =
    state.kind === "ready" ? state.approvals.filter(matches) : [];

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-4xl flex-col gap-3 p-4">
      <div className="shrink-0">
        <h2 className="text-[15px] font-semibold tracking-tight">审核队列 Review Queue</h2>
        <p className="mt-0.5 text-[12px] text-slate-400">
          人工审核入口 —— 数据来自后端 approval 存储 + Review Card,本页只读。
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

      {state.kind === "ready" && state.approvals.length > 0 ? (
        <div data-testid="queue-filters" className="flex shrink-0 flex-wrap gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              data-testid={`queue-filter-${f.key}`}
              onClick={() => setFilter(f.key)}
              className={
                filter === f.key
                  ? "rounded-md border border-slate-800 bg-slate-800 px-2.5 py-1 text-[11.5px] font-medium text-white"
                  : "rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11.5px] font-medium text-slate-600 hover:bg-slate-50"
              }
            >
              {f.label}
            </button>
          ))}
        </div>
      ) : null}

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
      {state.kind === "ready" && visible.length === 0 && state.approvals.length > 0 ? (
        <div data-testid="queue-filtered-empty" className="rounded-lg border border-dashed border-slate-200 bg-white p-6 text-center">
          <p className="text-[12.5px] text-slate-400">当前筛选下没有条目</p>
        </div>
      ) : null}
      {state.kind === "ready" && visible.length > 0 ? (
        <ul data-testid="queue-list" className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
          {visible.map((a) => {
            const card = cardOf(a);
            return (
              <li key={a.approval_id}>
                <button
                  data-testid={`queue-item-${a.approval_id}`}
                  onClick={() => onOpenApproval(a.approval_id)}
                  className="w-full rounded-lg border border-slate-200 bg-white p-3 text-left transition hover:border-slate-300 hover:bg-slate-50"
                >
                  <div className="flex items-center gap-2">
                    <ApprovalStatusBadge status={a.status} />
                    {card ? (
                      <RiskLevelBadge card={card} />
                    ) : runIdOf(a) ? (
                      <span
                        data-testid={`card-load-failed-${a.approval_id}`}
                        className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10.5px] font-medium text-slate-400"
                      >
                        Review Card 加载失败
                      </span>
                    ) : (
                      <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10.5px] font-medium text-slate-400">
                        无 Review Card(未携带运行上下文)
                      </span>
                    )}
                    <span className="ml-auto shrink-0 font-mono text-[11px] text-slate-400">
                      {a.approval_id}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-[13px] font-medium text-slate-700">
                    {contextField(a, "client_name") !== "—"
                      ? contextField(a, "client_name")
                      : a.reason.slice(0, 40) || a.approval_id}
                  </p>
                  {card ? (
                    <>
                      <div className="mt-1.5">
                        <ValidationChips card={card} />
                      </div>
                      <p
                        data-testid={`card-issue-${a.approval_id}`}
                        className="mt-1.5 text-[12px] text-slate-600"
                      >
                        {topIssue(card) ?? "无风险标记"}
                        {card.sampling.triggered ? " · 随机抽审命中" : ""}
                      </p>
                    </>
                  ) : null}
                  <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11.5px] text-slate-500 sm:grid-cols-4">
                    <span>项目: <span className="font-mono">{a.project_id}</span></span>
                    <span>Run: <span className="font-mono">{runIdOf(a) ?? "—"}</span></span>
                    <span>类型: {a.request_type}</span>
                    <span>创建: {a.created_at?.slice(0, 16).replace("T", " ") || "—"}</span>
                    <span>等待: {ACTIVE.has(a.status) ? waitingSince(a.created_at) : "—"}</span>
                    <span>决定: {a.decision ?? "—"}</span>
                  </div>
                </button>
              </li>
            );
          })}
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
