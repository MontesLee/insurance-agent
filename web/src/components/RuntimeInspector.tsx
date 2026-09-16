import type { Run } from "../types/runtime";
import type { RunUiState } from "../state/runReducer";
import { RunStatusBadge } from "./StatusBadge";
import { Pipeline } from "./Pipeline";
import { EvalPanel } from "./EvalPanel";
import { TraceTimeline } from "./TraceTimeline";
import { ArtifactInspector } from "./ArtifactInspector";

/**
 * RUNTIME INSPECTOR — the right rail. RUN / PIPELINE / EVAL / TRACE sections,
 * plus the artifact inspector for the selected stage. Every value here is either
 * server metadata (Run) or a projection of runtime events — nothing inferred.
 */
export function RuntimeInspector({
  meta,
  state,
  streaming,
  error,
  selectedStage,
  onSelectStage,
  artifactTypeOf,
}: {
  meta: Run | null;
  state: RunUiState;
  streaming: boolean;
  error: string | null;
  selectedStage: string | null;
  onSelectStage: (stageId: string | null) => void;
  artifactTypeOf: (stageId: string) => string | null;
}) {
  const stageOrder = state.stageOrder.length ? state.stageOrder : (meta?.stage_order ?? []);
  const artifactType = selectedStage ? artifactTypeOf(selectedStage) : null;

  return (
    <aside className="flex h-full min-h-0 w-[22rem] shrink-0 flex-col overflow-y-auto border-l border-slate-200 bg-slate-50/70">
      <Section title="Run" testid="run-section">
        {meta ? (
          <div className="grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-1 font-mono text-[10.5px]">
            <Row label="run_id" value={meta.run_id} />
            <Row label="case_id" value={meta.case_id} />
            <Row label="status" value={<RunStatusBadge status={meta.status} />} />
            <Row label="started" value={clock(meta.started_at)} />
            <Row label="completed" value={clock(meta.completed_at)} />
            <Row label="events" value={String(state.events.length)} />
          </div>
        ) : (
          <p className="px-1 text-xs text-slate-400">Loading run metadata…</p>
        )}
        {streaming ? (
          <p className="mt-2 flex items-center gap-1.5 px-1 text-[11px] text-blue-600">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
            SSE stream live
          </p>
        ) : null}
        {error ? <p className="mt-2 px-1 text-[11px] text-red-500">{error}</p> : null}
      </Section>

      <Section title="Pipeline" testid="pipeline-section">
        <Pipeline
          stageOrder={stageOrder}
          stages={state.stages}
          currentStage={meta?.current_stage ?? state.currentStage}
          selected={selectedStage}
          onSelect={onSelectStage}
        />
      </Section>

      <Section title="Eval" testid="eval-section">
        <EvalPanel evals={state.evals} />
      </Section>

      <Section title="Trace" testid="trace-section">
        <TraceTimeline events={state.events} streaming={streaming} />
      </Section>

      {selectedStage && artifactType ? (
        <Section title={`Artifact · ${artifactType}`} testid="artifact-section" sticky>
          <ArtifactInspector
            runId={state.runId}
            artifactType={artifactType}
            onPickArtifact={(t) => {
              const st = stageOrder.find((s) => s.produces === t);
              if (st) onSelectStage(st.id);
            }}
          />
        </Section>
      ) : null}
    </aside>
  );
}

function Section({
  title,
  children,
  testid,
  sticky,
}: {
  title: string;
  children: React.ReactNode;
  testid?: string;
  sticky?: boolean;
}) {
  return (
    <section
      className={`border-b border-slate-200 px-3 py-2.5 ${sticky ? "sticky top-0 bg-slate-50/95 backdrop-blur" : ""}`}
      data-testid={testid}
    >
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        {title}
      </p>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <>
      <span className="text-slate-400">{label}</span>
      <span className="min-w-0 break-all text-slate-700">{value}</span>
    </>
  );
}

function clock(iso: string | null): string {
  if (!iso) return "—";
  const t = iso.indexOf("T");
  return t >= 0 ? iso.slice(t + 1, t + 9) : iso;
}
