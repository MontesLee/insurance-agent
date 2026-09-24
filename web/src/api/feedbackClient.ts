/**
 * Feedback client (Phase 27.7) — Human Feedback Capture MVP.
 *
 * GAP-27.7-01 (recorded, backend intentionally UNCHANGED): there
 * is no backend feedback API. Per the phase rules ("existing
 * persistence mechanism or file-based storage abstraction; no new
 * schema"), this first implementation persists to browser
 * localStorage behind a client interface, so a future backend
 * endpoint (POST/GET feedback) is a drop-in replacement.
 *
 * Limitations of local capture (accepted for the MVP validation
 * goal): single-browser, single-reviewer; not shared, not
 * server-audited. The Feedback Loop boundary (ADR-018) holds:
 * records are inert evidence — nothing consumes them at runtime.
 *
 * Entity = the v0.1 design model (docs/architecture/
 * human-feedback-loop-v0.1.md §7), category fixed-closed.
 */

/** Fixed first-level categories — closed set, no free input. */
export const FEEDBACK_CATEGORIES = [
  "REASONING",
  "MISSING_INFORMATION",
  "WRONG_RECOMMENDATION",
  "EVIDENCE_ISSUE",
  "KNOWLEDGE_GAP",
  "UX_ISSUE",
] as const;
export type FeedbackCategory = (typeof FEEDBACK_CATEGORIES)[number];

export const CATEGORY_LABELS: Record<FeedbackCategory, string> = {
  REASONING: "Reasoning Issue · 推理/分析错误",
  MISSING_INFORMATION: "Missing Information · 信息缺失处理不当",
  WRONG_RECOMMENDATION: "Wrong Recommendation · 推荐/产品错误",
  EVIDENCE_ISSUE: "Evidence Issue · 证据问题",
  KNOWLEDGE_GAP: "Knowledge Gap · 知识缺口",
  UX_ISSUE: "UX Issue · 报告/呈现问题",
};

export interface FeedbackRecord {
  id: string;
  decision_id: string; // approval_id + decision (anchor)
  approval_id: string;
  category: FeedbackCategory;
  description: string;
  evidence_refs: string[]; // free-form references, optional
  expected_behavior?: string; // optional per design model
  status: "captured"; // lifecycle starts at captured
  created_by: string; // "local" — no identity API (GAP-27.5-4)
  created_at: string; // ISO
  provenance: "governance-ui";
}

const STORE_KEY = "webui:feedback:v1";

interface FeedbackStore {
  createFeedback(input: {
    approval_id: string;
    decision: string;
    category: FeedbackCategory;
    description: string;
    evidence_refs: string[];
    expected_behavior?: string;
  }): Promise<FeedbackRecord>;
  listFeedback(approvalId: string): Promise<FeedbackRecord[]>;
}

/** Local (browser) implementation — swap for HTTP when the backend lands. */
class LocalFeedbackStore implements FeedbackStore {
  private read(): FeedbackRecord[] {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      return raw ? (JSON.parse(raw) as FeedbackRecord[]) : [];
    } catch {
      return [];
    }
  }
  private write(records: FeedbackRecord[]): void {
    localStorage.setItem(STORE_KEY, JSON.stringify(records));
  }
  async createFeedback(input: {
    approval_id: string;
    decision: string;
    category: FeedbackCategory;
    description: string;
    evidence_refs: string[];
    expected_behavior?: string;
  }): Promise<FeedbackRecord> {
    const rec: FeedbackRecord = {
      id: `fb_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      decision_id: `${input.approval_id}#${input.decision}`,
      approval_id: input.approval_id,
      category: input.category,
      description: input.description,
      evidence_refs: input.evidence_refs,
      expected_behavior: input.expected_behavior || undefined,
      status: "captured",
      created_by: "local",
      created_at: new Date().toISOString(),
      provenance: "governance-ui",
    };
    this.write([...this.read(), rec]);
    return rec;
  }
  async listFeedback(approvalId: string): Promise<FeedbackRecord[]> {
    return this.read()
      .filter((r) => r.approval_id === approvalId)
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  }
}

export const feedbackClient: FeedbackStore = new LocalFeedbackStore();
