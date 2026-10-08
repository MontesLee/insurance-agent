import React, { useEffect, useRef, useState } from "react";
import {
  bucketText,
  type RunUiState,
  type StepOutputBucket,
  type StepSegment,
} from "../../state/runReducer";
import {
  consumerActivities,
  latestActivity,
  type ConsumerActivityStatus,
} from "../../state/activity";
import { activityAnchors, stepsAwaitingModel } from "../../state/stepAnchors";
import { consumerTerminalHeader } from "../../state/consumerView";
import { verbOfStage } from "../../state/activity";
import { sanitizeConsumerText } from "../../state/contentHygiene";
import { StageGlyph } from "../StatusBadge";

/**
 * AGENT ACTIVITY — the live work-trajectory card (consumer view).
 *
 * 28.E-3: the list is the Consumer Activity DTO folded from the REAL
 * event sequence (activity.ts consumerActivities) — every line is
 * event-backed; unknown events/stages/tools never render; started never
 * implies completed. The component does NOT interpret runtime events,
 * stage orders, tools, or skills — it renders the DTO. No ids, no raw
 * events, no counters.
 *
 * 28.K.28 (supersedes E-2): the step output box renders BOTH segment
 * kinds — `content` normally, `reasoning` de-emphasized and labelled —
 * because glm-5.3 streams reasoning for its entire first phase. The
 * answer bubble (`state.stream`) is still content-only; the activity
 * DTO never carries stream text at all.
 *
 * 28.K.13 (C): while the run is LIVE and NO new event has arrived for
 * HEARTBEAT_MS, a deterministic waiting line appears. It is UI liveness
 * feedback ONLY — it claims no backend operation, no progress, and no
 * completion; the moment a real event lands (events.length changes) or
 * the run reaches a terminal state, the line disappears.
 *
 * 28.K.29: each step's output box is rendered UNDER the activity row that
 * the step produced (stepAnchors.ts computes the ownership), not in a
 * trailing stack at the bottom of the card. Buckets with no owner (no
 * activity in the sequence at all) still render in the trailing container.
 */
const HEARTBEAT_MS = 12_000;
const HEARTBEAT_COPY = "这一步需要一些时间，请稍候";
/**
 * 28.K.17 (K.16 Option A): a delta arrival within DELTA_FRESH_MS means
 * the LLM is REALLY streaming tokens right now — the live "正在生成回答"
 * row is driven by arrivals, never by a fake timer. The ticker below only
 * re-evaluates freshness when a delta has arrived (it never fabricates
 * progress); terminal states never render any of this.
 */
const DELTA_FRESH_MS = 2_000;
const GENERATION_COPY = "正在生成回答";

function useActivitySilence(eventsCount: number): boolean {
  const [silent, setSilent] = useState(false);
  useEffect(() => {
    setSilent(false);
    const t = setTimeout(() => setSilent(true), HEARTBEAT_MS);
    return () => clearTimeout(t);
  }, [eventsCount]);
  return silent;
}

function useDeltaFresh(lastDeltaAt: number | null): boolean {
  const [, force] = useState(0);
  useEffect(() => {
    if (lastDeltaAt === null) return;
    // re-render exactly once when the arrival goes stale (freshness
    // evaluation only — no progress simulation)
    const t = setTimeout(() => force((n) => n + 1), DELTA_FRESH_MS);
    return () => clearTimeout(t);
  }, [lastDeltaAt]);
  return lastDeltaAt !== null && Date.now() - lastDeltaAt < DELTA_FRESH_MS;
}

