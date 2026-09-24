/**
 * Approval Detail (Phase 27.5-2) — PLACEHOLDER entry to the future
 * Review Workspace (Phase 27.5-3). Read-only projection of
 * GET /api/approvals/{id}: shows the backend record verbatim so a
 * Reviewer can at least see WHAT is being approved and WHY. No
 * approve/reject controls in this phase (27.5-4).
 */
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { ApprovalRecord } from "../../types/approval";
import { ApprovalStatusBadge } from "./ApprovalStatusBadge";

export function ApprovalDetail({
  approvalId,
  onBack,
  onOpenWorkspace,
}: {
  approvalId: string;
  onBack: () => void;
  onOpenWorkspace: (target: { projectId: string; approvalId: string }) => void;
}) {
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "error"; message: string } | {
      kind: "ready";
      project: string;
      approval: ApprovalRecord;
    }
  >({ kind: "loading" });

  useEffect(() => {
    let alive = true;
    setState({ kind: "loading" });
    api
      .getApproval(approvalId)
      .then((res) => {
        if (alive) setState({ kind: "ready", project: res.project_id, approval: res.approval });
      })
      .catch((e) => {
        if (alive)
          setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });
      });
    return () => {
      alive = false;
    };
  }, [approvalId]);

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-3xl flex-col gap-3 p-4">
      <div className="flex shrink-0 items-center gap-3">
        <button
          data-testid="detail-back"
          onClick={onBack}
          className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11.5px] font-medium text-slate-600 hover:bg-slate-50"
        >
          ← 返回队列
        </button>
        <h2 className="text-[15px] font-semibold tracking-tight">审核任务详情</h2>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          记录视图 — 完整上下文见 Review Workspace
        </span>
        {state.kind === "ready" ? (
          <button
            data-testid="open-workspace"
            onClick={() =>
              onOpenWorkspace({
                projectId: state.project,
                approvalId: state.approval.approval_id,
              })
            }
            className="ml-auto rounded-md bg-slate-800 px-3 py-1 text-[12px] font-medium text-white hover:bg-slate-700"
          >
            查看 Review Workspace →
          </button>
        ) : null}
      </div>

      {state.kind === "loading" ? (
        <p data-testid="detail-loading" className="p-6 text-center text-[13px] text-slate-400">
          正在加载审核任务...
        </p>
      ) : null}
      {state.kind === "error" ? (
        <div data-testid="detail-error" className="rounded-lg border border-red-200 bg-red-50 p-4 text-center">
          <p className="text-[13px] font-medium text-red-700">审核任务加载失败</p>
          <p className="mt-1 font-mono text-[12px] text-red-500">{state.message}</p>
        </div>
      ) : null}
      {state.kind === "ready" ? (
        <div data-testid="detail-card" className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-center gap-2">
            <ApprovalStatusBadge status={state.approval.status} />
            <span className="font-mono text-[12px] text-slate-500">
              {state.approval.approval_id}
            </span>
          </div>
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 text-[12.5px] sm:grid-cols-2">
            {(
              [
                ["项目", state.project],
                ["Task", state.approval.task_id || "—"],
                ["类型", state.approval.request_type],
                ["请求方", state.approval.requested_by],
                ["创建时间", state.approval.created_at?.replace("T", " ") ?? "—"],
                ["解决时间", state.approval.resolved_at?.replace("T", " ") ?? "—"],
                ["决定", state.approval.decision ?? "—"],
                ["决定人", state.approval.resolved_by ?? "—"],
              ] as [string, string][]
            ).map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <dt className="w-16 shrink-0 text-slate-400">{k}</dt>
                <dd className="min-w-0 break-all text-slate-700">{v}</dd>
              </div>
            ))}
          </dl>
          {state.approval.reason ? (
            <div className="mt-3 rounded-md bg-slate-50 p-2.5">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Reason
              </p>
              <p className="mt-0.5 text-[12.5px] text-slate-600">{state.approval.reason}</p>
            </div>
          ) : null}
          {state.approval.context && Object.keys(state.approval.context).length > 0 ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-[12px] text-slate-500">Context</summary>
              <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-slate-50 p-2 text-[11px] text-slate-600">
                {JSON.stringify(state.approval.context, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
