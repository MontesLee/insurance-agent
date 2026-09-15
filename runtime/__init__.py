"""Workflow layer (V2 Phase 7).

`runtime/insurance-analysis.yaml` declares the pipeline (single source of truth for stage
order, inputs, outputs, gates). `runtime/orchestrator.py` executes it against a CaseState.

The workflow layer moves artifacts and enforces order; it contains no insurance judgment.
"""
from .orchestrator import (
    approve,
    build_stage_input,
    load_workflow,
    run,
    seed_case,
    validate_artifact,
)

__all__ = [
    "load_workflow",
    "seed_case",
    "run",
    "approve",
    "build_stage_input",
    "validate_artifact",
]
