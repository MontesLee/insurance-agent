/**
 * Review Workspace (Phase 27.7.7) — HUMAN-READABLE redesign of 27.5-3.
 *
 * Same read-only contract (existing APIs only, no mutation, no
 * fabricated data), rebuilt around what an insurance advisor needs to
 * DECIDE, in this order:
 *
 *   1 Case Header        这是谁 · 核心诉求 · 审核状态
 *   2 Executive Summary  五张卡:需求/现有保障/主要缺口/Agent建议/审核状态
 *   3 Risk & Coverage    风险 → 当前 → 缺口 → 建议 (每行可展开判断依据)
 *   4 Solution           为什么这样设计 + 保障结构 + 取舍/未采用
 *   5 Product            为什么推荐 + 产品表 + 推荐依据 + 需要确认
 *   6 Human Review       🔴必须确认 / 🟡建议确认 / 🟢已验证
 *   F Decision + G Feedback (unchanged components, backend-authoritative)
 *   7 Deliverables       成果卡片 + 打开完整报告
 *   8 Agent 工作过程     人话步骤清单,详细执行记录折叠
 *   9 Technical Details  run/approval/registry/卡片/证据链/事件日志
 *
 * All business text comes from the ViewModel (components/review/viewModel.ts),
 * which copies artifact fields verbatim — components never parse payloads
 * and never author conclusions. Missing data renders 暂无信息.
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ApprovalRecord, SupervisorState } from "../../types/approval";
import type { RuntimeEvent } from "../../types/runtime";
import type { ReviewCard } from "../../types/reviewCard";
import type {
  ReviewWorkspaceVM,
  VMDeliverable,
  VMExecutionStep,
  VMHumanReview,
  VMNeed,
  VMProduct,
  VMSolution,
} from "../../types/reviewWorkspace";
import { Markdown } from "../Markdown";
import { ApprovalStatusBadge } from "./ApprovalStatusBadge";
import { DecisionPanel } from "./DecisionPanel";
import { FeedbackPanel } from "./FeedbackPanel";
import { ReviewCardDetail } from "./ReviewCardView";
import { buildReviewWorkspaceVM, type VMEvidence as VE } from "./viewModel";

type Async<T> =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: T };

function useAsync<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<Async<T>>({ kind: "loading" });
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    setState({ kind: "loading" });
    load()
      .then((data) => alive && setState({ kind: "ready", data }))
      .catch((e) =>
        alive &&
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : String(e),
        }),
      );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  const retry = useCallback(() => setNonce((n) => n + 1), []);
  return { state, retry };
}

const DASH = "—";
const EMPTY = "暂无信息";

/** Artifact types the workspace loads eagerly (absent ones degrade softly). */
const ALL_ARTIFACT_TYPES = [
  "client-profile", "requirement-analysis", "risk-assessment",
  "coverage-gap-analysis", "solution-plan", "product-candidates",
  "product-recommendation", "knowledge-evidence", "insurance-report",
];

function waitingSince(createdAt: string): string {
  const t = Date.parse(createdAt);
  if (Number.isNaN(t)) return DASH;
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  return mins < 60 ? `${mins} 分钟` : `${Math.floor(mins / 60)} 小时 ${mins % 60} 分`;
}

const APPROVAL_TONE: Record<string, { label: string; cls: string }> = {
  WAITING_HUMAN: { label: "待人工审核", cls: "bg-amber-50 text-amber-800 border-amber-300" },
  PENDING: { label: "待处理", cls: "bg-amber-50 text-amber-800 border-amber-300" },
  APPROVED: { label: "已批准", cls: "bg-emerald-50 text-emerald-800 border-emerald-300" },
  REJECTED: { label: "已拒绝", cls: "bg-slate-100 text-slate-600 border-slate-300" },
  EXPIRED: { label: "已过期", cls: "bg-slate-100 text-slate-600 border-slate-300" },
  RESUMED: { label: "已恢复执行", cls: "bg-slate-100 text-slate-600 border-slate-300" },
};

const SEV_TONE: Record<string, string> = {
  CRITICAL: "text-red-700", HIGH: "text-orange-700",
  MEDIUM: "text-amber-700", LOW: "text-slate-500",
};

function severityTone(raw: string | null): string {
  return (raw && SEV_TONE[raw.toUpperCase()]) || "text-slate-600";
}

