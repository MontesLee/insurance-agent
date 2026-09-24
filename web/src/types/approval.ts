/**
 * Approval record — VERBATIM projection of the backend
 * ApprovalRequest dict (runtime/approval/models.py create_request).
 * The UI must not invent, rename, or derive business states:
 * status vocabulary comes from the backend transition table
 * (PENDING / WAITING_HUMAN / APPROVED / REJECTED / EXPIRED / RESUMED).
 */
export interface ApprovalRecord {
  approval_id: string;
  project_id: string;
  task_id: string;
  graph_revision: number | null;
  request_type: string;
  reason: string;
  context: Record<string, unknown> | null;
  options: string[];
  default_action: string | null;
  status: string;
  requested_by: string;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  decision: string | null;
}

export interface ApprovalsResponse {
  project_id: string;
  approvals: ApprovalRecord[];
}

export interface ApprovalDetailResponse {
  project_id: string;
  approval: ApprovalRecord;
}

/**
 * Supervisor state — verbatim projection of
 * runtime/control/models.make_supervisor_state (+ monitor updates).
 */
export interface SupervisorState {
  project_id: string;
  status: string;
  risk_level: string;
  active_alerts: unknown[];
  pending_interventions: unknown[];
  last_event_id: string | null;
  last_checkpoint_id: string | null;
  updated_at: string;
}
