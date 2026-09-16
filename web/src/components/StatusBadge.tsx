import type { RunStatus } from "../types/runtime";
import type { StageUiStatus } from "../state/runReducer";

const RUN_STYLES: Record<RunStatus, { label: string; cls: string; dot: string }> = {
  queued: { label: "QUEUED", cls: "bg-slate-100 text-slate-600 border-slate-200", dot: "bg-slate-400" },
  running: { label: "RUNNING", cls: "bg-blue-50 text-blue-700 border-blue-200", dot: "bg-blue-500 animate-pulse" },
  completed: { label: "COMPLETED", cls: "bg-emerald-50 text-emerald-700 border-emerald-200", dot: "bg-emerald-500" },
  failed: { label: "FAILED", cls: "bg-red-50 text-red-700 border-red-200", dot: "bg-red-500" },
  needs_review: { label: "NEEDS REVIEW", cls: "bg-amber-50 text-amber-700 border-amber-200", dot: "bg-amber-500" },
  waiting: { label: "WAITING FOR CLIENT", cls: "bg-violet-50 text-violet-700 border-violet-200", dot: "bg-violet-500" },
};

export function RunStatusBadge({ status }: { status: RunStatus | "unknown" }) {
  if (status === "unknown") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold tracking-wide text-slate-500">
        <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
        UNKNOWN
      </span>
    );
  }
  const s = RUN_STYLES[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-semibold tracking-wide ${s.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

const STAGE_GLYPH: Record<StageUiStatus, { glyph: string; cls: string }> = {
  pending: { glyph: "○", cls: "text-slate-300" },
  running: { glyph: "●", cls: "text-blue-500 animate-pulse" },
  passed: { glyph: "✓", cls: "text-emerald-600" },
  failed: { glyph: "✕", cls: "text-red-600" },
  needs_review: { glyph: "⚠", cls: "text-amber-500" },
};

export function StageGlyph({ status }: { status: StageUiStatus }) {
  const g = STAGE_GLYPH[status];
  return <span className={`inline-block w-4 text-center font-mono text-sm ${g.cls}`}>{g.glyph}</span>;
}