// --------------------------------------------------------------------------- #
// Section shells
// --------------------------------------------------------------------------- #
function Section({
  n,
  title,
  hint,
  children,
}: {
  n?: string;
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white px-5 py-4">
      <div className="flex items-baseline gap-2">
        {n ? (
          <span className="text-[11px] font-semibold text-slate-300">{n}</span>
        ) : null}
        <h3 className="text-[14px] font-semibold tracking-tight text-slate-800">{title}</h3>
        {hint ? <span className="text-[11.5px] text-slate-400">{hint}</span> : null}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function NotAvailable({ text = EMPTY }: { text?: string }) {
  return <span className="text-slate-400">{text}</span>;
}

// --------------------------------------------------------------------------- #
// 1 — Case Header
// --------------------------------------------------------------------------- #
function APPROVAL_BADGE(a: ApprovalRecord) {
  const tone = APPROVAL_TONE[a.status] ?? { label: a.status, cls: "bg-slate-100 text-slate-600 border-slate-300" };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[12px] font-medium ${tone.cls}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {tone.label}
    </span>
  );
}

function CaseHeader({
  approval,
  vm,
  onStartReview,
}: {
  approval: ApprovalRecord;
  vm: ReviewWorkspaceVM;
  onStartReview: () => void;
}) {
  const [showProfile, setShowProfile] = useState(false);
  const c = vm.customer;
  return (
    <div data-testid="workspace-header" className="rounded-xl border border-slate-200 bg-white px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 className="text-[19px] font-semibold tracking-tight text-slate-900">
              {c.demographicLine ?? c.caseTitle ?? "客户案例"}
            </h2>
            {APPROVAL_BADGE(approval)}
            <span className="text-[11.5px] text-slate-400">已等待 {waitingSince(approval.created_at)}</span>
          </div>
          {c.caseTitle && c.demographicLine ? (
            <p className="mt-1 text-[12.5px] text-slate-500">{c.caseTitle}</p>
          ) : null}
          <div className="mt-2.5">
            <p className="text-[11.5px] font-medium text-slate-400">核心诉求</p>
            <p className="mt-0.5 text-[13.5px] text-slate-700">
              {c.needHeadline ?? <NotAvailable />}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            data-testid="show-client-profile"
            onClick={() => setShowProfile((v) => !v)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-600 hover:bg-slate-50"
          >
            查看客户资料
          </button>
          <button
            data-testid="start-human-review"
            onClick={onStartReview}
            className="rounded-lg bg-slate-800 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-slate-700"
          >
            开始人工审核
          </button>
        </div>
      </div>
      {showProfile ? (
        <dl data-testid="client-profile-fields" className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 border-t border-slate-100 pt-3 text-[12.5px] sm:grid-cols-3">
          {c.fields.map((f) => (
            <div key={f.label} className="flex gap-2">
              <dt className="w-20 shrink-0 text-slate-400">{f.label}</dt>
              <dd className="min-w-0 break-all text-slate-700">
                {f.value ?? <NotAvailable text="未确认" />}
                {f.status && f.status !== "KNOWN" ? (
                  <span className="ml-1 text-[11px] text-amber-600">（{f.status}）</span>
                ) : null}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------- #
// 2 — Executive Summary
// --------------------------------------------------------------------------- #
function SummaryCard({
  q,
  a,
  tone,
}: {
  q: string;
  a: string | null;
  tone?: "ok" | "warn" | "alert";
}) {
  const toneCls =
    tone === "alert" ? "text-red-700"
    : tone === "warn" ? "text-amber-700"
    : tone === "ok" ? "text-emerald-700"
    : "text-slate-800";
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <p className="text-[11.5px] font-medium text-slate-400">{q}</p>
      <p className={`mt-1 text-[13px] leading-relaxed ${toneCls}`}>
        {a ?? <NotAvailable />}
      </p>
    </div>
  );
}

function ExecutiveSummary({ vm }: { vm: ReviewWorkspaceVM }) {
  const s = vm.summary;
  return (
    <div data-testid="workspace-summary" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <SummaryCard q="客户需求" a={s.need} />
      <SummaryCard q="当前保障" a={s.currentCoverage} />
      <SummaryCard q="主要保障缺口" a={s.mainGap} tone={s.mainGap ? "alert" : undefined} />
      <SummaryCard q="Agent 建议" a={s.agentAdvice} />
      <SummaryCard q="审核状态" a={s.reviewStatus.text} tone={s.reviewStatus.tone} />
      {vm.needs.length > 1 ? <NeedsDetail needs={vm.needs} /> : null}
    </div>
  );
}

function NeedsDetail({ needs }: { needs: VMNeed[] }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 sm:col-span-2">
      <p className="text-[11.5px] font-medium text-slate-400">全部需求（{needs.length} 项）</p>
      <ul className="mt-1 space-y-0.5 text-[12.5px] text-slate-700">
        {needs.map((n) => (
          <li key={n.id ?? n.summary}>
            <span className="mr-1.5 text-slate-400">{n.priorityLabel ?? ""}</span>
            [{n.typeLabel ?? "—"}] {n.summary ?? EMPTY}
          </li>
        ))}
      </ul>
    </div>
  );
}

// --------------------------------------------------------------------------- #
// 3 — Risk & Coverage Gap
// --------------------------------------------------------------------------- #
function EvidenceInline({ refs, evidence }: { refs: string[]; evidence: VE[] }) {
  if (refs.length === 0) return null;
  const byId = new Map(evidence.map((e) => [e.id, e]));
  return (
    <div className="mt-2">
      <p className="text-[11.5px] font-medium text-slate-400">证据来源</p>
      <ul className="mt-1 space-y-1.5 border-l-2 border-slate-100 pl-3">
        {refs.map((ref) => {
          const ev = byId.get(ref);
          return (
            <li key={ref} className="text-[12px] text-slate-600">
              <span className="font-mono text-[11px] text-slate-400">{ref}</span>
              {ev ? (
                <>
                  <p className="mt-0.5 leading-relaxed">{ev.content ?? EMPTY}</p>
                  <p className="text-[11px] text-slate-400">
                    来源：{ev.source ?? DASH}{ev.section ? ` · ${ev.section}` : ""}
                  </p>
                </>
              ) : (
                <p className="mt-0.5 text-[11.5px] text-amber-600">未在知识证据中找到该引用</p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function RiskGapSection({ vm }: { vm: ReviewWorkspaceVM }) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (key: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  return (
    <div data-testid="workspace-risks">
      {vm.risks.length === 0 ? (
        <p className="py-2 text-[12.5px] text-slate-400">{EMPTY}（本运行未产出风险分析）</p>
      ) : (
        <table className="w-full border-collapse text-[12.5px]">
          <thead>
            <tr className="border-b border-slate-200 text-left text-[11.5px] text-slate-400">
              <th className="py-1.5 pr-2 font-medium">风险</th>
              <th className="py-1.5 pr-2 font-medium">当前情况</th>
              <th className="py-1.5 pr-2 font-medium">保障缺口</th>
              <th className="py-1.5 font-medium">Agent 建议</th>
            </tr>
          </thead>
          <tbody>
            {vm.risks.map((r) => {
              const key = r.riskId ?? r.gapId ?? r.name ?? "";
              const isOpen = open.has(key);
              return (
                <Fragment key={key}>
                  <tr
                    key={key}
                    data-testid={`risk-row-${key}`}
                    className="cursor-pointer border-b border-slate-100 align-top hover:bg-slate-50/60"
                    onClick={() => toggle(key)}
                  >
                    <td className="py-2 pr-2">
                      <span className={`font-medium ${severityTone(r.gapLevelRaw ?? r.severityRaw)}`}>
                        {r.severityLabel ? `${r.severityLabel} · ` : ""}
                      </span>
                      <span className="text-slate-800">{r.name ?? EMPTY}</span>
                      <span className="ml-1 text-[10.5px] text-slate-300">{isOpen ? "▾" : "▸"}</span>
                    </td>
                    <td className="py-2 pr-2 text-slate-600">{r.current ?? <NotAvailable />}</td>
                    <td className="py-2 pr-2 text-slate-600">
                      {r.gapLevelLabel ? (
                        <span className={`font-medium ${severityTone(r.gapLevelRaw)}`}>{r.gapLevelLabel}</span>
                      ) : null}
                      {r.gapLevelLabel && r.unprotectedLabel ? " · " : ""}
                      {r.unprotectedLabel ? <span>{r.unprotectedLabel}</span> : null}
                      {!r.gapLevelLabel && !r.unprotectedLabel ? <NotAvailable /> : null}
                    </td>
                    <td className="py-2 text-slate-600">{r.advice ?? <NotAvailable />}</td>
                  </tr>
                  {isOpen ? (
                    <tr className="border-b border-slate-100">
                      <td colSpan={4} className="bg-slate-50/60 px-4 py-3">
                        <p className="text-[11.5px] font-medium text-slate-400">为什么得出这个结论？</p>
                        <ul className="mt-1 space-y-1 text-[12px] text-slate-600">
                          {r.rationale.conclusion ? (
                            <li><span className="text-slate-400">结论：</span>{r.rationale.conclusion}</li>
                          ) : null}
                          {r.rationale.reason ? (
                            <li><span className="text-slate-400">判断理由：</span>{r.rationale.reason}</li>
                          ) : null}
                          {r.rationale.gapReason ? (
                            <li><span className="text-slate-400">缺口判定：</span>{r.rationale.gapReason}</li>
                          ) : null}
                          <li className="text-slate-500">
                            测算：
                            {r.rationale.protectedLabel !== null ? `已保障 ${r.rationale.protectedLabel}` : "已保障 无数据"}
                            {" / "}
                            {r.rationale.unprotectedLabel !== null ? `未保障 ${r.rationale.unprotectedLabel}` : "未保障 无数据"}
                            {r.rationale.confidence !== null ? `（置信度 ${r.rationale.confidence}）` : ""}
                          </li>
                          {r.rationale.targetRationale ? (
                            <li><span className="text-slate-400">建议方向依据：</span>{r.rationale.targetRationale}</li>
                          ) : null}
                          <li className="font-mono text-[11px] text-slate-400">
                            {r.riskId ?? DASH} · {r.gapId ?? DASH}
                            {r.rationale.residual ? ` · 残余风险 ${r.rationale.residual}` : ""}
                            {r.rationale.likelihood ? ` · 可能性 ${r.rationale.likelihood}` : ""}
                          </li>
                        </ul>
                        <EvidenceInline refs={r.rationale.evidenceRefs} evidence={vm.evidence} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
      <p className="mt-2 text-[11px] text-slate-400">点击任意一行可展开判断依据与证据原文。</p>
    </div>
  );
}

// --------------------------------------------------------------------------- #
// 4 — Solution
// --------------------------------------------------------------------------- #
function SolutionSection({ vm }: { vm: ReviewWorkspaceVM }) {
  if (vm.solutions.length === 0)
    return <p className="py-2 text-[12.5px] text-slate-400">{EMPTY}（本运行未产出解决方案）</p>;
  const head = vm.solutions[0];
  return (
    <div data-testid="workspace-solution" className="flex flex-col gap-4">
      <div>
        <p className="text-[11.5px] font-medium text-slate-400">为什么这样设计？</p>
        <p className="mt-1 text-[13px] leading-relaxed text-slate-700">
          {head?.reason ?? <NotAvailable />}
        </p>
      </div>
      <div>
        <p className="text-[11.5px] font-medium text-slate-400">保障结构</p>
        <ul className="mt-1.5 space-y-1.5">
          {vm.solutions.map((s: VMSolution) => (
            <li key={s.id ?? s.objective} className="text-[12.5px] text-slate-700">
              <span className="mr-1.5 inline-block rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">
                {s.priorityLabel ?? DASH}
              </span>
              <span className="font-medium">{s.typeLabel ?? DASH}</span>
              <span className="text-slate-500"> — {s.objective ?? EMPTY}</span>
              {s.direction ? (
                <p className="ml-1 mt-0.5 text-[12px] text-slate-500">{s.direction}</p>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
      {vm.solutions.some((s) => s.rejected.length > 0 || s.tradeoffs.length > 0) ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-slate-100 bg-slate-50/50 px-3 py-2.5">
            <p className="text-[11.5px] font-medium text-slate-400">考虑过但未采用</p>
            <ul className="mt-1 space-y-1 text-[12px] text-slate-600">
              {vm.solutions.flatMap((s) =>
                s.rejected.map((r) => (
                  <li key={`${s.id}-${r.direction}`}>
                    <span className="font-medium">{r.direction ?? DASH}</span>
                    <span className="text-slate-400"> — {r.reason ?? EMPTY}</span>
                  </li>
                )),
              )}
            </ul>
          </div>
          <div className="rounded-lg border border-slate-100 bg-slate-50/50 px-3 py-2.5">
            <p className="text-[11.5px] font-medium text-slate-400">关键取舍</p>
            <ul className="mt-1 space-y-1 text-[12px] text-slate-600">
              {vm.solutions.flatMap((s) =>
                s.tradeoffs.map((t, i) => (
                  <li key={`${s.id}-t${i}`}>
                    <span className="font-medium">{t.axis ?? DASH}</span>
                    ：选择「{t.chosen ?? DASH}」— {t.reason ?? EMPTY}
                  </li>
                )),
              )}
            </ul>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------- #
// 5 — Product Recommendation
// --------------------------------------------------------------------------- #
function ProductSection({ vm }: { vm: ReviewWorkspaceVM }) {
  const rec = vm.recommendation;
  if (!rec)
    return (
      <p data-testid="workspace-products" className="py-2 text-[12.5px] text-slate-400">
        {EMPTY}（本运行未产出产品推荐 —— 证据不足或流程未到达该阶段）
      </p>
    );
  const p: VMProduct | null = rec.primary;
  return (
    <div data-testid="workspace-products" className="flex flex-col gap-4">
      {p === null ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50/70 px-4 py-3">
          <p className="text-[13px] font-medium text-amber-800">本次未形成主推荐</p>
          {rec.noPrimaryReasons.length > 0 ? (
            <ul className="mt-1.5 space-y-1 text-[12px] text-amber-800/90">
              {rec.noPrimaryReasons.map((r, i) => (
                <li key={i}>· {r}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-[12px] text-amber-800/80">暂无具体原因记录</p>
          )}
          <p className="mt-1.5 text-[11.5px] text-amber-700">
            需要人工判断后续方向（人工确认 / 补充信息后重跑）。
          </p>
        </div>
      ) : (
        <>
          <div>
            <p className="text-[11.5px] font-medium text-slate-400">为什么推荐这个产品？</p>
            <p className="mt-1 text-[13px] leading-relaxed text-slate-700">{p.why ?? <NotAvailable />}</p>
          </div>
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[11.5px] text-slate-400">
                <th className="py-1.5 pr-2 font-medium">产品</th>
                <th className="py-1.5 pr-2 font-medium">解决什么问题</th>
                <th className="py-1.5 pr-2 text-right font-medium">年保费</th>
                <th className="py-1.5 pr-2 text-right font-medium">保障期限</th>
                <th className="py-1.5 font-medium">核心保障</th>
              </tr>
            </thead>
            <tbody>
              {[p, ...rec.alternatives].map((x) => (
                <tr key={x.candidateId} className="border-b border-slate-100 align-top">
                  <td className="py-2 pr-2">
                    <span className="font-medium text-slate-800">{x.name ?? x.candidateId}</span>
                    {x.company ? <p className="text-[11px] text-slate-400">{x.company}</p> : null}
                  </td>
                  <td className="py-2 pr-2 text-slate-600">
                    {x.solves.length > 0 ? x.solves.join("；") : <NotAvailable />}
                  </td>
                  <td className="py-2 pr-2 text-right text-slate-700">
                    {x.premiumAnnual !== null ? `¥${x.premiumAnnual.toLocaleString("zh-CN")}` : <NotAvailable />}
                  </td>
                  <td className="py-2 pr-2 text-right text-slate-700">
                    {x.termYears !== null ? `${x.termYears} 年` : <NotAvailable />}
                  </td>
                  <td className="py-2 text-slate-600">
                    {x.features.length > 0 ? x.features.join("、") : <NotAvailable />}
                    {x.deductible ? <span className="text-slate-400">（免赔额 {x.deductible}）</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-100 bg-slate-50/50 px-3 py-2.5">
              <p className="text-[11.5px] font-medium text-slate-400">推荐依据</p>
              <ul className="mt-1 space-y-0.5 text-[12px] text-slate-600">
                <li>需求匹配：{p.fit ?? DASH}{p.evidenceStatus ? ` · 证据状态 ${p.evidenceStatus}` : ""}</li>
                {p.provenance
                  .filter((pr) => pr.type !== "knowledge")
                  .map((pr, i) => (
                    <li key={`pk${i}`} className="font-mono text-[11px] text-slate-400">
                      {pr.type}:{pr.ref}
                    </li>
                  ))}
              </ul>
              <EvidenceInline
                refs={p.provenance.filter((pr) => pr.type === "knowledge").map((pr) => pr.ref)}
                evidence={vm.evidence}
              />
            </div>
            <div className="rounded-lg border border-slate-100 bg-slate-50/50 px-3 py-2.5">
              <p className="text-[11.5px] font-medium text-slate-400">需要确认</p>
              {p.confirmations.length > 0 ? (
                <ul className="mt-1 space-y-1 text-[12px] text-amber-800">
                  {p.confirmations.map((c, i) => (
                    <li key={i}>· {c.label}{c.detail ? `（${c.detail}）` : ""}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-[12px] text-slate-500">核保校验未发现待确认项（见技术详情）</p>
              )}
              <p className="mt-2 text-[11px] text-slate-400">
                健康告知、既往保障与具体条款需线下核实（系统暂无对应数据）。
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- #
// 6 — Human Review
// --------------------------------------------------------------------------- #
function HumanReviewSection({ hr }: { hr: VMHumanReview }) {
  return (
    <div data-testid="workspace-human-review" className="flex flex-col gap-3">
      <div>
        <p className="text-[12.5px] font-semibold text-red-700">🔴 需要你确认（{hr.must.length}）</p>
        {hr.must.length === 0 ? (
          <p className="mt-1 text-[12.5px] text-slate-400">无</p>
        ) : (
          <ul className="mt-1.5 space-y-1.5">
            {hr.must.map((it, i) => (
              <li key={i} className="rounded-md border border-red-100 bg-red-50/50 px-3 py-2">
                <p className="text-[12.5px] text-red-900">{it.title}</p>
                {it.detail ? <p className="mt-0.5 font-mono text-[11px] text-red-700/70">{it.detail}</p> : null}
                <p className="mt-0.5 text-[11px] text-slate-400">来源：{it.source}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="text-[12.5px] font-semibold text-amber-700">🟡 建议确认（{hr.suggest.length}）</p>
        {hr.suggest.length === 0 ? (
          <p className="mt-1 text-[12.5px] text-slate-400">无</p>
        ) : (
          <ul className="mt-1.5 space-y-1.5">
            {hr.suggest.map((it, i) => (
              <li key={i} className="rounded-md border border-amber-100 bg-amber-50/40 px-3 py-2">
                <p className="text-[12.5px] text-amber-900">{it.title}</p>
                {it.detail ? <p className="mt-0.5 text-[11.5px] text-amber-800/80">{it.detail}</p> : null}
                <p className="mt-0.5 text-[11px] text-slate-400">来源：{it.source}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="text-[12.5px] font-semibold text-emerald-700">🟢 已验证</p>
        <p className="mt-1 text-[12.5px] text-slate-600">
          {hr.verifiedNote ?? "暂无已确认的客户资料记录"}
        </p>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- #
// 7 — Deliverables
// --------------------------------------------------------------------------- #
const DELIV_ICON: Record<string, string> = {
  "insurance-report": "📄", "product-recommendation": "🔎",
  "coverage-gap-analysis": "🧩", "risk-assessment": "⚠️",
  "solution-plan": "🛡️", "requirement-analysis": "📋",
  "product-candidates": "🗂️", "knowledge-evidence": "📚", "client-profile": "👤",
};

function DeliverablesSection({ vm }: { vm: ReviewWorkspaceVM }) {
  const [reportOpen, setReportOpen] = useState(false);
  const cards: VMDeliverable[] = vm.deliverables.filter((d) => !d.isReport);
  if (vm.deliverables.length === 0)
    return <p data-testid="workspace-deliverables" className="py-2 text-[12.5px] text-slate-400">{EMPTY}（本运行未生成产物）</p>;
  return (
    <div data-testid="workspace-deliverables" className="flex flex-col gap-3">
      {vm.reportMarkdown ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50/40 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-[13.5px] font-semibold text-slate-800">
                📄 {vm.reportTitle ?? "方案报告"}
              </p>
              <p className="mt-0.5 text-[11.5px] text-slate-400">
                生成时间:{vm.reportGeneratedAt?.replace("T", " ").slice(0, 19) ?? DASH}
                {" "}· 已生成 · 待人工审核
              </p>
            </div>
            <button
              data-testid="open-full-report"
              onClick={() => setReportOpen((v) => !v)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-100"
            >
              {reportOpen ? "收起完整报告" : "打开完整报告"}
            </button>
          </div>
          {reportOpen ? (
            <div data-testid="full-report" className="mt-3 max-h-[32rem] overflow-y-auto rounded-md border border-slate-200 bg-white px-4 py-3">
              <Markdown text={vm.reportMarkdown} />
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((d) => (
          <div key={d.artifactType} className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
            <p className="text-[12.5px] font-medium text-slate-700">
              {DELIV_ICON[d.artifactType] ?? "📦"} {d.titleLabel}
            </p>
            <p className="mt-0.5 text-[11px] text-slate-400">{d.statusLabel ?? DASH}</p>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-slate-400">原始数据与完整 JSON 见底部「技术详情」。</p>
    </div>
  );
}

// --------------------------------------------------------------------------- #
// 8 — Agent execution (human verbs; raw log demoted)
// --------------------------------------------------------------------------- #
function ExecutionSection({ steps, events }: { steps: VMExecutionStep[]; events: RuntimeEvent[] | null }) {
  return (
    <div data-testid="workspace-execution">
      {steps.length === 0 ? (
        <p className="py-2 text-[12.5px] text-slate-400">{EMPTY}（无执行记录）</p>
      ) : (
        <ul className="space-y-1">
          {steps.map((s) => (
            <li key={s.key} data-testid={`exec-${s.stage}`} className="text-[12.5px]">
              <span className={s.status === "completed" ? "text-emerald-600" : "text-red-600"}>
                {s.status === "completed" ? "✓" : "✗"}
              </span>{" "}
              <span className={s.status === "completed" ? "text-slate-700" : "text-red-700 font-medium"}>
                {s.status === "completed" ? `已完成${s.label}` : `${s.label}失败`}
              </span>
            </li>
          ))}
        </ul>
      )}
      <details className="mt-2">
        <summary className="cursor-pointer text-[12px] text-slate-500">查看详细执行记录</summary>
        <div data-testid="workspace-timeline" className="mt-2 max-h-72 overflow-y-auto rounded-md border border-slate-100 bg-slate-50/60 p-2">
          {(events ?? []).length === 0 ? (
            <p className="text-[12px] text-slate-400">无事件记录</p>
          ) : (
            <ul>
              {(events ?? []).map((e) => (
                <li key={e.event_id} className="flex gap-2.5 py-0.5 font-mono text-[11px] text-slate-500">
                  <span className="w-16 shrink-0">{e.timestamp.slice(11, 19)}</span>
                  <span className="w-36 shrink-0">{e.event_type}</span>
                  <span className="w-40 shrink-0 truncate">{e.stage ?? e.skill ?? ""}</span>
                  <span className="min-w-0 flex-1 truncate">{e.message ?? ""}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
    </div>
  );
}

// --------------------------------------------------------------------------- #
// 9 — Technical Details (everything internal, collapsed)
// --------------------------------------------------------------------------- #
function KV({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-24 shrink-0 text-slate-400">{k}</dt>
      <dd className="min-w-0 break-all text-slate-700">{v}</dd>
    </div>
  );
}

function TechnicalDetails({
  approval,
  supervisor,
  runRaw,
  vm,
  artifacts,
  runId,
  contextArtifactIds,
  reviewCard,
}: {
  approval: ApprovalRecord;
  supervisor: SupervisorState | null;
  runRaw: unknown;
  vm: ReviewWorkspaceVM;
  artifacts: { artifact_id?: string; artifact_type: string; producer_stage?: string | null; status?: string | null }[];
  runId: string | null;
  contextArtifactIds?: string[];
  reviewCard: ReviewCard | null;
}) {
  const run = (runRaw ?? null) as Record<string, unknown> | null;
  return (
    <details data-testid="workspace-technical" className="rounded-xl border border-slate-200 bg-white px-5 py-3">
      <summary className="cursor-pointer text-[13px] font-semibold text-slate-600">
        技术详情（运行 / 审批 / 产物 / 卡片 / 证据链）
      </summary>
      <div className="mt-3 flex flex-col gap-4 text-[12px]">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">运行信息</p>
          <dl data-testid="run-linked" className="mt-1 grid grid-cols-2 gap-x-6 gap-y-0.5 sm:grid-cols-3">
            <KV k="Run ID" v={runId ?? DASH} />
            <KV k="Case" v={vm.customer.caseId ?? DASH} />
            <KV k="运行状态" v={String(run?.status ?? DASH)} />
            <KV k="restored" v={String(run?.restored ?? false)} />
            {run?.result_status ? <KV k="result_status" v={String(run.result_status)} /> : null}
          </dl>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">审批记录（verbatim）</p>
          <div data-testid="workspace-approval" className="mt-1">
            <div className="flex items-center gap-2">
              <ApprovalStatusBadge status={approval.status} />
              <span className="font-mono text-[11px] text-slate-400">{approval.approval_id}</span>
            </div>
            <dl className="mt-1.5 grid grid-cols-2 gap-x-6 gap-y-0.5 sm:grid-cols-3">
              <KV k="类型" v={approval.request_type} />
              <KV k="项目" v={approval.project_id} />
              <KV k="Task" v={approval.task_id || DASH} />
              <KV k="创建时间" v={approval.created_at?.replace("T", " ") ?? DASH} />
              <KV k="决定" v={approval.decision ?? DASH} />
              <KV k="决定人" v={approval.resolved_by ?? DASH} />
            </dl>
            {approval.reason ? (
              <p className="mt-1.5 rounded-md bg-slate-50 p-2 text-[12px] text-slate-600">{approval.reason}</p>
            ) : null}
            {contextArtifactIds && contextArtifactIds.length > 0 ? (
              <p data-testid="review-context-artifacts" className="mt-1 text-[11.5px] text-slate-500">
                审批关联的交付物:{contextArtifactIds.join(", ")}
              </p>
            ) : null}
          </div>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">监督状态</p>
          <div data-testid="workspace-case" className="mt-1">
            {supervisor ? (
              <dl className="grid grid-cols-2 gap-x-6 gap-y-0.5 sm:grid-cols-3">
                <KV k="项目状态" v={supervisor.status} />
                <KV k="风险级别" v={supervisor.risk_level} />
                <KV k="更新时间" v={supervisor.updated_at?.replace("T", " ") ?? DASH} />
              </dl>
            ) : (
              <p className="text-slate-400">暂无监督状态</p>
            )}
          </div>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">产物注册表（原始）</p>
          <div data-testid="workspace-artifacts" className="mt-1">
            <ArtifactRegistry runId={runId} artifacts={artifacts} />
          </div>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">证据链（原始视图）</p>
          <div data-testid="workspace-evidence" className="mt-1">
            <EvidenceChainRaw vm={vm} />
          </div>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Review Card（完整卡片）</p>
          <div className="mt-1">
            {reviewCard ? (
              <ReviewCardDetail card={reviewCard} />
            ) : (
              <p className="text-slate-400">无 Review Card（该审批未携带运行上下文）</p>
            )}
          </div>
        </div>
      </div>
    </details>
  );
}

async function writeClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try {
    if (!document.execCommand("copy")) throw new Error("execCommand failed");
  } finally {
    document.body.removeChild(ta);
  }
}

function ArtifactRegistry({
  runId,
  artifacts,
}: {
  runId: string | null;
  artifacts: { artifact_id?: string; artifact_type: string; producer_stage?: string | null; status?: string | null }[];
}) {
  const [openType, setOpenType] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<{ type: string; ok: boolean } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const detail = useAsync(
    () => (runId && openType ? api.getArtifact(runId, openType) : Promise.resolve(null)),
    [openType],
  );
  if (artifacts.length === 0)
    return <p className="text-slate-400">暂无产物记录</p>;
  const copy = async (type: string) => {
    if (!runId) return;
    try {
      const d = await api.getArtifact(runId, type);
      const payload = (d as { artifact?: unknown }).artifact ?? d;
      await writeClipboard(JSON.stringify(payload, null, 2));
      setCopyState({ type, ok: true });
    } catch {
      setCopyState({ type, ok: false });
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopyState(null), 2000);
  };
  return (
    <div className="flex flex-col gap-1">
      <ul>
        {artifacts.map((a) => (
          <li key={a.artifact_type} className="flex items-stretch gap-1.5">
            <button
              data-testid={`workspace-artifact-${a.artifact_type}`}
              onClick={() => setOpenType(openType === a.artifact_type ? null : a.artifact_type)}
              className="min-w-0 flex-1 rounded border border-slate-200 px-2 py-1 text-left text-[11.5px] hover:bg-slate-50"
            >
              <span className="font-mono text-slate-600">{a.artifact_type}</span>
              <span className="ml-2 text-slate-400">{a.artifact_id ?? DASH}</span>
              <span className="float-right text-slate-400">{a.producer_stage ?? DASH}</span>
            </button>
            <button
              data-testid={`workspace-artifact-copy-${a.artifact_type}`}
              onClick={() => copy(a.artifact_type)}
              className={
                copyState?.type === a.artifact_type
                  ? copyState.ok
                    ? "shrink-0 rounded border border-emerald-300 bg-emerald-50 px-2 text-[11px] text-emerald-700"
                    : "shrink-0 rounded border border-red-300 bg-red-50 px-2 text-[11px] text-red-600"
                  : "shrink-0 rounded border border-slate-200 px-2 text-[11px] text-slate-500 hover:bg-slate-50"
              }
            >
              {copyState?.type === a.artifact_type ? (copyState.ok ? "已复制" : "复制失败") : "复制 JSON"}
            </button>
          </li>
        ))}
      </ul>
      {openType ? (
        <div className="rounded border border-slate-200 bg-slate-50 p-2">
          {detail.state.kind === "loading" ? (
            <p className="text-[11.5px] text-slate-400">Loading...</p>
          ) : detail.state.kind === "error" ? (
            <p className="text-[11.5px] text-red-600">加载失败:{detail.state.message}</p>
          ) : (
            <pre className="max-h-56 overflow-auto text-[10.5px] text-slate-600">
              {JSON.stringify((detail.state.data as { artifact?: unknown } | null)?.artifact ?? detail.state.data, null, 2)}
            </pre>
          )}
        </div>
      ) : null}
    </div>
  );
}

function EvidenceChainRaw({ vm }: { vm: ReviewWorkspaceVM }) {
  const rec = vm.recommendation;
  const blocks: { key: string; title: string; refs: { type: string; ref: string }[]; missing: boolean }[] = [];
  if (rec?.primary) {
    blocks.push({
      key: `primary-${rec.primary.candidateId}`,
      title: `主推荐:${rec.primary.name ?? rec.primary.candidateId}`,
      refs: rec.primary.provenance,
      missing: !rec.primary.provenance.some((r) => r.type === "knowledge"),
    });
  }
  for (const c of rec?.insufficient ?? []) {
    blocks.push({
      key: `cand-${c.candidateId}`,
      title: `候选 ${c.candidateId}（insufficient_evidence）`,
      refs: c.provenance,
      missing: true,
    });
  }
  if (blocks.length === 0)
    return <p className="text-slate-400">No evidence linked（该 Run 无推荐产物或无 provenance）</p>;
  return (
    <div className="flex flex-col gap-2">
      {blocks.map((b) => (
        <div key={b.key} className="rounded border border-slate-200 p-2">
          <p className="text-[12px] font-medium text-slate-700">{b.title}</p>
          <div className="mt-1.5 space-y-1 border-l-2 border-slate-100 pl-2.5">
            {b.refs.length === 0 ? (
              <p className="text-[11.5px] text-slate-400">No evidence linked</p>
            ) : (
              b.refs.map((r, i) => {
                const ev = vm.evidence.find((e) => e.id === r.ref);
                return (
                  <div key={i} className="text-[11.5px]">
                    <span className="mr-1.5 rounded bg-slate-100 px-1 text-[10px] font-semibold uppercase text-slate-500">{r.type}</span>
                    <span className="font-mono text-slate-600">{r.ref}</span>
                    {ev ? (
                      <div className="mt-0.5 border-l border-slate-200 pl-2 text-slate-500">
                        <p>{ev.content}</p>
                        <p className="text-[10.5px] text-slate-400">来源:{ev.source || DASH}</p>
                      </div>
                    ) : r.type === "knowledge" ? (
                      <p className="text-amber-600">No evidence linked（知识库中无此引用）</p>
                    ) : null}
                  </div>
                );
              })
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- #
// Workspace orchestrator
// --------------------------------------------------------------------------- #
interface RunBundleRaw {
  run: unknown;
  events: RuntimeEvent[] | null;
  artifacts: NonNullable<Awaited<ReturnType<typeof api.getArtifacts>>>["artifacts"];
  details: Record<string, unknown>;
  reviewCard: ReviewCard | null;
  supervisor: SupervisorState | null;
  caseDesc: string | null;
}

export function ReviewWorkspace({
  projectId,
  approvalId,
  onBack,
}: {
  projectId: string;
  approvalId: string;
  onBack: () => void;
}) {
  const approvalQ = useAsync(() => api.getApproval(approvalId), [approvalId]);

  const approval: ApprovalRecord | null =
    approvalQ.state.kind === "ready" ? approvalQ.state.data.approval : null;
  const reviewContext =
    approvalQ.state.kind === "ready" ? approvalQ.state.data.review_context : undefined;
  const contextRunId: string | null =
    reviewContext?.run_id ??
    ((approval?.context as Record<string, unknown> | null)?.run_id as string | undefined) ??
    null;
  const contextArtifactIds =
    reviewContext?.artifact_ids ??
    ((approval?.context as Record<string, unknown> | null)?.artifact_ids as string[] | undefined);

  // One bundle: everything the run pages need, fetched in parallel.
  // 404s are soft (artifact simply absent); transport failure is loud.
  const bundleQ = useAsync(async (): Promise<RunBundleRaw | null> => {
    if (!contextRunId) return null;
    const soft = <T,>(p: Promise<T>): Promise<T | null> =>
      p.catch((e) => {
        if (e instanceof ApiError && e.status === 0) throw e;
        return null;
      });
    const [run, events, artifacts, reviewCard, supervisor, cases] = await Promise.all([
      soft(api.getRun(contextRunId)),
      soft(api.getEvents(contextRunId)),
      soft(api.getArtifacts(contextRunId)),
      soft(api.reviewCard(contextRunId)),
      soft(api.supervisor(projectId)),
      soft(api.cases()),
    ]);
    const details: Record<string, unknown> = {};
    await Promise.all(
      ALL_ARTIFACT_TYPES.map(async (t) => {
        try {
          details[t] = await api.getArtifact(contextRunId, t);
        } catch {
          /* artifact not produced / not persisted — degrades to 暂无信息 */
        }
      }),
    );
    const caseId = (run as { case_id?: string } | null)?.case_id ?? null;
    const caseDesc =
      caseId && cases ? cases.cases.find((c) => c.id === caseId)?.desc ?? null : null;
    return {
      run,
      events: (events as { events?: RuntimeEvent[] } | null)?.events ?? null,
      artifacts: (artifacts as { artifacts?: RunBundleRaw["artifacts"] } | null)?.artifacts ?? [],
      details,
      reviewCard,
      supervisor:
        (supervisor as { supervisor?: SupervisorState } | null)?.supervisor ?? null,
      caseDesc,
    };
  }, [contextRunId, projectId]);

  const vm = useMemo(
    () =>
      approval && bundleQ.state.kind === "ready" && bundleQ.state.data
        ? buildReviewWorkspaceVM({
            approval,
            supervisor: bundleQ.state.data.supervisor,
            caseDesc: bundleQ.state.data.caseDesc,
            run: bundleQ.state.data.run,
            events: bundleQ.state.data.events,
            artifacts: bundleQ.state.data.artifacts,
            details: bundleQ.state.data.details,
            reviewCard: bundleQ.state.data.reviewCard,
          })
        : null,
    [approval, bundleQ.state],
  );

  const decisionRef = useRef<HTMLDivElement | null>(null);
  const startReview = () =>
    decisionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-4xl flex-col gap-4 overflow-y-auto p-4">
      <div className="sticky top-0 z-10 -mx-4 flex shrink-0 items-center gap-3 border-b border-slate-200 bg-slate-50/95 px-4 pb-2 pt-1 backdrop-blur">
        <button
          data-testid="workspace-back"
          onClick={onBack}
          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11.5px] font-medium text-slate-600 hover:bg-slate-100"
        >
          ← 返回队列
        </button>
        <h2 className="text-[15px] font-semibold tracking-tight">人工审核工作台</h2>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          只读 · 证据追溯
        </span>
      </div>

      {approvalQ.state.kind === "loading" ? (
        <p className="p-8 text-center text-[13px] text-slate-400">正在加载审核任务...</p>
      ) : null}
      {approvalQ.state.kind === "error" ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-center">
          <p className="text-[13px] font-medium text-red-700">加载失败:{approvalQ.state.message}</p>
          <button
            onClick={approvalQ.retry}
            className="mt-2 rounded border border-red-300 bg-white px-3 py-1 text-[12px] font-medium text-red-600 hover:bg-red-100"
          >
            Retry
          </button>
        </div>
      ) : null}

      {approval && vm ? (
        <>
          <CaseHeader approval={approval} vm={vm} onStartReview={startReview} />
          <ExecutiveSummary vm={vm} />
          <Section n="3" title="风险与保障缺口" hint="每行可展开判断依据与证据">
            <RiskGapSection vm={vm} />
          </Section>
          <Section n="4" title="解决方案" hint="Agent 的设计思路与取舍">
            <SolutionSection vm={vm} />
          </Section>
          <Section n="5" title="产品推荐" hint="为什么推荐 · 匹配了什么">
            <ProductSection vm={vm} />
          </Section>
          <Section n="6" title="需要你确认的事项" hint="系统已把需要人工判断的点整理在此">
            <HumanReviewSection hr={vm.humanReview} />
          </Section>
          <div ref={decisionRef} className="scroll-mt-16">
            <DecisionPanel approval={approval} onDecided={approvalQ.retry} />
          </div>
          <FeedbackPanel approval={approval} />
          <Section n="7" title="已生成方案" hint="本次运行的交付物">
            <DeliverablesSection vm={vm} />
          </Section>
          <Section n="8" title="Agent 工作过程" hint="执行步骤一览">
            <ExecutionSection steps={vm.execution} events={bundleQ.state.kind === "ready" ? bundleQ.state.data?.events ?? null : null} />
          </Section>
          <TechnicalDetails
            approval={approval}
            supervisor={bundleQ.state.kind === "ready" ? bundleQ.state.data?.supervisor ?? null : null}
            runRaw={bundleQ.state.kind === "ready" ? bundleQ.state.data?.run ?? null : null}
            vm={vm}
            artifacts={bundleQ.state.kind === "ready" ? bundleQ.state.data?.artifacts ?? [] : []}
            runId={contextRunId}
            contextArtifactIds={contextArtifactIds}
            reviewCard={bundleQ.state.kind === "ready" ? bundleQ.state.data?.reviewCard ?? null : null}
          />
        </>
      ) : null}

      {approval && !contextRunId ? (
        <>
          <p data-testid="run-unavailable" className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 text-[12.5px] text-amber-800">
            该审批未携带运行上下文——案例分析区域不可用,可基于审批记录直接作出决定(见下方技术详情与决定面板)。
          </p>
          <div ref={decisionRef} className="scroll-mt-16">
            <DecisionPanel approval={approval} onDecided={approvalQ.retry} />
          </div>
          <FeedbackPanel approval={approval} />
          <TechnicalDetails
            approval={approval}
            supervisor={bundleQ.state.kind === "ready" ? bundleQ.state.data?.supervisor ?? null : null}
            runRaw={null}
            vm={buildReviewWorkspaceVM({
              approval,
              supervisor: null,
              caseDesc: null,
              run: null,
              events: null,
              artifacts: [],
              details: {},
              reviewCard: null,
            })}
            artifacts={[]}
            runId={null}
            contextArtifactIds={contextArtifactIds}
            reviewCard={null}
          />
        </>
      ) : null}

      {approval && contextRunId && bundleQ.state.kind === "error" ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-center">
          <p className="text-[13px] font-medium text-red-700">案例分析加载失败:{bundleQ.state.message}</p>
          <button
            onClick={bundleQ.retry}
            className="mt-2 rounded border border-red-300 bg-white px-3 py-1 text-[12px] font-medium text-red-600 hover:bg-red-100"
          >
            Retry
          </button>
        </div>
      ) : null}

      {approval && contextRunId && bundleQ.state.kind === "loading" ? (
        <p className="p-6 text-center text-[12.5px] text-slate-400">正在加载案例分析...</p>
      ) : null}
    </div>
  );
}
