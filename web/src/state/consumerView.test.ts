/**
 * ConsumerView — the allowlist boundary (28.E-2).
 *
 * A: allowlist (internal fields can never pass through)
 * E/F: Completion ≠ Artifact gating
 */
import { describe, expect, it } from "vitest";
import {
  ASSISTANT_NAME,
  consumerFallbackText,
  consumerFinalizeArtifact,
  consumerStageLabel,
  consumerTerminalHeader,
  consumerTerminalView,
  hasRealArtifact,
  REPORT_ARTIFACT_TYPE,
  toArtifactView,
} from "./consumerView";
import { initRunState, runReducer } from "./runReducer";
import type { RuntimeEvent } from "../types/runtime";

const ORDER = [
  { id: "client-intake", skill: "client-intake", produces: "client-profile" },
  { id: "report-generation", skill: "report-generation", produces: "insurance-report" },
];

function ev(type: string, stage: string | null, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: `evt_${Math.random().toString(36).slice(2, 8)}`, run_id: "run_v",
    timestamp: "2026-09-26T00:00:00Z", event_type: type as RuntimeEvent["event_type"],
    stage, skill: null, status: null, case_id: "case_v", artifact_id: null, eval_id: null,
    repair_attempt: null, message: null, data: {}, ...extra,
  };
}

function build(events: RuntimeEvent[]) {
  let s = initRunState("run_v", ORDER);
  return runReducer(s, { type: "events", events })!;
}

describe("toArtifactView (allowlist)", () => {
  it("known type → consumer title/cta; NO internal fields anywhere", () => {
    const v = toArtifactView("insurance-report");
    expect(v).toEqual({ title: "客户保险需求分析报告", cta: "查看完整报告" });
    expect(JSON.stringify(v)).not.toMatch(/run_|case_|artifact_id|eval_|approval_|trace_/);
  });

  it("unknown or internal types → NULL (never rendered)", () => {
    expect(toArtifactView("knowledge-evidence")).toBeNull();
    expect(toArtifactView("client-profile")).toBeNull();
    expect(toArtifactView("some-future-type")).toBeNull();
    expect(toArtifactView(null)).toBeNull();
    expect(toArtifactView("")).toBeNull();
  });
});

describe("Completion ≠ Artifact (the P0 fix)", () => {
  it("E: completed WITHOUT a real report artifact → NO artifact (QA turn)", () => {
    const s = build([
      ev("run_started", null),
      ev("intent_classified", null),
      ev("qa_answered", null, { data: { grounding_status: "refused" } }),
      ev("run_completed", null, { status: "completed" }),
    ]);
    expect(hasRealArtifact(s)).toBe(false);
    expect(consumerFinalizeArtifact(s)).toBeNull();
  });

  it("F: completed WITH a real report artifact → artifact view (no ids)", () => {
    const s = build([
      ev("run_started", null),
      ev("stage_completed", "report-generation"),
      ev("artifact_created", "report-generation"),
      ev("run_completed", null, { status: "completed" }),
    ]);
    expect(hasRealArtifact(s)).toBe(true);
    const a = consumerFinalizeArtifact(s);
    expect(a?.artifactType).toBe(REPORT_ARTIFACT_TYPE);
    expect(a?.title).toBe("客户保险需求分析报告");
  });

  it("artifact event WITHOUT completed status → still no artifact", () => {
    const s = build([
      ev("run_started", null),
      ev("artifact_created", "report-generation"),
    ]);
    expect(hasRealArtifact(s)).toBe(false);
  });

  it("non-report artifacts never qualify", () => {
    const s = build([
      ev("run_started", null),
      ev("artifact_created", "client-intake"),
      ev("run_completed", null, { status: "completed" }),
    ]);
    expect(hasRealArtifact(s)).toBe(false);
  });
});

describe("stage labels & terminal headers (no raw internals)", () => {
  it("known stages map to Chinese; unknown → generic, never raw ids", () => {
    expect(consumerStageLabel("client-intake")).toBe("客户建档");
    expect(consumerStageLabel("unknown-internal-id")).toBe("处理中");
  });

  it("terminal headers are consumer wording (no internal status codes)", () => {
    expect(consumerTerminalHeader("running", false)).toBe("正在处理你的请求");
    expect(consumerTerminalHeader("completed", false)).toBe("已完成");
    expect(consumerTerminalHeader("needs_review", false)).toBe("需要进一步核实");
    expect(consumerTerminalHeader("waiting", false)).toBe("需要你补充信息");
    expect(consumerTerminalHeader("failed", false)).toBe("这次没有完成");
  });

  it("fallback texts are conservative (no facts, no reasons, no internals)", () => {
    expect(consumerFallbackText("refusal")).not.toMatch(/QA_REFUSED|run_|引用校验失败原因/);
    expect(consumerFallbackText("error")).not.toMatch(/HTTP|trace|provider|model|stack/);
  });

  it("assistant identity is presentation-level", () => {
    expect(ASSISTANT_NAME).toBe("保险顾问助手");
  });
});

