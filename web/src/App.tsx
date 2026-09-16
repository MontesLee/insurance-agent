import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api/client";
import type { Run } from "./types/runtime";
import { useRunStream } from "./hooks/useRunStream";
import { CasesSidebar } from "./components/CasesSidebar";
import { Conversation } from "./components/Conversation";
import { RuntimeInspector } from "./components/RuntimeInspector";

const REPORT_STAGE = "report-generation";

/**
 * Three-column layout: CASES | CONVERSATION / OUTPUT | RUNTIME INSPECTOR.
 * The UI observes and triggers runs; the runtime decides everything else.
 */
export default function App() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [conflict, setConflict] = useState<{ caseId: string; runId: string } | null>(null);
  const [meta, setMeta] = useState<Run | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);

  const { state, error: streamError, streaming } = useRunStream(selectedRunId);

  // authoritative Run metadata: load once, then poll while the run is live
  useEffect(() => {
    if (!selectedRunId) {
      setMeta(null);
      setMetaError(null);
      return;
    }
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const run = await api.getRun(selectedRunId);
        if (stopped) return;
        setMeta(run);
        setMetaError(null);
        if (run.status === "queued" || run.status === "running") {
          timer = setTimeout(tick, 700);
        }
      } catch (e) {
        if (!stopped) setMetaError(human(e));
      }
    };
    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [selectedRunId]);

  const startRun = useCallback(async (caseId: string) => {
    setConflict(null);
    try {
      const created = await api.createRun(caseId);
      setSelectedStage(null);
      setRuns((prev) => [
        {
          run_id: created.run_id,
          case_id: created.case_id,
          status: "queued",
          started_at: null,
          completed_at: null,
          current_stage: null,
          event_count: 0,
          result_status: null,
          reasons: [],
          stage_order: [],
        },
        ...prev,
      ]);
      setSelectedRunId(created.run_id);
    } catch (e) {
      if (e instanceof ApiError && e.conflict) {
        setConflict({ caseId: e.conflict.case_id, runId: e.conflict.run_id });
      }
    }
  }, []);

  const stageOrder = useMemo(
    () => (state?.stageOrder.length ? state.stageOrder : (meta?.stage_order ?? [])),
    [state, meta],
  );

  const artifactTypeOf = useCallback(
    (stageId: string): string | null =>
      stageOrder.find((s) => s.id === stageId)?.produces ?? null,
    [stageOrder],
  );

  const reportStage = useMemo(
    () => stageOrder.find((s) => s.id === REPORT_STAGE),
    [stageOrder],
  );
  const reportArtifactType = reportStage?.produces ?? "insurance-report";

  return (
    <div className="flex h-screen min-h-0 flex-col bg-white text-slate-900">
      <header className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[15px] font-semibold tracking-tight">Insurance Agent System</h1>
          <span className="text-[11px] text-slate-400">
            runtime observability · control plane over the existing agent runtime
          </span>
        </div>
        {selectedRunId ? (
          <span className="font-mono text-[11px] text-slate-400">{selectedRunId}</span>
        ) : null}
      </header>

      <div className="flex min-h-0 flex-1">
        <CasesSidebar
          runs={runs}
          selectedRunId={selectedRunId}
          onSelectRun={(rid) => {
            setSelectedStage(null);
            setSelectedRunId(rid);
          }}
          onStartRun={(caseId) => void startRun(caseId)}
          conflict={conflict}
        />
        {!selectedRunId || !state ? (
          <EmptyMiddle />
        ) : (
          <main className="flex min-h-0 min-w-0 flex-1 flex-col">
            <Conversation
              state={state}
              reportStageId={reportStage?.id ?? REPORT_STAGE}
              reportArtifactType={reportArtifactType}
            />
          </main>
        )}
        {selectedRunId && state ? (
          <RuntimeInspector
            meta={meta}
            state={state}
            streaming={streaming}
            error={streamError ?? metaError}
            selectedStage={selectedStage}
            onSelectStage={setSelectedStage}
            artifactTypeOf={artifactTypeOf}
          />
        ) : null}
      </div>
    </div>
  );
}

function EmptyMiddle() {
  return (
    <main className="flex min-h-0 min-w-0 flex-1 items-center justify-center">
      <div className="max-w-sm text-center">
        <p className="text-sm font-medium text-slate-500">No case selected</p>
        <p className="mt-1 text-[12.5px] text-slate-400">
          Pick a case on the left and press <span className="font-medium text-slate-600">Run</span>.
          The pipeline, eval and trace panels fill from live runtime events.
        </p>
      </div>
    </main>
  );
}

function human(e: unknown): string {
  if (e instanceof ApiError) return `Runtime server error ${e.status}`;
  return "Cannot reach the runtime server.";
}
