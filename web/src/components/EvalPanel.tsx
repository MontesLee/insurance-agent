import type { EvalUiEntry } from "../state/runReducer";

/**
 * EVAL — pass / fail / repair trail, in event order. Pure projection of the
 * eval_* and repair_* runtime events (never re-evaluates anything).
 */
export function EvalPanel({ evals }: { evals: EvalUiEntry[] }) {
  if (evals.length === 0) {
    return <p className="px-1 text-xs text-slate-400">No eval yet.</p>;
  }
  const groups = new Map<string, EvalUiEntry[]>();
  for (const ev of evals) {
    const key = ev.stage ?? "run";
    const list = groups.get(key) ?? [];
    list.push(ev);
    groups.set(key, list);
  }
  return (
    <div className="space-y-3" data-testid="eval-panel">
      {[...groups.entries()].map(([stageLabel, entries]) => (
        <div key={stageLabel}>
          <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-slate-400">
            {stageLabel}
          </p>
          <ul className="space-y-0.5">
            {entries.map((ev) => (
              <li key={ev.key} className="flex items-baseline gap-2 text-[12px]">
                <span className="w-16 shrink-0 font-mono text-[10px] text-slate-400">
                  {ev.evalId ?? "…"}
                </span>
                {ev.status === "pass" ? (
                  <span className="text-emerald-600">✓ PASS</span>
                ) : ev.status === "fail" ? (
                  <span className="text-red-600">✕ FAIL</span>
                ) : (
                  <span className="animate-pulse text-blue-600">evaluating…</span>
                )}
                {ev.repairAttempt != null && ev.repairAttempt > 0 ? (
                  <span className="text-slate-400">
                    · repair {ev.repairAttempt}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