describe("consumerTerminalView — deterministic terminal presentation (28.E-5)", () => {
  it("E5-T1: success — reply text shown, artifact only when real", () => {
    expect(consumerTerminalView("completed", null, "重疾险等待期通常为……", true))
      .toEqual({ state: "answer", message: "重疾险等待期通常为……", artifact: true });
    expect(consumerTerminalView("completed", null, "重疾险等待期通常为……", false))
      .toEqual({ state: "answer", message: "重疾险等待期通常为……", artifact: false });
    // empty reply → honest fallback, never a fabricated success body
    expect(consumerTerminalView("completed", null, "  ", false).message).toBe("（本轮无回复）");
  });

  it("E5-T2: clarification — server questions kept, fallback when absent", () => {
    expect(consumerTerminalView("waiting", null, "孩子今年几岁？", false))
      .toEqual({ state: "clarification", message: "孩子今年几岁？", artifact: false });
    expect(consumerTerminalView("waiting", null, null, false).message)
      .toContain("需要你补充一些信息");
  });

  it("E5-T3: refusal — honest copy, NEVER a report/success, artifact forced off", () => {
    const v = consumerTerminalView("completed", "QA_REFUSED", "本次回答未能通过引用校验，先不作答。", true);
    expect(v.state).toBe("refusal");
    expect(v.message).toBe("本次回答未能通过引用校验，先不作答。");
    expect(v.artifact).toBe(false); // poisoned hasArtifact cannot fabricate a card
    expect(consumerTerminalView("completed", "QA_REFUSED", "", false).message)
      .toBe(consumerFallbackText("refusal"));
  });

  it("E5-T4: needs review — consumer copy, no approval/review internals", () => {
    const v = consumerTerminalView("needs_review", null, null, false);
    expect(v.state).toBe("needs_review");
    expect(v.message).toContain("人工核实");
    expect(v.message).not.toMatch(/approval|review_id|HITL|HOTL|eval/);
  });

  it("K.1 (P2-①): needs_review is a SYSTEM state — server template text is mapped away, never passed through", () => {
    // Case A: the exact 28.K pilot leak as replyText
    const a = consumerTerminalView(
      "needs_review", null,
      "这一步没有通过系统的质量校验。\n\nproduct_candidate_provider did not pass evaluation after repair — needs human review",
      false);
    expect(a.state).toBe("needs_review");
    expect(a.message).toContain("人工核实");
    // Case B: any unknown internal stage
    const b = consumerTerminalView(
      "needs_review", null,
      "unknown_internal_stage did not pass evaluation after repair — needs human review",
      false);
    for (const bad of ["product_candidate_provider", "unknown_internal_stage",
                       "did not pass", "provider", "human review", "stage", "_"]) {
      expect(a.message.includes(bad), `needs_review copy must not contain ${bad}`).toBe(false);
      expect(b.message.includes(bad), `needs_review copy must not contain ${bad}`).toBe(false);
    }
    // business answers (answer/refusal/clarification) still show server text
    expect(consumerTerminalView("completed", null, "回答正文", true).message).toBe("回答正文");
    expect(consumerTerminalView("completed", "QA_REFUSED", "拒答正文", false).message).toBe("拒答正文");
    expect(consumerTerminalView("waiting", null, "澄清正文", false).message).toBe("澄清正文");
  });

  it("E5-T5: system error — conservative copy, no internals", () => {
    const v = consumerTerminalView("failed", null, null, false);
    expect(v.state).toBe("error");
    expect(v.message).toBe(consumerFallbackText("error"));
    expect(v.message).not.toMatch(/httpx|timeout|stack|provider|model|runtime|500/);
  });

  it("E5-T6: terminal precedence — no contradictory states (poisoned inputs)", () => {
    // failed dominates everything, artifact impossible
    expect(consumerTerminalView("failed", null, "x", true))
      .toMatchObject({ state: "error", artifact: false });
    // waiting never completes / artifacts
    expect(consumerTerminalView("waiting", null, "x", true))
      .toMatchObject({ state: "clarification", artifact: false });
    // needs_review never success
    expect(consumerTerminalView("needs_review", null, "x", true))
      .toMatchObject({ state: "needs_review", artifact: false });
    // refused completed turn never carries an artifact
    expect(consumerTerminalView("completed", "QA_REFUSED", "x", true))
      .toMatchObject({ state: "refusal", artifact: false });
  });

  it("E5-T8/T9/T10: outputs never contain internal status codes or ids", () => {
    const blob = JSON.stringify([
      consumerTerminalView("completed", "QA_REFUSED", null, false),
      consumerTerminalView("waiting", "WAITING_USER", null, false),
      consumerTerminalView("needs_review", null, null, false),
      consumerTerminalView("failed", "INTERNAL_ERROR", null, false),
      consumerTerminalView("completed", null, null, true),
    ]);
    for (const bad of ["QA_REFUSED", "WAITING_USER", "INTERNAL_ERROR", "run_", "case_", "trace"]) {
      expect(blob.includes(bad), `terminal view must not contain ${bad}`).toBe(false);
    }
  });
});
