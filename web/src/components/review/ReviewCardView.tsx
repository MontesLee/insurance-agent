/**
 * Review Card view (Phase 27.7.6 v2) — verbatim rendering of the
 * backend-generated human_review_card. No level re-derivation, no
 * flag recomputation: what the card says is what the reviewer sees.
 * Shared by the Review Queue (compact chips) and the Review Workspace
 * (full detail block).
 */
import type { ReviewCard, ReviewLevel } from "../../types/reviewCard";

const LEVEL_STYLE: Record<ReviewLevel, string> = {
  AUTO_PASS: "border-emerald-300 bg-emerald-50 text-emerald-700",
  SUMMARY_REVIEW: "border-amber-300 bg-amber-50 text-amber-700",
  DEEP_REVIEW: "border-red-300 bg-red-50 text-red-700",
};
const LEVEL_LABEL: Record<ReviewLevel, string> = {
  AUTO_PASS: "AUTO_PASS · 无需人工",
  SUMMARY_REVIEW: "SUMMARY_REVIEW · 卡片审核",
  DEEP_REVIEW: "DEEP_REVIEW · 深度审核",
};

export function RiskLevelBadge({ card }: { card: ReviewCard }) {
  return (
    <span
      data-testid={`card-level-${card.review_action.level}`}
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10.5px] font-semibold tracking-wide ${
        LEVEL_STYLE[card.review_action.level]
      }`}
    >
      {LEVEL_LABEL[card.review_action.level]}
      {card.validation_status === "FAIL" ? (
        <span className="font-mono">· VALIDATION FAIL</span>
      ) : null}
    </span>
  );
}

export function ValidationChips({ card }: { card: ReviewCard }) {
  const dims: [string, string][] = [
    ["Schema", card.automatic_validation.schema_check],
    ["Trace", card.automatic_validation.trace_check],
    ["Evidence", card.automatic_validation.evidence_check],
    ["Logic", card.automatic_validation.logic_check],
  ];
  return (
    <span data-testid="card-validation" className="inline-flex flex-wrap gap-1.5">
      {dims.map(([name, st]) => (
        <span
          key={name}
          className={`rounded px-1.5 py-0.5 text-[10.5px] font-medium ${
            st === "PASS"
              ? "bg-emerald-50 text-emerald-700"
              : "bg-red-50 text-red-700"
          }`}
        >
          {st === "PASS" ? "✓" : "⚠"} {name} {st}
        </span>
      ))}
    </span>
  );
}

/** First issue line for queue rows — highest severity flag message. */
export function topIssue(card: ReviewCard): string | null {
  if (card.risk_flags.length === 0) return null;
  const order = { HIGH: 0, MEDIUM: 1, LOW: 2 } as const;
  const sorted = [...card.risk_flags].sort(
    (a, b) => order[a.severity] - order[b.severity],
  );
  return sorted[0]?.message ?? null;
}

const SEV_STYLE: Record<string, string> = {
  HIGH: "border-red-200 bg-red-50 text-red-700",
  MEDIUM: "border-amber-200 bg-amber-50 text-amber-700",
  LOW: "border-slate-200 bg-slate-50 text-slate-600",
};

/**
 * Full card detail — the workspace's Review Card section. Sections:
 * customer context / agent decision / validation / risk findings /
 * failed checks (evidence refs). Artifacts stay available below as
 * the drill-down (sections C/D/E).
 */
export function ReviewCardDetail({ card }: { card: ReviewCard }) {
  const v = card.automatic_validation;
  const cs = card.customer_summary;
  const cust: [string, string | null | undefined][] = [
    ["年龄", cs.age], ["性别", cs.gender], ["婚姻", cs.marital_status],
    ["子女", cs.children], ["职业", cs.occupation],
    ["年收入", cs.annual_income], ["房贷", cs.mortgage],
    ["已有商业保险", cs.existing_insurance],
  ];
  return (
    <div data-testid="review-card-detail" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <RiskLevelBadge card={card} />
        <ValidationChips card={card} />
        <span className="text-[11px] text-slate-400">
          eval {v.eval_summary.passed}/{v.eval_summary.total} PASS
          {card.sampling.triggered ? " · 随机抽审命中" : ""}
        </span>
        <span className="ml-auto font-mono text-[10.5px] text-slate-400">
          {card.card_id} · {card.generator ?? "review-card-generator"}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-md border border-slate-200 p-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Customer Context 客户背景
          </p>
          <dl className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[12px]">
            {cust.map(([k, val]) => (
              <div key={k} className="flex gap-1.5">
                <dt className="w-20 shrink-0 text-slate-400">{k}</dt>
                <dd className="min-w-0 break-all text-slate-700">{val ?? "—"}</dd>
              </div>
            ))}
          </dl>
          {cs.unresolved && cs.unresolved.length > 0 ? (
            <p className="mt-1.5 text-[11px] text-amber-600">
              未确认字段:{cs.unresolved.join(", ")}
            </p>
          ) : null}
        </div>

        <div className="rounded-md border border-slate-200 p-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Agent Decision Agent 结论
          </p>
          <p className="mt-1.5 text-[12px] text-slate-700">
            案例状态:<span className="font-mono">{card.agent_summary.case_status}</span>
            {" · "}推荐状态:
            <span className="font-mono">
              {card.agent_summary.recommendation_status ?? "—"}
            </span>
          </p>
          {card.agent_summary.objective.length > 0 ? (
            <p className="mt-1 text-[12px] text-slate-600">
              目标:{card.agent_summary.objective.join("; ")}
            </p>
          ) : null}
          <p className="mt-1 text-[12px] text-slate-600">
            主推荐:
            {card.agent_summary.primary
              ? `${card.agent_summary.primary.product_name ?? card.agent_summary.primary.candidate_id}`
              : "无(见风险标记)"}
          </p>
          {card.agent_summary.risk_highlights.length > 0 ? (
            <ul className="mt-1.5 text-[11.5px] text-slate-500">
              {card.agent_summary.risk_highlights.map((r) => (
                <li key={r.risk_id}>
                  {r.risk_id} {r.risk_name ?? ""} · {r.severity ?? "—"}/
                  {r.residual_risk ?? "—"} · 缺口 {String(r.unprotected_amount ?? "—")}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>

      <div className="rounded-md border border-slate-200 p-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Risk Findings 风险发现
        </p>
        {card.risk_flags.length === 0 ? (
          <p className="mt-1 text-[12px] text-slate-400">无风险标记</p>
        ) : (
          <ul className="mt-1.5 flex flex-col gap-1">
            {card.risk_flags.map((f, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-1.5 text-[12px]">
                <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${SEV_STYLE[f.severity]}`}>
                  {f.severity}
                </span>
                <span className="text-slate-700">{f.message}</span>
                {f.evidence_ref ? (
                  <span className="font-mono text-[10.5px] text-slate-400">{f.evidence_ref}</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[11px] text-slate-400">
          触发依据:{card.review_action.reasons.join(" | ")}
        </p>
      </div>

      {v.failed_checks.length > 0 ? (
        <div className="rounded-md border border-red-200 bg-red-50/50 p-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-red-500">
            Failed Checks(深度审核入口,对应下方 C/D/E 证据)
          </p>
          <ul className="mt-1.5 flex flex-col gap-0.5 text-[11.5px] text-red-700">
            {v.failed_checks.map((fc, i) => (
              <li key={i} className="font-mono">
                {fc.eval_id ?? "—"} · {fc.artifact_type ?? "—"} · {fc.check_id}
                {fc.message ? ` — ${fc.message}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
