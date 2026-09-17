/**
 * Developer Mode — the Phase 2 Cases / Runtime console, unchanged in behaviour.
 * Kept as a separate UX entry: engineers debug the runtime here; users stay in
 * the chat. Both modes observe the SAME /api/runs + SSE event stream.
 */
import { useCallback, useMemo, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Run } from "../../types/runtime";
import { useRunMeta, useRunStream } from "../../hooks/useRunStream";
import { CasesSidebar } from "../CasesSidebar";
import { Conversation as RunOutput } from "../Conversation";
import { RuntimeInspector } from "../RuntimeInspector";

const REPORT_STAGE = "report-generation";

export function DeveloperMode({ onBack }: { onBack: () => void }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [conflict, setConflict] = useState<{ caseId: string; runId: string } | null>(null);
  const { meta, error: metaError } = useRunMeta(selectedRunId);
  const { state, error: streamError, streaming } = useRunStream(selectedRunId);

  const startRun = useCallback(async (caseId: string) => {
    setConflict(null);
    try {
      const created = await api.createRun(caseId);
      setSelectedStage(null);
      setRuns((prev) => [
        {
          run_id: created.run_id, case_id: created.case_id, status: "queued",
          started_at: null, completed_at: null, current_stage: null, event_count: 0,
          result_status: null, reasons: [], stage_order: [],
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
    () => stageOrder.find((s) => s.id === REPORT_STAGE)?.id ?? REPORT_STAGE,
    [stageOrder],
  );
  const reportArtifactType = stageOrder.find((s) => s.id === REPORT_STAGE)?.produces ?? "insurance-report";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
        <div className="flex items-baseline gap-3">
          <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-white">
            Dev
          </span>
          <span className="text-[13px] font-semibold text-slate-700">Cases · Runtime Console</span>
          <span className="hidden font-mono text-[11px] text-slate-400 sm:inline">
            {selectedRunId ?? "no run selected"}
          </span>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11.5px] font-medium text-slate-600 hover:bg-slate-50"
          data-testid="back-to-chat"
        >
          ← 返回 Chat
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        <CasesSidebar
          runs={runs}
          selectedRunId={selectedRunId}
          onSelectRun={(rid) => { setSelectedStage(null); setSelectedRunId(rid); }}
          onStartRun={(caseId) => void startRun(caseId)}
          conflict={conflict}
        />
        {!selectedRunId || !state ? (
          <main className="flex min-h-0 min-w-0 flex-1 items-center justify-center">
            <div className="max-w-sm text-center">
              <p className="text-sm font-medium text-slate-500">No case selected</p>
              <p className="mt-1 text-[12.5px] text-slate-400">
                左侧选择 case 并 Run。Pipeline / Eval / Trace 由真实 Runtime Events 驱动。
              </p>
            </div>
          </main>
        ) : (
          <main className="flex min-h-0 min-w-0 flex-1 flex-col">
            <RunOutput state={state} reportStageId={reportStage} reportArtifactType={reportArtifactType} />
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
