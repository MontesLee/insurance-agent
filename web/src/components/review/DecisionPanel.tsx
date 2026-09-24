/**
 * Decision Panel (Phase 27.5-4) — the human decision layer.
 *
 * Submits APPROVE / REJECT through the EXISTING Phase 9 endpoints
 * (POST /api/approvals/{id}/approve|reject, REVIEWER role, body
 * {actor, reason}). No workflow redesign: the backend stays the
 * only authority — after a successful call the panel re-reads the
 * approval record and renders the backend status verbatim. No
 * optimistic updates, no silent failures, no editing of recorded
 * decisions.
 *
 * Gaps honored: there is no "current identity" API, so the
 * pre-decision reviewer shows "—" (the recorded decision shows the
 * backend's resolved_by). The decision record carries a single
 * resolved entry (no multi-entry history endpoint).
 */
import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ApprovalRecord } from "../../types/approval";
import { ApprovalStatusBadge } from "./ApprovalStatusBadge";

const RESOLVED = new Set(["APPROVED", "REJECTED", "EXPIRED", "RESUMED"]);

type Phase =
  | { kind: "input" }
  | { kind: "confirm"; action: "approve" }
  | { kind: "submitting"; action: "approve" | "reject" }
  | { kind: "error"; action: "approve" | "reject"; message: string }
  | { kind: "done" };

export function DecisionPanel({
  approval,
  onDecided,
}: {
  approval: ApprovalRecord;
  onDecided: () => void;
}) {
  const [comment, setComment] = useState("");
  const [phase, setPhase] = useState<Phase>({ kind: "input" });

  const alreadyDecided = RESOLVED.has(approval.status);

  const submit = async (action: "approve" | "reject") => {
    if (action === "reject" && comment.trim().length === 0) return;
    setPhase({ kind: "submitting", action });
    try {
      // actor is overridden server-side by the authenticated user
      // when authn is on; the body value only applies in no-keys
      // local-dev mode (backend contract, unchanged).
      if (action === "approve") {
        await api.approveApproval(approval.approval_id, {
          actor: "human",
          reason: comment.trim(),
        });
      } else {
        await api.rejectApproval(approval.approval_id, {
          actor: "human",
          reason: comment.trim(),
        });
      }
      setPhase({ kind: "done" });
      onDecided(); // re-read the backend record — never local truth
    } catch (e) {
      setPhase({
        kind: "error",
        action,
        message:
          e instanceof ApiError
            ? `${e.status} ${e.message}`
            : e instanceof Error
              ? e.message
              : String(e),
      });
    }
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4" data-testid="decision-panel">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[13.5px] font-semibold tracking-tight text-slate-700">
          F · 审批决定
        </h3>
        <span className="text-[11px] text-slate-400">
          提交后将由后端记录决定(不可编辑)
        </span>
      </div>

      <div className="mt-2.5 flex items-center gap-2 text-[12.5px]">
        <span className="text-slate-400">当前状态:</span>
        <ApprovalStatusBadge status={approval.status} />
        <span className="ml-4 text-slate-400">Reviewer:</span>
        <span className="text-slate-700">
          {approval.resolved_by ?? "—"}
        </span>
        <span className="ml-auto text-[11px] text-slate-400">
          身份 API 缺失(未发明身份;决定后显示后端 resolved_by)
        </span>
      </div>

      {alreadyDecided ? (
        <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3" data-testid="decision-history">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Decision Record(后端记录,不可编辑)
          </p>
          <dl className="mt-1.5 grid grid-cols-2 gap-x-6 gap-y-1 text-[12.5px] sm:grid-cols-4">
            <div><dt className="text-slate-400">Action</dt><dd className="text-slate-700">{approval.decision ?? "—"}</dd></div>
            <div><dt className="text-slate-400">Reviewer</dt><dd className="text-slate-700">{approval.resolved_by ?? "—"}</dd></div>
            <div><dt className="text-slate-400">Time</dt><dd className="text-slate-700">{approval.resolved_at?.replace("T", " ") ?? "—"}</dd></div>
            <div><dt className="text-slate-400">Status</dt><dd className="text-slate-700">{approval.status}</dd></div>
          </dl>
          <p className="mt-2 text-[12px] text-slate-500">
            Comment:{approval.reason ? `决定时意见未单列存储(见审批 reason/审计 GAP)` : "—"}
          </p>
          <p className="mt-2 text-[11px] text-slate-400">
            该审批已决定,操作按钮禁用(不可重复提交/编辑)。
          </p>
        </div>
      ) : (
        <div className="mt-3">
          <label className="text-[12px] font-medium text-slate-500" htmlFor="decision-comment">
            Comment(REJECT 必填;APPROVE 可留空)
          </label>
          <textarea
            id="decision-comment"
            data-testid="decision-comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={3}
            placeholder="审查意见:证据链是否成立、需要修改什么…"
            className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[12.5px] text-slate-700 outline-none focus:border-slate-400"
          />

          {phase.kind === "confirm" ? (
            <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2.5" data-testid="decision-confirm">
              <p className="text-[12.5px] font-medium text-amber-700">
                确认批准?此操作将记录你的决定。
              </p>
              <div className="mt-1.5 flex gap-2">
                <button
                  data-testid="confirm-yes"
                  disabled={phase.kind !== "confirm"}
                  onClick={() => void submit("approve")}
                  className="rounded bg-emerald-600 px-3 py-1 text-[12px] font-medium text-white hover:bg-emerald-500"
                >
                  确认批准
                </button>
                <button
                  data-testid="confirm-no"
                  onClick={() => setPhase({ kind: "input" })}
                  className="rounded border border-slate-300 bg-white px-3 py-1 text-[12px] font-medium text-slate-600 hover:bg-slate-50"
                >
                  取消
                </button>
              </div>
            </div>
          ) : null}

          {phase.kind === "error" ? (
            <div className="mt-2 rounded-md border border-red-200 bg-red-50 p-2.5" data-testid="decision-error">
              <p className="text-[12.5px] font-medium text-red-700">决定提交失败</p>
              <p className="mt-0.5 font-mono text-[11.5px] text-red-500">{phase.message}</p>
              <button
                data-testid="decision-retry"
                onClick={() => setPhase({ kind: "input" })}
                className="mt-1.5 rounded border border-red-300 bg-white px-2.5 py-0.5 text-[11.5px] font-medium text-red-600 hover:bg-red-100"
              >
                Retry
              </button>
            </div>
          ) : null}

          {phase.kind === "done" ? (
            <p className="mt-2 rounded-md border border-emerald-200 bg-emerald-50 p-2.5 text-[12.5px] font-medium text-emerald-700" data-testid="decision-success">
              已提交 —— 记录以后端为准(刷新中)。
            </p>
          ) : null}

          <div className="mt-2.5 flex items-center gap-2">
            <button
              data-testid="decision-approve"
              disabled={phase.kind === "submitting"}
              onClick={() => setPhase({ kind: "confirm", action: "approve" })}
              className="rounded-md bg-emerald-600 px-4 py-1.5 text-[12.5px] font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              Approve
            </button>
            <button
              data-testid="decision-reject"
              disabled={phase.kind === "submitting" || comment.trim().length === 0}
              onClick={() => void submit("reject")}
              title={comment.trim().length === 0 ? "REJECT 必须填写理由" : undefined}
              className="rounded-md bg-red-600 px-4 py-1.5 text-[12.5px] font-medium text-white hover:bg-red-500 disabled:opacity-40"
            >
              Reject
            </button>
            {phase.kind === "submitting" ? (
              <span className="text-[12px] text-slate-400">提交中…(等待后端响应)</span>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
