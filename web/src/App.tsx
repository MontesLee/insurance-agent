import { useEffect, useState } from "react";
import { ChatLayout } from "./components/chat/ChatLayout";
import { DeveloperMode } from "./components/developer/DeveloperMode";
import { ReviewQueue } from "./components/review/ReviewQueue";
import { ApprovalDetail } from "./components/review/ApprovalDetail";
import { ReviewWorkspace } from "./components/review/ReviewWorkspace";
import { PilotDashboard } from "./components/dashboard/PilotDashboard";

/**
 * UX entries over ONE runtime:
 *   User Mode (default) — chat-first agent experience
 *   Review Queue        — Phase 27.5-2 reviewer entry (read-only
 *                         projection of the backend approval store)
 *   Developer Mode      — Phase 2 cases / runtime console
 * All consume backend API + SSE; none owns agent execution state.
 */
type Mode = "chat" | "review" | "dashboard" | "developer";
const MODE_KEY = "webui:mode";

export default function App() {
  const [mode, setMode] = useState<Mode>(() => {
    try {
      const m = localStorage.getItem(MODE_KEY);
      return m === "developer" || m === "review" || m === "dashboard" ? m : "chat";
    } catch {
      return "chat";
    }
  });
  const [approvalId, setApprovalId] = useState<string | null>(null);
  const [workspaceTarget, setWorkspaceTarget] = useState<{
    projectId: string;
    approvalId: string;
  } | null>(null);
  useEffect(() => {
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      /* ignore */
    }
  }, [mode]);

  const navBtn = (m: Mode, label: string) => (
    <button
      data-testid={`nav-${m}`}
      onClick={() => {
        if (m !== "review") {
          setApprovalId(null);
          setWorkspaceTarget(null);
        }
        setMode(m);
      }}
      className={`rounded-md px-2.5 py-1 text-[12px] font-medium transition ${
        mode === m
          ? "bg-slate-800 text-white"
          : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex h-screen min-h-0 flex-col bg-slate-50 text-slate-900">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
        <div className="flex items-center gap-2.5">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-slate-800 text-[11px] font-bold text-white">
            保
          </span>
          <h1 className="text-[15px] font-semibold tracking-tight">Insurance Agent</h1>
          <span className="hidden text-[11px] text-slate-400 sm:inline">
            chat-first agent system · 同一 Runtime，多视图
          </span>
        </div>
        <nav className="flex items-center gap-1.5" aria-label="primary">
          {mode === "chat" ? (
            <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">
              Chat
            </span>
          ) : null}
          {navBtn("chat", "对话")}
          {navBtn("review", "审核队列")}
          {navBtn("dashboard", "Dashboard")}
          {navBtn("developer", "Developer")}
        </nav>
      </header>

      <div className="min-h-0 flex-1">
        {mode === "chat" ? (
          <ChatLayout onOpenDeveloperMode={() => setMode("developer")} />
        ) : mode === "review" ? (
          workspaceTarget ? (
            <ReviewWorkspace
              projectId={workspaceTarget.projectId}
              approvalId={workspaceTarget.approvalId}
              onBack={() => {
                setWorkspaceTarget(null);
                setApprovalId(workspaceTarget.approvalId);
              }}
            />
          ) : approvalId ? (
            <ApprovalDetail
              approvalId={approvalId}
              onBack={() => setApprovalId(null)}
              onOpenWorkspace={(t) => setWorkspaceTarget(t)}
            />
          ) : (
            <ReviewQueue onOpenApproval={(id) => setApprovalId(id)} />
          )
        ) : mode === "dashboard" ? (
          <PilotDashboard
            onOpenQueue={() => {
              setWorkspaceTarget(null);
              setApprovalId(null);
              setMode("review");
            }}
          />
        ) : (
          <DeveloperMode onBack={() => setMode("chat")} />
        )}
      </div>
    </div>
  );
}
