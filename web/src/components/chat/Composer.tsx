import { useRef } from "react";
import { DEMO_CASES, mapPromptToCase } from "../../state/chatState";

/**
 * COMPOSER — Enter sends, Shift+Enter newline. While the agent runs the send is
 * disabled and the only action is "停止查看" (disconnect the VIEW — the runtime
 * keeps executing; there is no cancel API and the UI never fakes one).
 */
export function Composer({
  disabled,
  streaming,
  viewStopped,
  onStopViewing,
  onResumeViewing,
  onSend,
  draft,
  setDraft,
  caseId,
  setCaseId,
  mode = "demo",
}: {
  disabled: boolean;
  streaming: boolean;
  viewStopped: boolean;
  onStopViewing: () => void;
  onResumeViewing: () => void;
  onSend: (text: string, caseId: string) => void;
  draft: string;
  setDraft: (t: string) => void;
  caseId: string;
  setCaseId: (c: string) => void;
  mode?: "agent" | "demo";
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  const send = () => {
    const text = draft.trim();
    if (!text || disabled) return;
    const mapped = mapPromptToCase(text);
    setCaseId(mapped);
    setDraft("");
    onSend(text, mapped);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="border-t border-slate-200 bg-white/90 px-4 py-3 backdrop-blur" data-testid="composer">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm focus-within:border-slate-400">
          <textarea
            ref={ref}
            value={draft}
            rows={1}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="输入你的家庭保障问题……"
            disabled={disabled}
            className="max-h-40 min-h-[1.75rem] flex-1 resize-none bg-transparent text-[13.5px] leading-relaxed text-slate-800 outline-none placeholder:text-slate-300 disabled:opacity-60"
            data-testid="composer-input"
          />
          {streaming ? (
            <button
              type="button"
              onClick={onStopViewing}
              className="shrink-0 rounded-lg border border-slate-200 px-3 py-1.5 text-[12px] font-medium text-slate-500 hover:bg-slate-50"
              data-testid="stop-viewing"
            >
              停止查看
            </button>
          ) : null}
          {viewStopped ? (
            <button
              type="button"
              onClick={onResumeViewing}
              className="shrink-0 rounded-lg border border-blue-200 px-3 py-1.5 text-[12px] font-medium text-blue-600 hover:bg-blue-50"
              data-testid="resume-viewing"
            >
              重新连接
            </button>
          ) : null}
          <button
            type="button"
            onClick={send}
            disabled={disabled || !draft.trim()}
            className="shrink-0 rounded-lg bg-slate-800 px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-slate-700 disabled:opacity-40"
            aria-label="发送"
            data-testid="send"
          >
            ↑
          </button>
        </div>
        <div className="mt-1.5 flex items-center gap-2 text-[10.5px] text-slate-400">
          <span>Enter 发送 · Shift+Enter 换行</span>
          {mode === "demo" ? (
            <>
              <span className="text-slate-300">|</span>
              <label className="flex items-center gap-1">
                演示 case：
                <select
                  value={caseId}
                  onChange={(e) => setCaseId(e.target.value)}
                  className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10.5px] text-slate-600 outline-none"
                  data-testid="case-select"
                >
                  {DEMO_CASES.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label} · {c.id}
                    </option>
                  ))}
                </select>
              </label>
            </>
          ) : (
            <span className="text-blue-500/80">Agent Mode · 真实 LLM 理解与决策</span>
          )}
        </div>
      </div>
    </div>
  );
}
