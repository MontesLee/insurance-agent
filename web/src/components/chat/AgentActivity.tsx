import { useEffect, useRef } from "react";
import type { RunUiState } from "../../state/runReducer";
import { latestActivity, stageZh, zhTool } from "../../state/activity";
import { StageGlyph } from "../StatusBadge";

/**
 * AGENT ACTIVITY — the live work-trajectory card. Every line is derived from
 * RunUiState (the reducer's projection of RuntimeEvents): stages, eval verdicts,
 * the latest activity label. No chain-of-thought, no invented progress.
 * While the agent streams, the ACTIVE step shimmers and the model's live
 * output (thinking / text) streams underneath, DeepSeek-style.
 */
export function AgentActivity({
  state,
  caseId,
  streaming,
  activeLabel,
}: {
  state: RunUiState;
  caseId: string;
  streaming: boolean;
  activeLabel?: string | null;
}) {
  const live = state.status === "running" || state.status === "queued" || state.status === "unknown";
  const head = headerOf(state.status, streaming);
  const evalSummary = evalSummaryOf(state);
  const artifacts = Object.values(state.stages).filter((s) => s.artifactId).length;
  const activeStage = state.currentStage;
  const runningTool = state.currentTool ? zhTool(state.currentTool) : null;
  const activeText = runningTool ?? (activeStage ? stageZh(activeStage) : null) ?? activeLabel ?? null;

  return (
    <div
      className="my-3 max-w-2xl rounded-xl border border-slate-200 bg-slate-50/80 shadow-sm"
      data-testid="agent-activity"
      data-activity-status={state.status}
    >
      <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-2.5">
        <span className={live ? "animate-pulse text-blue-500" : "text-slate-400"}>✦</span>
        <span className="text-[13px] font-semibold text-slate-700" data-testid="activity-header">{head}</span>
        {live && activeText ? (
          <span className="flex items-center gap-1 text-[12px] font-medium text-blue-600">
            <span className="mx-0.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
            {activeText}
            <AnimatedDots />
          </span>
        ) : null}
        {live ? (
          <span className="ml-auto font-mono text-[10px] text-slate-400">
            {state.events.length} events
          </span>
        ) : null}
      </div>

      <ul className="space-y-1 px-4 py-3" data-testid="activity-stages">
        {state.stageOrder.map((info) => {
          const st = state.stages[info.id];
          const isActive = live && st?.status === "running";
          return (
            <li
              key={info.id}
              className={
                isActive
                  ? "flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50/70 px-2 py-1 text-[13px] animate-pulse"
                  : "flex items-center gap-2 px-2 py-0.5 text-[13px]"
              }
              data-activity-stage={info.id}
              data-active={isActive || undefined}
            >
              <StageGlyph status={st?.status ?? "pending"} />
              <span className={isActive ? "font-semibold text-blue-700" : st?.status === "pending" ? "text-slate-400" : "text-slate-700"}>
                {stageZh(info.id) || info.skill || info.id}
              </span>
              {isActive ? (
                <span className="ml-auto flex items-center gap-1 text-[11px] font-medium text-blue-600">
                  <span className="inline-block h-1.5 w-1.5 animate-ping rounded-full bg-blue-500" />
                  正在运行
                </span>
              ) : null}
              {st?.repairAttempt != null && st.repairAttempt > 0 ? (
                <span className={isActive ? "" : "text-[11px] text-amber-600"}>修复 {st.repairAttempt}</span>
              ) : null}
            </li>
          );
        })}
      </ul>

      {state.stream ? <StreamPanel stream={state.stream} /> : null}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-200 px-4 py-2 text-[11.5px] text-slate-500">
        {evalSummary ? <span data-testid="activity-eval">{evalSummary}</span> : null}
        <span>{artifacts} 份产物已生成</span>
        <span className="ml-auto font-mono text-[10px] text-slate-400" data-testid="activity-latest">
          {latestActivity(state.events) ?? ""}
        </span>
      </div>

      <div className="rounded-b-xl border-t border-dashed border-slate-200 bg-white/60 px-4 py-1.5 text-[10.5px] text-slate-400">
        Portfolio Demo Mode · 结构化 Client State · {caseId}
      </div>
    </div>
  );
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

/** DeepSeek-style live output box under the active step. */
function StreamPanel({ stream }: { stream: { text: string; kind: "reasoning" | "content" } }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [stream.text]);
  return (
    <div className="mx-4 mb-3 overflow-hidden rounded-lg border border-slate-200 bg-white" data-testid="stream-panel" data-stream-kind={stream.kind}>
      <p className="flex items-center gap-1.5 border-b border-slate-100 px-3 py-1.5 text-[10.5px] font-medium text-slate-400">
        <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />
        {stream.kind === "reasoning" ? "思考中…" : "正在输出…"}
      </p>
      <div
        ref={ref}
        className={
          stream.kind === "reasoning"
            ? "max-h-44 overflow-y-auto whitespace-pre-wrap px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-400"
            : "max-h-44 overflow-y-auto whitespace-pre-wrap px-3 py-2 text-[12px] leading-relaxed text-slate-600"
        }
      >
        {stream.text}
        <span className="ml-0.5 inline-block h-3 w-[2px] animate-pulse bg-blue-500 align-middle" />
      </div>
    </div>
  );
}

function headerOf(status: RunUiState["status"], streaming: boolean): string {
  if (streaming || status === "running" || status === "queued") return "Agent 正在工作";
  switch (status) {
    case "completed":
      return "分析完成";
    case "needs_review":
      return "需要人工复核";
    case "waiting":
      return "等待补充客户信息";
    case "failed":
      return "运行失败";
    default:
      return "Agent";
  }
}

function evalSummaryOf(state: RunUiState): string | null {
  const closed = state.evals.filter((e) => e.status !== "running");
  if (closed.length === 0) return null;
  const pass = closed.filter((e) => e.status === "pass").length;
  const fail = closed.length - pass;
  if (fail === 0) return `质量校验 ${pass}/${closed.length} 通过`;
  return `质量校验 ${pass}/${closed.length} 通过 · ${fail} 次未过已处理`;
}
