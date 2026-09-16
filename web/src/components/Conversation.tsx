import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { RunUiState } from "../state/runReducer";
import { Markdown } from "./Markdown";
import { labelOf } from "./Pipeline";
import { clockOf } from "./TraceTimeline";

/**
 * CONVERSATION / OUTPUT — the agent's work product, never a re-implementation
 * of it. While the run is live: progress lines straight from runtime events.
 * When the report artifact exists: the runtime's own rendered report.
 */
export function Conversation({
  state,
  reportStageId,
  reportArtifactType,
}: {
  state: RunUiState;
  reportStageId: string;
  reportArtifactType: string;
}) {
  const runDone = state.terminalEvent != null;
  const reportReady = state.stages[reportStageId]?.status === "passed";

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4" data-testid="conversation">
      {state.events.length === 0 && !runDone ? (
        <p className="text-sm text-slate-400">Agent is working…</p>
      ) : (
        <>
          {!reportReady ? <LiveProgress state={state} /> : null}
          {reportReady ? (
            <ReportBlock
              runId={state.runId}
              artifactType={reportArtifactType}
              retryKey={state.terminalEvent?.event_id ?? state.events.length}
            />
          ) : null}
          {runDone && state.terminalEvent ? (
            <div
              className={`mt-4 rounded border px-3 py-2 text-[12.5px] ${
                state.status === "completed"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : state.status === "needs_review"
                    ? "border-amber-200 bg-amber-50 text-amber-800"
                    : "border-red-200 bg-red-50 text-red-800"
              }`}
              data-testid="run-outcome"
            >
              <p className="font-semibold">
                Run {state.status.replaceAll("_", " ")}
                {state.terminalEvent.stage ? ` — stopped at ${state.terminalEvent.stage}` : ""}
              </p>
              {state.terminalEvent.message ? (
                <p className="mt-0.5 break-words text-[11.5px] opacity-80">
                  {state.terminalEvent.message}
                </p>
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function LiveProgress({ state }: { state: RunUiState }) {
  const lines = state.events.filter(
    (e) =>
      e.event_type === "stage_started" ||
      e.event_type === "stage_completed" ||
      e.event_type === "stage_failed" ||
      e.event_type === "eval_failed" ||
      e.event_type === "repair_started" ||
      e.event_type === "repair_exhausted" ||
      e.event_type === "tool_started",
  );
  return (
    <div>
      <p className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500">
        <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
        Agent is working…
      </p>
      <ul className="space-y-1 font-mono text-[12px]" data-testid="live-progress">
        {lines.map((e) => (
          <li key={e.event_id} className="flex gap-2">
            <span className="w-16 shrink-0 text-slate-300">{clockOf(e.timestamp)}</span>
            <span className={lineColor(e.event_type)}>{lineText(e)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function lineColor(t: string): string {
  if (t === "stage_completed" || t === "eval_passed") return "text-emerald-600";
  if (t === "stage_failed" || t === "eval_failed") return "text-red-600";
  if (t.startsWith("repair")) return "text-amber-600";
  if (t.startsWith("tool")) return "text-violet-600";
  return "text-slate-600";
}

function lineText(e: { event_type: string; stage: string | null; repair_attempt: number | null }): string {
  const stage = e.stage ? labelOf({ id: e.stage, skill: e.stage }) : "";
  switch (e.event_type) {
    case "stage_started":
      return `${stage} running…`;
    case "stage_completed":
      return `${stage} completed`;
    case "stage_failed":
      return `${stage} failed`;
    case "eval_failed":
      return `${stage} eval FAIL${e.repair_attempt ? ` · repair ${e.repair_attempt}` : ""}`;
    case "repair_started":
      return `${stage} repair ${e.repair_attempt ?? ""} started`;
    case "repair_exhausted":
      return `${stage} repair budget exhausted — needs review`;
    case "tool_started":
      return `${e.stage ?? "stage"} requested knowledge-search`;
    default:
      return e.event_type;
  }
}

function ReportBlock({
  runId,
  artifactType,
  retryKey,
}: {
  runId: string;
  artifactType: string;
  retryKey: string | number;
}) {
  const [md, setMd] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setMd(null);
    setError(null);

    // the stage_completed event can arrive BEFORE the final checkpoint is flushed
    // to disk — poll briefly instead of failing once and giving up
    const attempt = async (n: number): Promise<void> => {
      try {
        const d = await api.getArtifact(runId, artifactType);
        const payload = (d.artifact as { payload?: { rendered_report?: string } })?.payload;
        if (!alive) return;
        if (payload?.rendered_report) {
          setMd(payload.rendered_report);
        } else if (n < 15) {
          setTimeout(() => void attempt(n + 1), 400);
        } else {
          setError("Report artifact has no rendered report.");
        }
      } catch {
        if (!alive) return;
        if (n < 15) setTimeout(() => void attempt(n + 1), 400);
        else setError("Report artifact could not be loaded.");
      }
    };
    void attempt(0);
    return () => {
      alive = false;
    };
  }, [runId, artifactType, retryKey]);

  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (md === null) return <p className="text-sm text-slate-400">Loading report…</p>;
  return (
    <article className="mx-auto max-w-3xl rounded-lg border border-slate-200 bg-white px-6 py-5 shadow-sm" data-testid="report">
      <Markdown text={md} />
    </article>
  );
}
