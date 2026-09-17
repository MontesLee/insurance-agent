import { useEffect, useState } from "react";
import { ChatLayout } from "./components/chat/ChatLayout";
import { DeveloperMode } from "./components/developer/DeveloperMode";

/**
 * Two UX entries over ONE runtime (§26):
 *   User Mode (default) — chat-first agent experience
 *   Developer Mode      — Phase 2 cases / runtime console
 * Both consume the same /api/runs + SSE RuntimeEvent stream; neither owns
 * agent execution state.
 */
type Mode = "chat" | "developer";
const MODE_KEY = "webui:mode";

export default function App() {
  const [mode, setMode] = useState<Mode>(() => {
    try {
      return localStorage.getItem(MODE_KEY) === "developer" ? "developer" : "chat";
    } catch {
      return "chat";
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      /* ignore */
    }
  }, [mode]);

  return (
    <div className="flex h-screen min-h-0 flex-col bg-slate-50 text-slate-900">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
        <div className="flex items-center gap-2.5">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-slate-800 text-[11px] font-bold text-white">
            保
          </span>
          <h1 className="text-[15px] font-semibold tracking-tight">Insurance Agent</h1>
          <span className="hidden text-[11px] text-slate-400 sm:inline">
            chat-first agent system · 同一 Runtime，两种视图
          </span>
        </div>
        {mode === "chat" ? null : (
          <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-white">
            Developer Mode
          </span>
        )}
      </header>

      <div className="min-h-0 flex-1">
        {mode === "chat" ? (
          <ChatLayout onOpenDeveloperMode={() => setMode("developer")} />
        ) : (
          <DeveloperMode onBack={() => setMode("chat")} />
        )}
      </div>
    </div>
  );
}
