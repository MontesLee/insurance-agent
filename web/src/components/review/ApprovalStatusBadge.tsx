/**
 * Approval status badge — labels are VERBATIM backend statuses
 * (runtime/approval/models.py TRANSITIONS). The UI never renames
 * or invents approval states; unknown values render as-is with a
 * neutral style rather than being mapped to a known state.
 */
const STYLES: Record<string, { cls: string; dot: string }> = {
  PENDING: { cls: "bg-slate-100 text-slate-600 border-slate-200", dot: "bg-slate-400" },
  WAITING_HUMAN: { cls: "bg-amber-50 text-amber-700 border-amber-200", dot: "bg-amber-500 animate-pulse" },
  APPROVED: { cls: "bg-emerald-50 text-emerald-700 border-emerald-200", dot: "bg-emerald-500" },
  REJECTED: { cls: "bg-red-50 text-red-700 border-red-200", dot: "bg-red-500" },
  EXPIRED: { cls: "bg-slate-100 text-slate-500 border-slate-200", dot: "bg-slate-300" },
  RESUMED: { cls: "bg-blue-50 text-blue-700 border-blue-200", dot: "bg-blue-500" },
};

export function ApprovalStatusBadge({ status }: { status: string }) {
  const s = STYLES[status] ?? {
    cls: "bg-slate-50 text-slate-500 border-slate-200",
    dot: "bg-slate-300",
  };
  return (
    <span
      data-testid={`approval-status-${status}`}
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-semibold tracking-wide ${s.cls}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {status}
    </span>
  );
}
