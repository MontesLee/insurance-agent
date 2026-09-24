/**
 * Feedback Panel (Phase 27.7) — Human Feedback Capture MVP.
 *
 * Section G of the Review Workspace, after the Decision Panel.
 * Anchored on the Decision (ADR-018 + design v0.1 Option A): the
 * capture form appears once the approval is decided; feedback is
 * optional, structured (closed category set + required
 * description), and stored as INERT EVIDENCE — nothing in the
 * runtime consumes it, submitting never touches approval/artifact/
 * skill state. Submission is submit → await store → re-read (no
 * optimistic update); failures keep the user's input.
 */
import { useCallback, useEffect, useState } from "react";
import {
  FEEDBACK_CATEGORIES,
  CATEGORY_LABELS,
  feedbackClient,
  type FeedbackCategory,
  type FeedbackRecord,
} from "../../api/feedbackClient";
import type { ApprovalRecord } from "../../types/approval";

const RESOLVED = new Set(["APPROVED", "REJECTED", "EXPIRED", "RESUMED"]);

type Phase =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "error"; message: string };

export function FeedbackPanel({ approval }: { approval: ApprovalRecord }) {
  const [category, setCategory] = useState<FeedbackCategory | null>(null);
  const [description, setDescription] = useState("");
  const [refsText, setRefsText] = useState("");
  const [expected, setExpected] = useState("");
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [records, setRecords] = useState<FeedbackRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const decided = RESOLVED.has(approval.status);
  const reload = useCallback(() => {
    setLoading(true);
    feedbackClient
      .listFeedback(approval.approval_id)
      .then((rs) => setRecords(rs))
      .finally(() => setLoading(false));
  }, [approval.approval_id]);

  useEffect(() => {
    reload();
  }, [reload]);

  const valid = category !== null && description.trim().length > 0;

  const submit = async () => {
    if (!valid || phase.kind === "submitting") return;
    setPhase({ kind: "submitting" });
    try {
      await feedbackClient.createFeedback({
        approval_id: approval.approval_id,
        decision: approval.decision ?? approval.status,
        category: category!,
        description: description.trim(),
        evidence_refs: refsText
          .split(/[\n,;]/)
          .map((s) => s.trim())
          .filter(Boolean),
        expected_behavior: expected.trim() || undefined,
      });
      setCategory(null);
      setDescription("");
      setRefsText("");
      setExpected("");
      setPhase({ kind: "idle" });
      reload(); // re-read the store — no optimistic update
    } catch (e) {
      setPhase({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  };

  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-4"
      data-testid="feedback-panel"
    >
      <div className="flex items-baseline gap-2">
        <h3 className="text-[13.5px] font-semibold tracking-tight text-slate-700">
          G · Human Feedback
        </h3>
        <span className="text-[11px] text-slate-400">
          决定后的结构化反馈(可选)—— 仅作为评估证据沉淀,不影响运行时
        </span>
      </div>

      {/* Existing feedback — verbatim, no summarization */}
      <div className="mt-2.5" data-testid="feedback-list">
        {loading ? (
          <p className="text-[12px] text-slate-400">Loading...</p>
        ) : records.length === 0 ? (
          <p data-testid="feedback-empty" className="text-[12px] text-slate-400">
            暂无反馈记录
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {records.map((r) => (
              <li
                key={r.id}
                data-testid={`feedback-record-${r.id}`}
                className="rounded-md border border-slate-100 bg-slate-50 p-2.5"
              >
                <div className="flex items-center gap-2 text-[11.5px]">
                  <span className="rounded bg-slate-200 px-1.5 py-0.5 font-mono font-semibold text-slate-600">
                    {r.category}
                  </span>
                  <span className="font-mono text-slate-400">{r.id}</span>
                  <span className="ml-auto text-slate-400">
                    {r.created_by} · {r.created_at.replace("T", " ").slice(0, 16)}
                  </span>
                </div>
                <p className="mt-1 text-[12.5px] text-slate-700">{r.description}</p>
                {r.evidence_refs.length > 0 ? (
                  <p className="mt-1 font-mono text-[11px] text-slate-500">
                    refs: {r.evidence_refs.join(", ")}
                  </p>
                ) : null}
                {r.expected_behavior ? (
                  <p className="mt-0.5 text-[11.5px] text-slate-500">
                    expected: {r.expected_behavior}
                  </p>
                ) : null}
                <p className="mt-0.5 font-mono text-[10.5px] text-slate-400">
                  anchor: {r.decision_id} · status: {r.status} · provenance: {r.provenance}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Capture form — anchored on a Decision */}
      {!decided ? (
        <p data-testid="feedback-gate" className="mt-3 text-[12px] text-slate-400">
          反馈锚定在决定上 —— 请先在 F 节完成 Approve / Reject。
        </p>
      ) : (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <p className="text-[12px] font-medium text-slate-500">Category(必选,固定分类)</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="feedback-categories">
            {FEEDBACK_CATEGORIES.map((c) => (
              <button
                key={c}
                data-testid={`feedback-cat-${c}`}
                onClick={() => setCategory(c)}
                className={`rounded-md border px-2.5 py-1 text-[11.5px] font-medium transition ${
                  category === c
                    ? "border-slate-800 bg-slate-800 text-white"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {CATEGORY_LABELS[c]}
              </button>
            ))}
          </div>

          <textarea
            data-testid="feedback-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Description(必填):为什么错/对,Agent 本应如何表现…"
            className="mt-2 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[12.5px] text-slate-700 outline-none focus:border-slate-400"
          />
          <input
            data-testid="feedback-refs"
            value={refsText}
            onChange={(e) => setRefsText(e.target.value)}
            placeholder="Evidence References(可选,逗号/换行分隔,如 REQ-MED, 01_medical_insurance_002)"
            className="mt-1.5 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] text-slate-700 outline-none focus:border-slate-400"
          />
          <input
            data-testid="feedback-expected"
            value={expected}
            onChange={(e) => setExpected(e.target.value)}
            placeholder="Expected behavior(可选):期望行为"
            className="mt-1.5 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] text-slate-700 outline-none focus:border-slate-400"
          />

          {phase.kind === "error" ? (
            <div className="mt-2 rounded-md border border-red-200 bg-red-50 p-2.5" data-testid="feedback-error">
              <p className="text-[12.5px] font-medium text-red-700">Failed to submit feedback</p>
              <p className="mt-0.5 font-mono text-[11.5px] text-red-500">{phase.message}</p>
              <button
                data-testid="feedback-retry"
                onClick={() => setPhase({ kind: "idle" })}
                className="mt-1.5 rounded border border-red-300 bg-white px-2.5 py-0.5 text-[11.5px] font-medium text-red-600 hover:bg-red-100"
              >
                Retry
              </button>
            </div>
          ) : null}

          <div className="mt-2.5 flex items-center gap-2">
            <button
              data-testid="feedback-submit"
              disabled={!valid || phase.kind === "submitting"}
              onClick={() => void submit()}
              title={!valid ? "Category 与 Description 必填" : undefined}
              className="rounded-md bg-slate-800 px-4 py-1.5 text-[12.5px] font-medium text-white hover:bg-slate-700 disabled:opacity-40"
            >
              Submit Feedback
            </button>
            {phase.kind === "submitting" ? (
              <span className="text-[12px] text-slate-400">提交中…</span>
            ) : (
              <span className="text-[11px] text-slate-400">
                存储为本机浏览器(localStorage)—— GAP-27.7-01:后端反馈端点待补
              </span>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
