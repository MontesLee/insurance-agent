/**
 * The RuntimeEvent contract — the single most important front/back contract.
 * Mirrors runtime/events.py RuntimeEvent.to_dict() field-for-field.
 * No `any`: unknown extras collapse into `data`.
 */
export interface RuntimeEvent {
  event_id: string;
  run_id: string;
  timestamp: string;
  event_type: EventType;
  stage: string | null;
  skill: string | null;
  status: string | null;
  case_id: string | null;
  artifact_id: string | null;
  eval_id: string | null;
  repair_attempt: number | null;
  message: string | null;
  data: Record<string, unknown>;
}

export type EventType =
  // Phase 28.B prep — the union is the FULL dual-end contract: it equals
  // schema/event-vocabulary.json "vocabulary" (== runtime/events.py
  // EVENT_TYPES, asserted by tests/contract/test_event_vocabulary.py)
  // plus "reserved" (contract-first: grounding phases are embedded in
  // qa_answered today; standalone emission lands under a runtime-
  // authorized phase). Sync is asserted by web/src/types/runtime.test.ts.
  | "agent_assigned"
  | "agent_completed"
  | "agent_decision"
  | "agent_failed"
  | "agent_message_acknowledged"
  | "agent_message_failed"
  | "agent_message_received"
  | "agent_message_sent"
  | "agent_output_validated"
  | "agent_started"
  | "agent_step_error"
  | "agent_step_started"
  | "agent_stream_delta"
  | "agent_tool_call"
  | "agent_tool_completed"
  | "agent_validation_failed"
  | "approval_approved"
  | "approval_expired"
  | "approval_failed"
  | "approval_rejected"
  | "approval_requested"
  | "approval_resumed"
  | "approval_waiting"
  | "artifact_created"
  | "checkpoint_created"
  | "checkpoint_resumed"
  | "eval_failed"
  | "eval_passed"
  | "eval_started"
  | "graph_validation_failed"
  | "graph_validation_passed"
  | "graph_validation_started"
  | "handoff_rejected"
  | "handoff_validated"
  | "intent_classified"
  | "planner_completed"
  | "planner_failed"
  | "planner_started"
  | "qa_answered"
  | "repair_completed"
  | "repair_exhausted"
  | "repair_started"
  | "run_completed"
  | "run_failed"
  | "run_started"
  | "stage_completed"
  | "stage_failed"
  | "stage_started"
  | "task_activated"
  | "tool_completed"
  | "tool_failed"
  | "tool_started"
  // contract-reserved (no backend emission yet)
  | "grounding_started"
  | "grounding_completed"
;

export const RUN_TERMINAL_EVENT_TYPES: ReadonlySet<EventType> = new Set([
  "run_completed",
  "run_failed",
] as EventType[]);

/** Run metadata from GET /api/runs/{run_id} — authoritative status, never inferred. */
export type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "needs_review"
  | "waiting";

export interface StageInfo {
  id: string;
  skill: string | null;
  produces: string | null;
}

export interface Run {
  run_id: string;
  case_id: string;
  status: RunStatus;
  started_at: string | null;
  completed_at: string | null;
  current_stage: string | null;
  event_count: number;
  result_status: string | null;
  reasons: string[];
  stage_order: StageInfo[];
}

export interface CaseInfo {
  id: string;
  category: string | null;
  desc: string | null;
  kb: string | null;
}

export interface ArtifactSummary {
  artifact_id: string;
  artifact_type: string;
  producer_stage: string | null;
  producer_skill: string | null;
  created_at: string | null;
  status: string | null;
  input_artifacts: string[];
  evidence_refs: string[];
  lineage: { artifact_id: string; artifact_type: string | null }[];
}

export interface ArtifactDetail extends ArtifactSummary {
  artifact: unknown;
}

export interface EventsResponse {
  run_id: string;
  count: number;
  events: RuntimeEvent[];
}

/** POST /api/runs conflict body (HTTP 409). */
export interface CaseAlreadyRunning {
  error: "case_already_running";
  run_id: string;
  case_id: string;
}
