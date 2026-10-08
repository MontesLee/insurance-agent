/**
 * CONSUMER SHELL — the product surface for ordinary insurance clients
 * (Phase 28.E-1; identity boundary 28.G). Chat-first and deliberately
 * free of internal entries: no operator/developer navigation, no runtime
 * inspector, no demo-mode toggle. Internal surfaces live behind their own
 * routes (see app/route.ts) and are intentionally NOT linked from here.
 *
 * 28.G: the shell resolves the consumer identity once (whoami); in keys
 * mode an unauthenticated visitor meets the identity gate, and switching
 * identity never shows another subject's local transcripts.
 */
import { ChatLayout } from "../chat/ChatLayout";
import { IdentityGate, useConsumerIdentity } from "./IdentityGate";
import { RefReport } from "./RefReport";

export function ConsumerShell({ reportRef }: { reportRef?: string }) {
  const { state, subject, signOut, refresh } = useConsumerIdentity();

  return (
    <div className="flex h-screen min-h-0 flex-col bg-slate-50 text-slate-900">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
        <div className="flex items-center gap-2.5">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-slate-800 text-[11px] font-bold text-white">
            保
          </span>
          <h1 className="text-[15px] font-semibold tracking-tight">保险顾问助手</h1>
          <span className="hidden text-[11px] text-slate-400 sm:inline">
            家庭保障问答 · 规划 · 产品咨询
          </span>
        </div>
        {subject ? (
          <button
            type="button"
            onClick={signOut}
            className="rounded-md border border-slate-200 px-2.5 py-1 text-[12px] font-medium text-slate-600 transition hover:bg-slate-50"
            data-testid="sign-out"
          >
            退出
          </button>
        ) : null}
      </header>
      <div className="min-h-0 flex-1">
        {state === "loading" ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-[13px] text-slate-400">加载中…</p>
          </div>
        ) : state === "gate" ? (
          <IdentityGate onIdentity={refresh} />
        ) : reportRef ? (
          <RefReport ref={reportRef} />
        ) : (
          <ChatLayout />
        )}
      </div>
    </div>
  );
}
