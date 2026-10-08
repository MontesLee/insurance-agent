import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Markdown } from "../Markdown";
import { toArtifactView } from "../../state/consumerView";

/**
 * ARTIFACT CARD — a REAL artifact the runtime produced (28.E-2 consumer
 * view). Rendering is gated by the consumerView allowlist: only known
 * consumer-displayable types render (unknown types → nothing), and the
 * card shows the consumer title + CTA only — never artifact_type, never
 * run ids. "查看报告" opens the runtime's own artifact (never
 * regenerated) in a modal.
 */
export function ArtifactCard({
  runId,
  artifactType,
}: {
  runId: string;
  artifactType: string;
  title?: string; // retained for message-shape compat; display uses the allowlist view
}) {
  const [open, setOpen] = useState(false);
  const view = toArtifactView(artifactType);
  if (!view) return null;

  return (
    <div className="my-2 max-w-md">
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="artifact-card">
        <div className="px-4 py-3">
          <p className="flex items-center gap-2 text-[13.5px] font-semibold text-slate-800">
            <span className="text-slate-400">📄</span>
            {view.title}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="w-full rounded-b-xl border-t border-slate-100 px-4 py-2 text-left text-[12.5px] font-medium text-slate-600 transition-colors hover:bg-slate-50"
          data-testid="open-report"
        >
          {view.cta} →
        </button>
      </div>
      {open ? (
        <ReportModal runId={runId} artifactType={artifactType} title={view.title} onClose={() => setOpen(false)} />
      ) : null}
    </div>
  );
}

function ReportModal({
  runId,
  artifactType,
  title,
  onClose,
}: {
  runId: string;
  artifactType: string;
  title: string;
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

  // E-4 export: client-side Markdown download of the ALREADY-FETCHED
  // content — no new backend contract; the filename is consumer-safe
  // (never ids/types).
  const download = () => {
    if (md === null) return;
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // 28.G / D-05′: copy a consumer deep link — the server issues an opaque
  // reference (ownership re-checked on every resolution); the URL never
  // contains a run id.
  const [linkCopied, setLinkCopied] = useState(false);
  const copyLink = async () => {
    try {
      const { ref } = await api.issueArtifactRef(runId, artifactType);
      const url = `${window.location.origin}${window.location.pathname}#/report/${ref}`;
      await navigator.clipboard?.writeText(url);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    } catch {
      /* clipboard unavailable or issuance refused — silent no-op */
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      data-testid="report-modal"
    >
      <div className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <p className="text-[14px] font-semibold text-slate-800">{title}</p>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => void copyLink()}
              className="rounded border border-slate-200 px-2 py-0.5 text-[12px] font-medium text-slate-600 transition hover:bg-slate-50"
              aria-label="复制报告链接"
              data-testid="copy-report-link"
            >
              {linkCopied ? "已复制" : "链接"}
            </button>
            <button
              type="button"
              onClick={download}
              disabled={md === null}
              className="rounded border border-slate-200 px-2 py-0.5 text-[12px] font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-40"
              aria-label="下载报告"
              data-testid="download-report"
            >
              下载
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded px-2 py-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              aria-label="关闭报告"
            >
              ✕
            </button>
          </div>
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
