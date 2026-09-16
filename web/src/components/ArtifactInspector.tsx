import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ArtifactDetail } from "../types/runtime";

/**
 * ARTIFACT INSPECTOR — shows exactly what the runtime produced for a stage:
 * registry metadata (id / producer / created_at), the provenance chain from the
 * artifact registry's own lineage, and the artifact's structured JSON + raw view.
 * It never regenerates or rewrites an artifact.
 */
export function ArtifactInspector({
  runId,
  artifactType,
  onPickArtifact,
}: {
  runId: string;
  artifactType: string;
  onPickArtifact?: (artifactType: string) => void;
}) {
  const [detail, setDetail] = useState<ArtifactDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [raw, setRaw] = useState(false);

  useEffect(() => {
    setDetail(null);
    setError(null);
    setRaw(false);
    let alive = true;
    api
      .getArtifact(runId, artifactType)
      .then((d) => alive && setDetail(d))
      .catch((e) => alive && setError(human(e)));
    return () => {
      alive = false;
    };
  }, [runId, artifactType]);

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-slate-400">{error}</p>
      </div>
    );
  }
  if (!detail) {
    return <p className="px-1 text-xs text-slate-400">Loading artifact…</p>;
  }

  return (
    <div className="space-y-3" data-testid="artifact-inspector" data-artifact-type={artifactType}>
      <div className="grid grid-cols-[6.5rem_1fr] gap-x-2 gap-y-1 font-mono text-[10.5px]">
        <Meta label="artifact_id" value={detail.artifact_id} />
        <Meta label="stage" value={detail.producer_stage} />
        <Meta label="producer" value={detail.producer_skill} />
        <Meta label="created" value={clock(detail.created_at)} />
        <Meta label="status" value={detail.status} />
        <Meta label="inputs" value={detail.input_artifacts.join(", ") || "—"} />
        <Meta label="evidence" value={detail.evidence_refs.slice(0, 4).join(", ") || "—"} />
      </div>

      <div>
        <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-slate-400">
          Provenance
        </p>
        <ol className="space-y-0">
          {detail.lineage.map((node, i) => (
            <li key={node.artifact_id}>
              {i > 0 ? <span className="block pl-3 text-slate-300">↓</span> : null}
              <button
                type="button"
                disabled={node.artifact_type === artifactType}
                onClick={() => node.artifact_type && onPickArtifact?.(node.artifact_type)}
                className={`flex w-full items-baseline gap-2 rounded px-1 py-[2px] text-left text-[11.5px] ${
                  node.artifact_type === artifactType
                    ? "bg-slate-100 text-slate-700"
                    : "hover:bg-slate-50 text-slate-600"
                }`}
              >
                <span className="w-14 shrink-0 font-mono text-[10px] text-slate-400">
                  {node.artifact_id}
                </span>
                <span>{node.artifact_type ?? "?"}</span>
              </button>
            </li>
          ))}
        </ol>
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between">
          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
            Artifact
          </p>
          <button
            type="button"
            onClick={() => setRaw(!raw)}
            className="rounded border border-slate-200 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 hover:bg-slate-50"
          >
            {raw ? "structured" : "raw JSON"}
          </button>
        </div>
        {raw ? (
          <pre className="max-h-72 overflow-auto rounded border border-slate-200 bg-slate-50 p-2 font-mono text-[10px] leading-snug text-slate-600">
            {JSON.stringify(detail.artifact, null, 2)}
          </pre>
        ) : (
          <StructuredView value={detail.artifact} />
        )}
      </div>
    </div>
  );
}

function StructuredView({ value }: { value: unknown }) {
  const payload =
    value && typeof value === "object" && "payload" in (value as Record<string, unknown>)
      ? (value as { payload: unknown }).payload
      : value;
  if (!payload || typeof payload !== "object") {
    return (
      <pre className="rounded border border-slate-200 bg-slate-50 p-2 font-mono text-[10px] text-slate-600">
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }
  const entries = Object.entries(payload as Record<string, unknown>).slice(0, 12);
  return (
    <div className="rounded border border-slate-200">
      {entries.map(([k, v], i) => (
        <div
          key={k}
          className={`grid grid-cols-[9rem_1fr] gap-2 px-2 py-1 ${i % 2 ? "bg-slate-50/60" : ""}`}
        >
          <span className="font-mono text-[10.5px] text-slate-400">{k}</span>
          <span className="break-all font-mono text-[10.5px] text-slate-700">
            {summarize(v)}
          </span>
        </div>
      ))}
    </div>
  );
}

function summarize(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return `[${v.length} items] ` + JSON.stringify(v.slice(0, 2)).slice(0, 120);
  return JSON.stringify(v).slice(0, 160);
}

function Meta({ label, value }: { label: string; value: string | null }) {
  return (
    <>
      <span className="text-slate-400">{label}</span>
      <span className="break-all text-slate-700">{value ?? "—"}</span>
    </>
  );
}

function clock(iso: string | null): string {
  if (!iso) return "—";
  const t = iso.indexOf("T");
  return t >= 0 ? iso.slice(0, t) + " " + iso.slice(t + 1, t + 9) : iso;
}

function human(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 404) return "No artifact of this type (yet) for this run.";
    return `Artifact read failed (${e.status}).`;
  }
  return "Artifact read failed.";
}
