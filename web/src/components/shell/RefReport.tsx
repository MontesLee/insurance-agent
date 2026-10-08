import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Markdown } from "../Markdown";
import { toArtifactView } from "../../state/consumerView";

/**
 * REF REPORT (28.G / D-05′) — a consumer deep link: the URL carries ONLY
 * an opaque artifact reference; the server resolves it AND re-checks
 * ownership before returning content. The reference is never
 * authorization — an unauthenticated or non-owning visitor gets a
 * consumer-safe refusal, never artifact data.
 */
export function RefReport({ ref }: { ref: string }) {
  const [md, setMd] = useState<string | null>(null);
  const [title, setTitle] = useState<string>("报告");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.artifactByRef(ref)
      .then((detail) => {
        if (!alive) return;
        const artifact = detail.artifact as {
          artifact_type?: string;
          payload?: { rendered_report?: string };
        };
        const view = toArtifactView(artifact?.artifact_type ?? "");
        if (view) setTitle(view.title);
        const rendered = artifact?.payload?.rendered_report;
        if (rendered) setMd(rendered);
        else setError("报告中没有可渲染的内容。");
      })
      .catch(() => {
        if (alive) setError("无法打开这份报告（链接无效、已过期，或不是你的报告）。");
      });
    return () => {
      alive = false;
    };
  }, [ref]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-6" data-testid="ref-report">
      <a
        href="#/chat"
        className="text-[12.5px] font-medium text-slate-500 hover:text-slate-700"
      >
        ← 返回对话
      </a>
      <h1 className="mt-3 text-[16px] font-semibold text-slate-800">{title}</h1>
      <div className="mt-4 rounded-xl border border-slate-200 bg-white px-6 py-5">
        {error ? <p className="text-sm text-slate-500">{error}</p> : null}
        {!error && md === null ? (
          <p className="text-sm text-slate-400">报告加载中…</p>
        ) : null}
        {md !== null ? <Markdown text={md} /> : null}
      </div>
    </div>
  );
}
