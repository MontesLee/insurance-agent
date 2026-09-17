import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Markdown } from "../Markdown";

/**
 * ARTIFACT CARD — an artifact the runtime produced (report first-class).
 * "查看报告" opens the runtime's own artifact (never regenerated) in a modal.
 */
export function ArtifactCard({
  runId,
  artifactType,
  title,
}: {
  runId: string;
  artifactType: string;
  title: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="my-2 max-w-md">
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="artifact-card">
        <div className="px-4 py-3">
          <p className="flex items-center gap-2 text-[13.5px] font-semibold text-slate-800">
            <span className="text-slate-400">📄</span>
            {title}
          </p>
          <p className="mt-1 font-mono text-[10.5px] text-slate-400">
            {artifactType} · run {runId.slice(0, 12)}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="w-full rounded-b-xl border-t border-slate-100 px-4 py-2 text-left text-[12.5px] font-medium text-slate-600 transition-colors hover:bg-slate-50"
          data-testid="open-report"
        >
          查看完整报告 →
        </button>
      </div>
      {open ? (
        <ReportModal runId={runId} artifactType={artifactType} onClose={() => setOpen(false)} />
      ) : null}
    </div>
  );
}

function ReportModal({
  runId,
  artifactType,
  onClose,
}: {
  runId: string;
  artifactType: string;
  onClose: () => void;
}) {
  const [md, setMd] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const attempt = async (n: number): Promise<void> => {
      try {
        const d = await api.getArtifact(runId, artifactType);
        const payload = (d.artifact as { payload?: { rendered_report?: string } })?.payload;
        if (!alive) return;
        if (payload?.rendered_report) setMd(payload.rendered_report);
        else if (n < 15) setTimeout(() => void attempt(n + 1), 400);
        else setError("报告中没有可渲染的内容。");
      } catch {
        if (alive && n >= 15) setError("报告加载失败。");
        else if (alive) setTimeout(() => void attempt(n + 1), 400);
      }
    };
    void attempt(0);
    return () => {
      alive = false;
    };
  }, [runId, artifactType]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      data-testid="report-modal"
    >
      <div className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <p className="text-[14px] font-semibold text-slate-800">{artifactType}</p>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="关闭报告"
          >
            ✕
          </button>
        </div>
        <div className="overflow-y-auto px-6 py-5">
          {error ? <p className="text-sm text-red-500">{error}</p> : null}
          {!error && md === null ? <p className="text-sm text-slate-400">报告加载中…</p> : null}
          {md !== null ? <Markdown text={md} /> : null}
        </div>
      </div>
    </div>
  );
}