export function AgentActivity({
  state,
  streaming,
}: {
  state: RunUiState;
  streaming: boolean;
}) {
  const live = state.status === "running" || state.status === "queued" || state.status === "unknown";
  const head = consumerTerminalHeader(state.status, streaming);
  const items = consumerActivities(state.events);
  const evalSummary = evalSummaryOf(state);
  const artifacts = state.events.filter((e) => e.event_type === "artifact_created").length;
  const running = items.find((a) => a.status === "running");
  const deltaFresh = useDeltaFresh(state.lastDeltaAt);
  // 28.K.17 Case A (fresh delta → generation row wins over heartbeat) /
  // Case C (true silence → K.13 heartbeat) / Case D (terminal → neither).
  const showGeneration = live && deltaFresh;
  const silent = useActivitySilence(state.events.length);
  const showHeartbeat = live && silent && !deltaFresh;
  // 28.K.27 / 28.K.28: keep the ACTIVE step's box mounted while the run is
  // live and the model has started emitting. `lastDeltaAt` is stamped by ANY
  // delta kind, so it flips on the first REASONING delta — and since 28.K.28
  // that same delta also puts text INTO the bucket, so the box is normally
  // non-empty from the first token on. An empty bucket is still shown only for
  // the CURRENT step, so a step that never streams renders nothing at all (no
  // templated/empty boxes).
  //
  // 28.K.30: an EMPTY box additionally requires that the model is still
  // generating. The box's empty state renders "正在思考…", and that claim is
  // only true while a generation is in flight — once the model has returned,
  // the remaining silence belongs to tool/stage execution where no model is
  // running at all. `stepsAwaitingModel` reads that boundary off the real
  // event stream (no timer, no heuristics).
  //
  // The QA-slice bucket (`qa-composing`) needs no exception: runReducer opens
  // it INSIDE the delta handler, after the empty-text early return, so it is
  // never empty and never reaches this branch.
  const awaiting = stepsAwaitingModel(state.events);
  const stepBoxes = state.stepOutputs.filter(
    (b) =>
      bucketText(b).trim().length > 0 ||
      (live &&
        awaiting.has(b.key) &&
        state.lastDeltaAt !== null &&
        b.key === state.currentStepKey),
  );
  // 28.K.29: resolve each visible box to the activity row it belongs to, so
  // the text sits with its milestone instead of trailing at the card bottom.
  const anchors = activityAnchors(state.events, stepBoxes.map((b) => b.key));
  const boxesByActivity = new Map<string, StepOutputBucket[]>();
  const orphanBoxes: StepOutputBucket[] = [];
  for (const b of stepBoxes) {
    const owner = anchors.get(b.key) ?? null;
    if (owner === null) {
      orphanBoxes.push(b);
      continue;
    }
    const list = boxesByActivity.get(owner);
    if (list) list.push(b);
    else boxesByActivity.set(owner, [b]);
  }
  // 28.K.25: ○ upcoming business stages — rendered ONLY once execution has
  // actually started on the planning spine (≥1 stage_started in the real
  // event list) and only for stages the WORKFLOW definition declares (the
  // run's stage_order, loaded deterministically at run start). Stages that
  // have not started are shown hollow; nothing is templated before the
  // first real stage event, and QA turns (no stage events) show none.
  const startedStages = new Set(
    state.events.filter((e) => e.event_type === "stage_started" && e.stage)
      .map((e) => e.stage as string),
  );
  const pendingStages = startedStages.size === 0 ? [] :
    state.stageOrder
      .filter((s) => !startedStages.has(s.id))
      .map((s) => `正在${verbOfStage(s.id)}`);

  return (
    <div
      className="my-3 max-w-2xl rounded-xl border border-slate-200 bg-slate-50/80 shadow-sm"
      data-testid="agent-activity"
      data-activity-status={state.status}
    >
      <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-2.5">
        <span className={live ? "animate-pulse text-blue-500" : "text-slate-400"}>✦</span>
        <span className="text-[13px] font-semibold text-slate-700" data-testid="activity-header">{head}</span>
        {live && running ? (
          <span className="flex items-center gap-1 text-[12px] font-medium text-blue-600">
            <span className="mx-0.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
            {running.label}
            <AnimatedDots />
          </span>
        ) : null}
      </div>

      {items.length > 0 ? (
        <ul className="space-y-1 px-4 py-3" data-testid="activity-stages">
          {showGeneration ? (
            <li
              className="flex items-center gap-2 px-2 py-0.5 text-[13px] animate-pulse"
              data-testid="activity-generation"
            >
              <span className="mx-0.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
              <span className="font-semibold text-blue-700">{GENERATION_COPY}</span>
            </li>
          ) : null}
          {showHeartbeat ? (
            <li
              className="flex items-center gap-2 px-2 py-0.5 text-[12.5px] text-slate-400"
              data-testid="activity-heartbeat"
            >
              <span className="mx-0.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400" />
              {HEARTBEAT_COPY}
            </li>
          ) : null}
          {items.map((a) => {
            const isActive = live && a.status === "running";
            const boxes = boxesByActivity.get(a.key) ?? [];
            return (
              <li key={a.key}>
                <div
                  className={
                    isActive
                      ? "flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50/70 px-2 py-1 text-[13px] animate-pulse"
                      : "flex items-center gap-2 px-2 py-0.5 text-[13px]"
                  }
                  data-activity-item="1"
                  data-status={a.status}
                >
                  <StageGlyph status={glyphOf(a.status)} />
                  <span
                    className={
                      isActive
                        ? "font-semibold text-blue-700"
                        : a.status === "running"
                          ? "text-slate-500"
                          : a.status === "failed"
                            ? "text-slate-500"
                            : "text-slate-700"
                    }
                  >
                    {a.label}
                  </span>
                  {isActive ? (
                    <span className="ml-auto flex items-center gap-1 text-[11px] font-medium text-blue-600">
                      <span className="inline-block h-1.5 w-1.5 animate-ping rounded-full bg-blue-500" />
                      进行中
                    </span>
                  ) : null}
                </div>
                {/* 28.K.29: this step's streaming output, nested under its own
                    milestone (indented + left rule) so the text reads as part
                    of that row rather than a detached block at the bottom. */}
                {boxes.length > 0 ? (
                  <div
                    className="ml-5 mt-1 space-y-1.5 border-l-2 border-slate-200 pl-2.5"
                    data-testid="activity-step-outputs"
                  >
                    {boxes.map((b) => (
                      <StepOutputBox
                        key={b.key}
                        segments={b.segments}
                        active={live && b.key === state.currentStepKey}
                      />
                    ))}
                  </div>
                ) : null}
              </li>
            );
          })}
          {pendingStages.map((label) => (
            <li
              key={"pending-" + label}
              className="flex items-center gap-2 px-2 py-0.5 text-[13px] text-slate-300"
              data-activity-item="1"
              data-status="pending"
            >
              <span className="mx-0.5 text-slate-300">○</span>
              <span>{label}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {/* Step-scoped streaming outputs (Codex-style execution transparency).
          Each agent-step LLM call gets its own fixed-height output box; the
          ACTIVE step shows a cursor, completed steps retain their final
          content. Render-time sanitizer is the last hygiene layer, applied to
          EVERY segment.

          28.K.29: boxes that CAN be attributed to an activity row are already
          rendered under that row (see the list above). This container is the
          FALLBACK for buckets with no owner at all — e.g. a run whose event
          sequence carries no mapped activity. A box is never dropped just
          because it could not be nested. */}
      {orphanBoxes.length > 0 ? (
        <div className="space-y-2 px-4 pb-3" data-testid="step-outputs">
          {orphanBoxes.map((b) => (
            <StepOutputBox
              key={b.key}
              segments={b.segments}
              active={live && b.key === state.currentStepKey}
            />
          ))}
        </div>
      ) : null}

      {/* 28.K.20: the live content stream moved to the chat-message position
          (Conversation stream-message bubble) — one display, no duplication.
          28.K.28: reasoning is displayable in the STEP BOX but still never
          enters that bubble, so the final answer cannot carry CoT. */}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-200 px-4 py-2 text-[11.5px] text-slate-500">
        {evalSummary ? <span data-testid="activity-eval">{evalSummary}</span> : null}
        {artifacts > 0 ? <span>{artifacts} 份产物已生成</span> : null}
        <span className="ml-auto text-[10.5px] text-slate-400" data-testid="activity-latest">
          {latestActivity(state.events) ?? ""}
        </span>
      </div>
    </div>
  );
}

function glyphOf(status: ConsumerActivityStatus): "passed" | "running" | "failed" | "needs_review" {
  switch (status) {
    case "completed":
      return "passed";
    case "running":
      return "running";
    case "failed":
      return "failed";
    case "waiting":
      return "needs_review";
  }
}

function AnimatedDots() {
  return (
    <span className="inline-flex w-4 justify-start">
      <span className="animate-[dotblink_1.2s_infinite_100ms]">·</span>
      <span className="animate-[dotblink_1.2s_infinite_300ms]">·</span>
      <span className="animate-[dotblink_1.2s_infinite_500ms]">·</span>
    </span>
  );
}

/**
 * One step's streaming output box — FIXED HEIGHT (content never grows
 * the page unbounded), auto-scrolls to bottom while streaming, and
 * shows a cursor on the ACTIVE step only. Sanitized at render (the
 * last hygiene layer after source+delivery sanitization upstream) —
 * applied to EVERY segment, reasoning included.
 *
 * 28.K.28: renders segments in arrival order. `content` is the step's
 * real output; `reasoning` is the model's working notes, shown muted +
 * italic behind a 「思考」 chip so the two never blur together.
 */
const StepOutputBox = React.memo(function StepOutputBox({
  segments,
  active,
}: {
  segments: StepSegment[];
  active: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const userScrolled = useRef(false);
  const len = segments.reduce((n, s) => n + s.text.length, 0);

  // 28.K.30: keep the box pinned to the NEWEST text.
  //
  // The previous guard asked "am I within 24px of the bottom?" AFTER the
  // content had already grown, so a single delta taller than 24px (≈2 lines
  // at this font size) — or the first delta after the box filled up —
  // evaluated to false and the box stopped following for the REST of the
  // step. Text kept arriving while the visible screenful stayed frozen,
  // which reads as "it wrote one sentence and stopped".
  //
  // Following is now paused by exactly ONE thing: the user actively
  // scrolling away from the bottom (see onScroll). Scrolling back down
  // resumes it.
  useEffect(() => {
    const el = ref.current;
    if (!el || !active || userScrolled.current) return;
    el.scrollTop = el.scrollHeight;
  }, [len, active]);

  return (
    <div
      ref={ref}
      onScroll={() => {
        const el = ref.current;
        if (!el) return;
        // paused ONLY while the user is genuinely away from the bottom;
        // coming back to the bottom re-arms the auto-follow
        userScrolled.current =
          el.scrollHeight - el.scrollTop - el.clientHeight >= 24;
      }}
      className="max-h-40 min-h-[3.25rem] overflow-y-auto whitespace-pre-wrap
                 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2
                 text-[12px] leading-relaxed text-slate-600"
      data-testid="step-output-box"
      data-active={active ? "1" : "0"}
    >
      {segments.map((seg, i) =>
        seg.kind === "reasoning" ? (
          <span key={i} data-segment-kind="reasoning">
            <span
              className="mr-1 inline-block select-none rounded bg-slate-200/70 px-1
                         align-baseline text-[10px] leading-4 text-slate-500"
              data-testid="step-output-reasoning-chip"
            >
              思考
            </span>
            <span className="italic text-slate-400" data-testid="step-output-reasoning">
              {sanitizeConsumerText(seg.text)}
            </span>
          </span>
        ) : (
          <span key={i} data-segment-kind="content" data-testid="step-output-content">
            {sanitizeConsumerText(seg.text)}
          </span>
        ),
      )}
      {len === 0 && active ? (
        // Defensive: the box only mounts once deltas started, and 28.K.28
        // stores reasoning text too — so this shows only if a delta carried
        // no text at all. Progress WITHOUT any model text.
        //
        // 28.K.30 — this line is a claim that the agent is THINKING, so the
        // caller only mounts an EMPTY box while the model is still generating
        // (see the `awaitingModel` gate on stepBoxes). Once the model has
        // returned, an empty box is not mounted at all, and the silence of
        // the following tool/stage execution is shown by the milestone row
        // instead of being mislabelled as thought.
        <span
          className="flex items-center gap-1.5 text-slate-400"
          data-testid="step-output-thinking"
        >
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />
          正在思考…
        </span>
      ) : null}
      {active ? (
        <span className="ml-0.5 inline-block h-3.5 w-[2px] animate-pulse bg-blue-500 align-middle" />
      ) : null}
    </div>
  );
});

function evalSummaryOf(state: RunUiState): string | null {
  const closed = state.evals.filter((e) => e.status !== "running");
  if (closed.length === 0) return null;
  const pass = closed.filter((e) => e.status === "pass").length;
  const fail = closed.length - pass;
  if (fail === 0) return `质量校验 ${pass}/${closed.length} 通过`;
  return `质量校验 ${pass}/${closed.length} 通过 · ${fail} 次未过已处理`;
}
