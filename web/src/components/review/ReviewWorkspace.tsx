/**
 * Review Workspace (Phase 27.5-3) — READ-ONLY aggregation view.
 *
 * Answers, from existing backend APIs only (no business logic,
 * no state mutation, no fabricated data):
 *   A. Why am I reviewing this?   — /api/approvals/{id}
 *   B. What case is this about?   — approval context + supervisor
 *      (there is NO project/case GET endpoint — gap recorded;
 *      missing fields render "—")
 *   C. What did the Agent do?     — /api/runs/{id}/events timeline
 *   D. What was produced?         — /api/runs/{id}/artifacts
 *      (+ harness artifact ids from the approval context)
 *   E. Why does the Agent believe this? — evidence chain joined
 *      from the run's product-recommendation provenance refs and
 *      the knowledge-evidence artifact. Missing → "No evidence
 *      linked".
 *
 * Phase 27.7.6-C: sections C-E auto-link from the approval's
 * review_context.run_id (read-only backend projection of the
 * approval context) — the reviewer never enters a run id. When
 * the context has no run, C-E show "Run information unavailable".
 * Statuses render verbatim from the backend; durations are
 * presentation arithmetic over event timestamps.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import type {
  ApprovalRecord,
  SupervisorState,
} from "../../types/approval";
import type {
  ArtifactSummary,
  EventsResponse,
  RuntimeEvent,
} from "../../types/runtime";
import { ApprovalStatusBadge } from "./ApprovalStatusBadge";
import { DecisionPanel } from "./DecisionPanel";
import { FeedbackPanel } from "./FeedbackPanel";
import { ReviewCardDetail } from "./ReviewCardView";

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

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[13.5px] font-semibold tracking-tight text-slate-700">
          {title}
        </h3>
        {hint ? <span className="text-[11px] text-slate-400">{hint}</span> : null}
      </div>
      <div className="mt-2.5">{children}</div>
    </section>
  );
}

function AsyncBlock<T>({
  state,
  retry,
  empty,
  render,
}: {
  state: Async<T>;
  retry: () => void;
  empty: (data: T) => boolean;
  render: (data: T) => React.ReactNode;
}) {
  if (state.kind === "loading")
    return <p className="py-3 text-center text-[12.5px] text-slate-400">Loading...</p>;
  if (state.kind === "error")
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-3 text-center">
        <p className="text-[12.5px] font-medium text-red-700">
          加载失败:{state.message}
        </p>
        <button
          onClick={retry}
          className="mt-1.5 rounded border border-red-300 bg-white px-2.5 py-0.5 text-[11.5px] font-medium text-red-600 hover:bg-red-100"
        >
          Retry
        </button>
      </div>
    );
  if (empty(state.data))
    return <p className="py-3 text-center text-[12.5px] text-slate-400">No data available</p>;
  return <>{render(state.data)}</>;
}

function waitingSince(createdAt: string): string {
  const t = Date.parse(createdAt);
  if (Number.isNaN(t)) return "—";
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)} h ${mins % 60} min`;
}

const DASH = "—";
const fmtTime = (iso: string | null | undefined) =>
  iso ? iso.slice(11, 19) : DASH;

// ---- Section C: timeline projection over run events ------------------ #
interface TimelineRow {
  key: string;
  actor: string;
  runId: string;
  status: string;
  start: string;
  end: string | null;
  durationMs: number | null;
}

function buildTimeline(events: RuntimeEvent[]): TimelineRow[] {
  const rows = new Map<string, TimelineRow>();
  for (const e of events) {
    if (e.event_type === "run_started" || e.event_type === "run_completed"
      || e.event_type === "run_failed") {
      const k = `run:${e.event_type}`;
      rows.set(k, {
        key: k, actor: `run ${e.event_type}`, runId: e.run_id,
        status: e.event_type, start: e.timestamp, end: e.timestamp,
        durationMs: 0,
      });
      continue;
    }
    if (e.event_type !== "stage_started" && e.event_type !== "stage_completed"
      && e.event_type !== "stage_failed") {
      continue;
    }
    const stage = e.stage ?? "unknown-stage";
    const prev = rows.get(stage);
    if (e.event_type === "stage_started") {
      rows.set(stage, {
        key: stage,
        actor: e.skill ?? stage,
        runId: e.run_id,
        status: "stage_started",
        start: e.timestamp,
        end: null,
        durationMs: null,
      });
    } else if (prev) {
      rows.set(stage, {
        ...prev,
        status: e.event_type,
        end: e.timestamp,
        durationMs: Date.parse(e.timestamp) - Date.parse(prev.start),
      });
    }
  }
  return [...rows.values()].sort((a, b) =>
    Date.parse(a.start) - Date.parse(b.start),
  );
}

// ---- Section E: evidence chain from real artifact payloads ------------ #
interface EvidenceRef {
  type: string;
  ref: string;
}
interface ChainBlock {
  key: string;
  title: string;
  refs: EvidenceRef[];
  missing: boolean;
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
  const approvalQ = useAsync(
    () => api.getApproval(approvalId),
    [approvalId],
  );
  const supervisorQ = useAsync(
    () => api.supervisor(projectId),
    [projectId],
  );

  // Phase 27.7.6-C: auto-link run from the approval context —
  // the reviewer never sees or types a run_id. When the approval
  // loads, extract run_id from its context (or review_context)
  // and activate sections C/D/E automatically.
  const approval: ApprovalRecord | null =
    approvalQ.state.kind === "ready" ? approvalQ.state.data.approval : null;
  const reviewContext =
    approvalQ.state.kind === "ready"
      ? approvalQ.state.data.review_context
      : undefined;
  const contextRunId: string | null =
    reviewContext?.run_id ??
    ((approval?.context as Record<string, unknown> | null)?.run_id as
      | string
      | undefined) ??
    null;

  const [runLoaded, setRunLoaded] = useState<string | null>(null);
  useEffect(() => {
    // Auto-activate when the approval carries a linked run
    if (contextRunId) setRunLoaded(contextRunId);
  }, [contextRunId]);

  const eventsQ = useAsync(
    () =>
      runLoaded
        ? api.getEvents(runLoaded)
        : Promise.resolve<EventsResponse>({
            run_id: "", count: 0, events: [],
          }),
    [runLoaded],
  );

  const supervisor: SupervisorState | null =
    supervisorQ.state.kind === "ready" ? supervisorQ.state.data.supervisor : null;

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-4xl flex-col gap-3 overflow-y-auto p-4">
      <div className="sticky top-0 z-10 -mx-4 flex shrink-0 items-center gap-3 border-b border-slate-200 bg-slate-50/95 px-4 pb-2 pt-1 backdrop-blur">
        <button
          data-testid="workspace-back"
          onClick={onBack}
          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11.5px] font-medium text-slate-600 hover:bg-slate-100"
        >
          ← 返回队列
        </button>
        <h2 className="text-[15px] font-semibold tracking-tight">Review Workspace</h2>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          只读 · 证据追溯
        </span>
      </div>

      {/* A — Approval Summary */}
      <Section title="A · 审批摘要" hint="为什么需要我审核?">
        <AsyncBlock
          state={approvalQ.state}
          retry={approvalQ.retry}
          empty={() => false}
          render={() => {
            const a = approval;
            if (!a) return null;
            const ctx = (a.context ?? {}) as Record<string, unknown>;
            const ctxStr = (k: string) =>
              typeof ctx[k] === "string" ? (ctx[k] as string) : DASH;
            const ctxArr = (k: string) =>
              Array.isArray(ctx[k]) ? (ctx[k] as string[]).join(", ") : DASH;
            return (
              <div data-testid="workspace-approval">
                <div className="flex items-center gap-2">
                  <ApprovalStatusBadge status={a.status} />
                  <span className="font-mono text-[11.5px] text-slate-400">
                    {a.approval_id}
                  </span>
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-[12.5px] sm:grid-cols-3">
                  {([
                    ["Approval ID", a.approval_id],
                    ["类型", a.request_type],
                    ["项目", a.project_id],
                    ["Task", a.task_id || DASH],
                    ["Stage", ctxStr("stage")],
                    ["创建时间", a.created_at?.replace("T", " ") ?? DASH],
                    ["等待时长", waitingSince(a.created_at)],
                    ["决定", a.decision ?? DASH],
                    ["决定人", a.resolved_by ?? DASH],
                  ] as [string, string][]).map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <dt className="w-16 shrink-0 text-slate-400">{k}</dt>
                      <dd className="min-w-0 break-all text-slate-700">{v}</dd>
                    </div>
                  ))}
                </dl>
                {a.reason ? (
                  <p className="mt-2 rounded-md bg-slate-50 p-2 text-[12.5px] text-slate-600">
                    {a.reason}
                  </p>
                ) : null}
                {ctxArr("task_types") !== DASH ? (
                  <p className="mt-1 text-[11.5px] text-slate-400">
                    涉及任务类型:{ctxArr("task_types")}
                  </p>
                ) : null}
              </div>
            );
          }}
        />
      </Section>

      {/* B — Case Context (limited by existing APIs) */}
      <Section title="B · 案例上下文" hint="关于哪个客户/案例?">
        <AsyncBlock
          state={supervisorQ.state}
          retry={supervisorQ.retry}
          empty={() => false}
          render={() => {
            const s = supervisor;
            if (!s) return null;
            return (
              <div data-testid="workspace-case" className="grid grid-cols-2 gap-x-6 gap-y-1 text-[12.5px] sm:grid-cols-3">
                {([
                  ["客户", DASH],
                  ["Case ID", DASH],
                  ["案例摘要", DASH],
                  ["风险画像", DASH],
                  ["需求", DASH],
                  ["已知约束", DASH],
                  ["项目状态(后端)", s.status],
                  ["项目风险级别(后端)", s.risk_level],
                  ["项目更新时间", s.updated_at?.replace("T", " ") ?? DASH],
                ] as [string, string][]).map(([k, v]) => (
                  <div key={k} className="flex gap-2">
                    <dt className="w-24 shrink-0 text-slate-400">{k}</dt>
                    <dd className="min-w-0 break-all text-slate-700">{v}</dd>
                  </div>
                ))}
                <p className="col-span-full mt-1 text-[11px] text-slate-400">
                  注:后端暂无 project/case 详情端点(已记录 API GAP),
                  客户字段暂不可得,显示 "—"。
                </p>
              </div>
            );
          }}
        />
      </Section>

      {/* A2 — Review Card (Phase 27.7.6 v2: risk-based review entry) */}
      <Section
        title="A2 · Review Card"
        hint="风险卡 —— 该案例需要什么级别的审核?"
      >
        {!contextRunId ? (
          <p className="py-3 text-center text-[12.5px] text-slate-400">
            无 Review Card(该审批未携带运行上下文)
          </p>
        ) : (
          <CardBlock runId={contextRunId} />
        )}
      </Section>

      {/* Run info display (auto-linked; no manual input) */}
      {contextRunId ? (
        <p data-testid="run-linked" className="text-[11.5px] text-slate-400">
          已自动关联运行:<span className="font-mono">{contextRunId}</span>
          (来自审批上下文,审核者无需输入)
        </p>
      ) : (
        <p data-testid="run-unavailable" className="text-[11.5px] text-slate-400">
          Run information unavailable(该审批未携带运行上下文)
        </p>
      )}

      {/* C — Agent Execution Timeline */}
      <Section title="C · Agent 执行时间线" hint="Agent 做了什么?">
        {!contextRunId ? (
          <p data-testid="timeline-no-run" className="py-3 text-center text-[12.5px] text-slate-400">
            Run information unavailable
          </p>
        ) : (
          <AsyncBlock
            state={eventsQ.state}
            retry={eventsQ.retry}
            empty={(d: EventsResponse) => d.events.length === 0}
            render={(d: EventsResponse) => (
              <ul data-testid="workspace-timeline" className="flex flex-col">
                {buildTimeline(d.events).map((row) => (
                  <li key={row.key} className="flex gap-3 border-l border-slate-200 py-1.5 pl-3 text-[12.5px]">
                    <span className="w-16 shrink-0 font-mono text-slate-400">
                      {fmtTime(row.start)}
                    </span>
                    <span className="min-w-0 flex-1 text-slate-700">{row.actor}</span>
                    <span className="font-mono text-[11px] text-slate-400">{row.runId}</span>
                    <span className="w-36 shrink-0 text-right text-slate-500">{row.status}</span>
                    <span className="w-14 shrink-0 text-right text-slate-400">
                      {row.durationMs != null ? `${Math.round(row.durationMs / 100) / 10}s` : "…"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          />
        )}
      </Section>

      {/* D — Generated Artifacts */}
      <Section title="D · 生成的产物" hint="产出了什么?">
        {(() => {
          const ctxArtifacts = (approval?.context as Record<string, unknown> | null)
            ?.artifact_ids;
          const artifactIds =
            reviewContext?.artifact_ids ??
            (Array.isArray(ctxArtifacts) ? (ctxArtifacts as string[]) : undefined);
          return artifactIds && artifactIds.length > 0 ? (
            <p data-testid="review-context-artifacts" className="mb-2 text-[11.5px] text-slate-500">
              审批关联的交付物:{artifactIds.join(", ")}
            </p>
          ) : null;
        })()}
        {!contextRunId ? (
          <p data-testid="artifacts-no-run" className="py-3 text-center text-[12.5px] text-slate-400">
            Run information unavailable
          </p>
        ) : (
          <ArtifactsSection runId={runLoaded ?? contextRunId} />
        )}
      </Section>

      {/* E — Evidence Chain */}
      <Section title="E · 证据链" hint="Agent 为什么这样认为?(推荐→需求→证据→来源)">
        {!contextRunId ? (
          <p data-testid="evidence-no-run" className="py-3 text-center text-[12.5px] text-slate-400">
            Run information unavailable
          </p>
        ) : (
          <EvidenceSection runId={runLoaded ?? contextRunId} />
        )}
      </Section>

      {/* F — Human Decision (Phase 27.5-4; backend-authoritative) */}
      {approval ? (
        <DecisionPanel approval={approval} onDecided={approvalQ.retry} />
      ) : null}

      {/* G — Human Feedback (Phase 27.7; inert evidence, local MVP) */}
      {approval ? <FeedbackPanel approval={approval} /> : null}
    </div>
  );
}

/** Phase 27.7.6 v2: the run's Review Card, fetched read-only and
 *  rendered verbatim (level/validation/flags come from the backend
 *  generator — this view never re-derives them). */
function CardBlock({ runId }: { runId: string }) {
  const q = useAsync(() => api.reviewCard(runId), [runId]);
  return (
    <AsyncBlock
      state={q.state}
      retry={q.retry}
      empty={() => false}
      render={(card) => <ReviewCardDetail card={card} />}
    />
  );
}

async function writeClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  // Fallback for non-secure contexts / jsdom.
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

function ArtifactsSection({ runId }: { runId: string }) {
  const q = useAsync(() => api.getArtifacts(runId), [runId]);
  const [openType, setOpenType] = useState<string | null>(null);
  const detail = useAsync(
    () => api.getArtifact(runId, openType ?? ""),
    [openType],
  );
  // Copy-to-clipboard feedback for one artifact at a time.
  const [copyState, setCopyState] = useState<{
    type: string; ok: boolean;
  } | null>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (copyTimer.current) clearTimeout(copyTimer.current);
    },
    [],
  );
  const copyArtifact = async (a: ArtifactSummary) => {
    try {
      const d = await api.getArtifact(runId, a.artifact_type);
      const payload = (d as { artifact?: unknown }).artifact ?? d;
      await writeClipboard(JSON.stringify(payload, null, 2));
      setCopyState({ type: a.artifact_type, ok: true });
    } catch {
      setCopyState({ type: a.artifact_type, ok: false });
    }
    if (copyTimer.current) clearTimeout(copyTimer.current);
    copyTimer.current = setTimeout(() => setCopyState(null), 2000);
  };
  return (
    <AsyncBlock
      state={q.state}
      retry={q.retry}
      empty={(d) => d.artifacts.length === 0}
      render={(d) => (
        <div data-testid="workspace-artifacts">
          <ul className="flex flex-col gap-1.5">
            {d.artifacts.map((a: ArtifactSummary) => (
              <li
                key={a.artifact_id}
                className="flex items-stretch gap-1.5"
              >
                <button
                  data-testid={`workspace-artifact-${a.artifact_type}`}
                  onClick={() => setOpenType(openType === a.artifact_type ? null : a.artifact_type)}
                  className="min-w-0 flex-1 rounded-md border border-slate-200 px-3 py-1.5 text-left text-[12.5px] hover:bg-slate-50"
                >
                  <span className="font-medium text-slate-700">{a.artifact_type}</span>
                  <span className="ml-2 font-mono text-[11px] text-slate-400">
                    {a.artifact_id}
                  </span>
                  <span className="float-right text-[11px] text-slate-400">
                    {a.producer_stage ?? DASH}
                  </span>
                </button>
                <button
                  data-testid={`workspace-artifact-copy-${a.artifact_type}`}
                  onClick={() => copyArtifact(a)}
                  title="复制该产物的完整 JSON"
                  className={
                    copyState?.type === a.artifact_type
                      ? copyState.ok
                        ? "shrink-0 rounded-md border border-emerald-300 bg-emerald-50 px-2 text-[11.5px] font-medium text-emerald-700"
                        : "shrink-0 rounded-md border border-red-300 bg-red-50 px-2 text-[11.5px] font-medium text-red-600"
                      : "shrink-0 rounded-md border border-slate-200 bg-white px-2 text-[11.5px] font-medium text-slate-500 hover:bg-slate-50"
                  }
                >
                  {copyState?.type === a.artifact_type
                    ? copyState.ok
                      ? "已复制"
                      : "复制失败"
                    : "复制 JSON"}
                </button>
              </li>
            ))}
          </ul>
          {openType ? (
            <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-2">
              {detail.state.kind === "loading" ? (
                <p className="text-[12px] text-slate-400">Loading...</p>
              ) : detail.state.kind === "error" ? (
                <p className="text-[12px] text-red-600">
                  加载失败:{detail.state.message}
                </p>
              ) : (
                <pre className="max-h-64 overflow-auto text-[11px] text-slate-600">
                  {JSON.stringify(
                    (detail.state.data as { artifact?: unknown }).artifact ??
                      detail.state.data,
                    null,
                    2,
                  )}
                </pre>
              )}
            </div>
          ) : null}
        </div>
      )}
    />
  );
}

function EvidenceSection({ runId }: { runId: string }) {
  const q = useAsync(
    async () => {
      const [rec, kev] = await Promise.all([
        api.getArtifact(runId, "product-recommendation").catch(() => null),
        api.getArtifact(runId, "knowledge-evidence").catch(() => null),
      ]);
      return { rec, kev };
    },
    [runId],
  );
  const evidenceIndex = useMemo(() => {
    if (q.state.kind !== "ready") return new Map<string, { content: string; source: string }>();
    const kevPayload = (q.state.data.kev as
      | { artifact?: { payload?: Record<string, unknown> } }
      | null)?.artifact?.payload;
    const m = new Map<string, { content: string; source: string }>();
    for (const e of ((kevPayload?.evidence ?? []) as {
      evidence_id?: string;
      chunk_id?: string;
      content?: string;
      source?: string;
    }[])) {
      const id = e.evidence_id ?? e.chunk_id ?? "";
      if (id)
        m.set(id, { content: e.content ?? "", source: e.source ?? "" });
    }
    return m;
  }, [q.state]);
  const blocks = useMemo(() => {
    if (q.state.kind !== "ready") return [] as ChainBlock[];
    const recPayload = (q.state.data.rec as
      | { artifact?: { payload?: Record<string, unknown> } }
      | null)?.artifact?.payload;
    if (!recPayload) return [];
    const out: ChainBlock[] = [];
    const prim = recPayload.primary_recommendation as
      | { candidate_id?: string; provenance?: EvidenceRef[] }
      | undefined;
    if (prim && prim.candidate_id) {
      out.push({
        key: `primary-${prim.candidate_id}`,
        title: `主推荐:${prim.candidate_id}`,
        refs: prim.provenance ?? [],
        missing: !(prim.provenance ?? []).some((r) => r.type === "knowledge"),
      });
    }
    for (const c of (recPayload.candidate_evaluations ?? []) as {
      candidate_id?: string;
      recommendation_status?: string;
      provenance?: EvidenceRef[];
    }[]) {
      if (c.recommendation_status === "primary" || !c.candidate_id) continue;
      if (c.recommendation_status !== "insufficient_evidence") continue;
      out.push({
        key: `cand-${c.candidate_id}`,
        title: `候选 ${c.candidate_id}(insufficient_evidence)`,
        refs: c.provenance ?? [],
        missing: true,
      });
    }
    return out;
  }, [q.state]);
  return (
    <AsyncBlock
      state={q.state}
      retry={q.retry}
      empty={() => false}
      render={() => (
        <div data-testid="workspace-evidence">
          {blocks.length === 0 ? (
            <p className="py-3 text-center text-[12.5px] text-slate-400">
              No evidence linked(该 Run 无推荐产物或无 provenance)
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {blocks.map((b) => (
                <div key={b.key} className="rounded-md border border-slate-200 p-3">
                  <p className="text-[13px] font-medium text-slate-700">{b.title}</p>
                  <div className="mt-2 space-y-1.5 border-l-2 border-slate-200 pl-3">
                    {b.refs.length === 0 ? (
                      <p className="text-[12px] text-slate-400">No evidence linked</p>
                    ) : (
                      b.refs.map((r, i) => {
                        const ev =
                          r.type === "knowledge" ? evidenceIndex.get(r.ref) : null;
                        return (
                          <div key={i} className="text-[12px]">
                            <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] font-semibold uppercase text-slate-500">
                              {r.type}
                            </span>
                            <span className="font-mono text-slate-600">{r.ref}</span>
                            {ev ? (
                              <div className="mt-0.5 ml-1 border-l border-slate-200 pl-2 text-slate-500">
                                <p className="line-clamp-2">{ev.content}</p>
                                <p className="text-[11px] text-slate-400">
                                  来源:{ev.source || DASH}
                                </p>
                              </div>
                            ) : r.type === "knowledge" ? (
                              <p className="ml-1 text-[11.5px] text-amber-600">
                                No evidence linked(知识库中无此引用)
                              </p>
                            ) : null}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    />
  );
}
