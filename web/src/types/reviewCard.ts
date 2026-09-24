/**
 * Review Card — VERBATIM projection of the backend card produced by
 * evaluation/human-review/review_card_generator.py (schema:
 * evaluation/human-review/review-card.schema.json). The UI must not
 * re-derive level/flags/validation: it renders the card verbatim.
 */
export type ReviewLevel = "AUTO_PASS" | "SUMMARY_REVIEW" | "DEEP_REVIEW";
export type CheckStatus = "PASS" | "FAIL";
export type FlagSeverity = "HIGH" | "MEDIUM" | "LOW";

export interface ReviewRiskFlag {
  type: string;
  severity: FlagSeverity;
  message: string;
  evidence_ref: string | null;
}

export interface ReviewCard {
  schema_version: string;
  card_id: string;
  case_id: string;
  run_id: string;
  generated_at: string;
  generator?: string;
  source?: {
    state_path: string | null;
    trace_path: string | null;
    state_persisted: boolean;
  };
  customer_summary: {
    age?: string | null;
    gender?: string | null;
    marital_status?: string | null;
    children?: string | null;
    housing?: string | null;
    occupation?: string | null;
    annual_income?: string | null;
    annual_expense?: string | null;
    mortgage?: string | null;
    insurance_budget?: string | null;
    social_security?: string | null;
    existing_insurance?: string | null;
    unresolved?: string[];
  };
  agent_summary: {
    case_status: string;
    objective: string[];
    recommendation_status: string | null;
    primary: {
      candidate_id: string;
      product_id: string | null;
      product_name: string | null;
    } | null;
    recommendation: string[];
    risk_highlights: {
      risk_id: string;
      risk_name: string | null;
      severity: string | null;
      residual_risk: string | null;
      unprotected_amount: number | string | null;
    }[];
    waiting_for_user: Record<string, unknown> | null;
  };
  automatic_validation: {
    schema_check: CheckStatus;
    trace_check: CheckStatus;
    evidence_check: CheckStatus;
    logic_check: CheckStatus;
    eval_summary: {
      total: number;
      passed: number;
      failed: number;
      failed_eval_ids: string[];
    };
    failed_checks: {
      eval_id: string | null;
      artifact_type: string | null;
      check_id: string;
      message: string;
    }[];
  };
  risk_flags: ReviewRiskFlag[];
  review_action: {
    required: boolean;
    level: ReviewLevel;
    reasons: string[];
  };
  validation_status: "PASS" | "FAIL";
  sampling: { rate: number; triggered: boolean; seed: string };
}
