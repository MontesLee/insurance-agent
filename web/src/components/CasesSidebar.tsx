import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CaseInfo, Run } from "../types/runtime";
import { RunStatusBadge } from "./StatusBadge";

/**
 * CASES — the left rail: the runtime's case catalog (GET /api/cases) plus this
 * browser session's runs. Start Run = POST /api/runs (the only control action
 * the UI ever takes; everything else is observation).
 */
export function CasesSidebar({
  runs,
  onSelectRun,
  onStartRun,
  conflict,
}: {
  runs: Run[];
  selectedRunId?: string | null;
  onSelectRun: (runId: string) => void;
  onStartRun: (caseId: string) => void;
  conflict: { caseId: string; runId: string } | null;
}) {
  const [cases, setCases] = useState<CaseInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .cases()
      .then((r) => alive && setCases(r.cases))
      .catch(() => alive && setError("Cannot load cases — is the runtime server running?"));
    return () => {
      alive = false;
    };
  }, []);

  const latestByCase = new Map<string, Run>();
  for (const r of runs) if (!latestByCase.has(r.case_id)) latestByCase.set(r.case_id, r);

  const shown = (cases ?? []).filter(
    (c) =>
      !filter ||
      c.id.toLowerCase().includes(filter.toLowerCase()) ||
      (c.desc ?? "").includes(filter) ||
      (c.category ?? "").includes(filter),
  );

  return (
    <aside className="flex h-full min-h-0 w-64 shrink-0 flex-col border-r border-slate-200 bg-slate-50/70">
      <div className="border-b border-slate-200 px-3 py-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          Cases
        </p>
      </div>
      <div className="px-3 py-2">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="filter cases…"
          className="w-full rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 outline-none placeholder:text-slate-300 focus:border-slate-400"
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3" data-testid="cases-list">
        {error ? <p className="px-1 text-xs text-red-500">{error}</p> : null}
        {!error && cases === null ? (
          <p className="px-1 text-xs text-slate-400">Loading cases…</p>
        ) : null}
        {shown.map((c) => {
          const latest = latestByCase.get(c.id) ?? null;
          return (
            <div key={c.id} className="mb-1 rounded border border-slate-200 bg-white">
              <div className="px-2 pt-1.5 pb-1">
                <p className="truncate font-mono text-[11px] text-slate-500">{c.id}</p>
                <p className="truncate text-[12px] text-slate-800" title={c.desc ?? ""}>
                  {c.desc ?? c.category}
                </p>
              </div>
              <div className="flex items-center justify-between border-t border-slate-100 px-2 py-1">
                {latest ? (
                  <button
                    type="button"
                    onClick={() => onSelectRun(latest.run_id)}
                    className="flex items-center gap-1.5 text-left"
                    data-testid="open-latest-run"
                  >
                    <RunStatusBadge status={latest.status} />
                    <span className="font-mono text-[10px] text-slate-400">
                      {latest.run_id.slice(0, 12)}
                    </span>
                  </button>
                ) : (
                  <span className="font-mono text-[10px] text-slate-300">no run yet</span>
                )}
                <button
                  type="button"
                  onClick={() => onStartRun(c.id)}
                  className="rounded bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-white transition-colors hover:bg-slate-700"
                  data-start-case={c.id}
                >
                  Run
                </button>
              </div>
            </div>
          );
        })}
        {conflict ? (
          <div
            className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-2 text-[11.5px] text-amber-800"
            data-testid="conflict-banner"
          >
            <p className="font-semibold">This case is already running.</p>
            <p className="mt-0.5 font-mono text-[10.5px]">Run: {conflict.runId}</p>
            <button
              type="button"
              onClick={() => onSelectRun(conflict.runId)}
              className="mt-1 rounded border border-amber-300 bg-white px-2 py-0.5 text-[11px] font-medium text-amber-800 hover:bg-amber-100"
            >
              Open active run
            </button>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
