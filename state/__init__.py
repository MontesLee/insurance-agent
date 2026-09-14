"""CaseState layer (V2 Phase 7).

The state layer gives the 8-skill pipeline a spine: one client case == one CaseState that
holds every canonical artifact and the status of every stage.

    CaseState
      ├── stage_order      canonical, monotonic stage order (from workflow/)
      ├── stages           per-stage status (PENDING/RUNNING/COMPLETED/NEEDS_REVIEW/FAILED/SKIPPED)
      ├── artifacts        canonical artifacts keyed by artifact_type (the pipeline's data)
      ├── services         non-linear shared services (knowledge-search Evidence Provider)
      └── events           append-only log

Hard rules (see state/transitions.py):
  * monotonic    -- no stage runs before its predecessors complete; no backflow
  * precondition -- a stage runs only when every artifact it consumes is present
  * immutable    -- a COMPLETED stage's artifact is frozen (fingerprint-enforced)

The state layer contains NO insurance judgment. It stores and orders; it never decides.
"""
from . import case_state, store, transitions
from .case_state import (
    get_artifact,
    new_case_state,
    put_artifact,
    record_event,
    set_status,
    statuses,
    validate,
    verified,
)

__all__ = [
    "case_state",
    "store",
    "transitions",
    "new_case_state",
    "record_event",
    "set_status",
    "put_artifact",
    "get_artifact",
    "verified",
    "statuses",
    "validate",
]
