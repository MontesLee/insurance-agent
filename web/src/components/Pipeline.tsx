import type { StageInfo } from "../types/runtime";
import type { StageUiState } from "../state/runReducer";
import { StageGlyph } from "./StatusBadge";

/**
 * PIPELINE — the canonical stage list comes verbatim from the runtime's
 * stage_order; per-stage status comes ONLY from SSE runtime events via the
 * reducer's transition table. Clicking a stage opens its artifact inspector.
 */
export function Pipeline({
  stageOrder,
  stages,
  currentStage,
  selected,
  onSelect,
}: {
  stageOrder: StageInfo[];
  stages: Record<string, StageUiState>;
  currentStage: string | null;
  selected: string | null;
  onSelect: (stageId: string) => void;
}) {
  if (stageOrder.length === 0) {
    return <p className="px-1 text-xs text-slate-400">Waiting for run metadata…</p>;
  }
  return (
    <ol className="space-y-1">
      {stageOrder.map((info, idx) => {
        const st = stages[info.id];
        const status = st?.status ?? "pending";
        const isNow = currentStage === info.id && status === "running";
        return (
          <li key={info.id}>
            <button
              type="button"
              onClick={() => onSelect(info.id)}
              className={`flex w-full items-center gap-2 rounded px-1.5 py-1 text-left transition-colors ${
                selected === info.id ? "bg-slate-100" : "hover:bg-slate-50"
              }`}
              data-stage-id={info.id}
              data-stage-status={status}
            >
              <StageGlyph status={status} />
              <span className="min-w-0 flex-1">
                <span
                  className={`block truncate text-[13px] leading-tight ${
                    status === "pending" ? "text-slate-400" : "text-slate-700"
                  } ${isNow ? "font-semibold" : ""}`}
                >
                  {labelOf(info)}
                </span>
                {(st?.repairAttempt != null && st.repairAttempt > 0) || st?.artifactId ? (
                  <span className="block truncate font-mono text-[10px] leading-tight text-slate-400">
                    {st.artifactId ?? ""}
                    {st.repairAttempt != null && st.repairAttempt > 0
                      ? ` · repair ${st.repairAttempt}`
                      : ""}
                  </span>
                ) : null}
              </span>
              <span className="font-mono text-[10px] text-slate-300">{idx + 1}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

const LABELS: Record<string, string> = {
  "client-intake": "Client Intake",
  "requirement-analysis": "Requirement Analysis",
  "risk-analysis": "Risk Analysis",
  "coverage-gap-analysis": "Coverage Gap Analysis",
  solution: "Solution",
  "product-candidate-provider": "Product Candidate",
  "product-recommendation": "Recommendation",
  "report-generation": "Report",
};

export function labelOf(info: { id: string; skill: string | null }): string {
  return LABELS[info.id] ?? info.skill ?? info.id;
}
