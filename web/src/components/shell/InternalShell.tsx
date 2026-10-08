/**
 * INTERNAL SHELL — operator & developer surfaces behind their own
 * routes (Phase 28.E-1). Everything internal stays here: review /
 * approval / feedback (Operator) and dashboard / runtime console
 * (Developer). Nothing internal is removed or altered — only moved
 * behind the internal navigation boundary.
 *
 * Access policy (auth/roles) is deliberately UNCHANGED:
 * AUTH POLICY = DEFERRED OWNER DECISION (E-0 audit §12). This shell is
 * a navigation boundary, not a security boundary.
 */
import { useState } from "react";
import { navigate, ROUTES, type Route } from "../../app/route";
import { ReviewQueue } from "../review/ReviewQueue";
import { ApprovalDetail } from "../review/ApprovalDetail";
import { ReviewWorkspace } from "../review/ReviewWorkspace";
import { PilotDashboard } from "../dashboard/PilotDashboard";
import { DeveloperMode } from "../developer/DeveloperMode";

export function InternalShell({ route }: { route: Route }) {
  // Operator sub-navigation (queue → approval detail → workspace) keeps
  // its in-view state, exactly as the pre-E-1 review console did.
  const [approvalId, setApprovalId] = useState<string | null>(null);
  const [workspaceTarget, setWorkspaceTarget] = useState<{
    projectId: string;
    approvalId: string;
  } | null>(null);

  const isOperator = route.space === "operator";
  const isDashboard = route.space === "developer" && route.view === "dashboard";

  const navBtn = (path: string, label: string, active: boolean, testId: string) => (
    <button
      type="button"
      data-testid={testId}
      onClick={() => {
        if (path !== ROUTES.operatorReview) {
          // switching away from the operator view drops its sub-state
          setApprovalId(null);
          setWorkspaceTarget(null);
        }
        navigate(path);
      }}
      className={`rounded-md px-2.5 py-1 text-[12px] font-medium transition ${
        active
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
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-slate-700 text-[10px] font-bold text-white">
            INT
          </span>
          <h1 className="text-[15px] font-semibold tracking-tight">Insurance Agent 内部工作台</h1>
          <span className="hidden text-[11px] text-slate-400 sm:inline">
            Operator / Developer · 非消费者面
          </span>
        </div>
        <nav className="flex items-center gap-1.5" aria-label="internal">
          {navBtn(ROUTES.operatorReview, "审核队列", isOperator, "nav-internal-review")}
          {navBtn(ROUTES.developerDashboard, "Dashboard", isDashboard, "nav-internal-dashboard")}
          {navBtn(
            ROUTES.developerConsole,
            "运行控制台",
            route.space === "developer" && route.view === "console",
            "nav-internal-console",
          )}
          <a
            href={`#${ROUTES.consumerChat}`}
            data-testid="nav-back-consumer"
            className="ml-2 rounded-md border border-slate-200 px-2.5 py-1 text-[12px] font-medium text-slate-600 transition hover:bg-slate-50"
          >
            ← 返回对话
          </a>
        </nav>
      </header>

      <div className="min-h-0 flex-1">
        {isOperator ? (
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
        ) : isDashboard ? (
          <PilotDashboard
            onOpenQueue={() => {
              setApprovalId(null);
              setWorkspaceTarget(null);
              navigate(ROUTES.operatorReview);
            }}
          />
        ) : (
          <DeveloperMode onBack={() => navigate(ROUTES.developerDashboard)} />
        )}
      </div>
    </div>
  );
}
