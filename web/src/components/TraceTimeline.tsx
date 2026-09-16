import { useState } from "react";
import type { RuntimeEvent } from "../types/runtime";

/** Compact HH:MM:SS from the event's own UTC timestamp. */
export function clockOf(iso: string): string {
  const t = iso.indexOf("T");
  return t >= 0 ? iso.slice(t + 1, t + 9) : iso;
}

/**
 * TRACE TIMELINE — every runtime event in order; click for the full record.
 * Events are metadata-only by contract (no client-sensitive content).
 */
export function TraceTimeline({
  events,
  streaming,
}: {
  events: RuntimeEvent[];
  streaming: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);

  if (events.length === 0) {
    return (
      <p className="px-1 text-xs text-slate-400" data-testid="trace-empty">
        {streaming ? "Waiting for runtime events…" : "No events."}
      </p>
    );
  }
  return (
    <ol className="space-y-0" data-testid="trace-timeline">
      {events.map((e) => {
        const isOpen = open === e.event_id;
        return (
          <li key={e.event_id}>
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : e.event_id)}
              className="flex w-full items-baseline gap-2 rounded px-1 py-[3px] text-left font-mono text-[11px] leading-tight hover:bg-slate-50"
              data-event-type={e.event_type}
            >
              <span className="w-16 shrink-0 text-slate-400">{clockOf(e.timestamp)}</span>
              <span className={colorOf(e.event_type)}>{e.event_type}</span>
              {e.stage ? <span className="truncate text-slate-500">{e.stage}</span> : null}
              {e.repair_attempt != null && e.repair_attempt > 0 ? (
                <span className="text-amber-600">repair {e.repair_attempt}</span>
              ) : null}
            </button>
            {isOpen ? <EventDetail event={e} /> : null}
          </li>
        );
      })}
      {streaming ? (
        <li className="px-1 py-1 font-mono text-[11px] text-slate-400">
          <span className="animate-pulse">▍streaming…</span>
        </li>
      ) : null}
    </ol>
  );
}

function EventDetail({ event }: { event: RuntimeEvent }) {
  const rows: [string, string][] = [
    ["event_id", event.event_id],
    ["event_type", event.event_type],
    ["stage", event.stage ?? "—"],
    ["skill", event.skill ?? "—"],
    ["status", event.status ?? "—"],
    ["artifact_id", event.artifact_id ?? "—"],
    ["eval_id", event.eval_id ?? "—"],
    ["repair_attempt", event.repair_attempt?.toString() ?? "—"],
    ["timestamp", event.timestamp],
    ["message", event.message ?? "—"],
  ];
  return (
    <div className="mb-1 rounded border border-slate-200 bg-slate-50 p-2">
      <dl className="grid grid-cols-[8rem_1fr] gap-x-2 gap-y-0.5 font-mono text-[10px]">
        {rows.map(([k, v]) => (
          <div key={k} className="col-span-2 grid grid-cols-subgrid">
            <dt className="text-slate-400">{k}</dt>
            <dd className="break-all text-slate-700">{v}</dd>
          </div>
        ))}
        <div className="col-span-2 mt-1 text-slate-400">data</div>
        <dd className="col-span-2 overflow-x-auto rounded bg-white p-1 text-[10px] text-slate-600">
          <pre className="whitespace-pre-wrap break-all">{JSON.stringify(event.data, null, 2)}</pre>
        </dd>
      </dl>
    </div>
  );
}

function colorOf(t: string): string {
  if (t.startsWith("run_") || t.startsWith("stage_")) return "text-slate-700";
  if (t.startsWith("eval_pass")) return "text-emerald-600";
  if (t.startsWith("eval_fail") || t === "stage_failed") return "text-red-600";
  if (t.startsWith("repair")) return "text-amber-600";
  if (t.startsWith("tool")) return "text-violet-600";
  if (t.startsWith("artifact")) return "text-cyan-700";
  return "text-slate-500";
}
