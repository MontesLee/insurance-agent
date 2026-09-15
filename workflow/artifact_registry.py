"""Artifact Registry (Step 3).

The registry is *metadata + lineage*, never a second copy of the content (spec §9): content stays
in `state["artifacts"]` (and on disk at `content_ref`). Each record answers: who produced it, from
which inputs, is it still the bytes that were produced, and which evidence does it lean on.

Lineage (`lineage()`) walks `input_artifacts` back to the client facts, which is what lets us
answer "where did this report recommendation come from?" without re-running anything.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from state import case_state as cs  # noqa: E402
from state import transitions  # noqa: E402


def _next_id(state: dict) -> str:
    n = len(state.get("artifact_registry", {})) + 1
    return "ART-%03d" % n


def _payload_of(artifact: Any) -> Any:
    if isinstance(artifact, dict) and isinstance(artifact.get("payload"), dict):
        return artifact["payload"]
    return artifact


def _collect_evidence_refs(node: Any, found: set) -> None:
    """Recursively collect string ids declared under `evidence_refs` / `related_artifact_ids`."""
    if isinstance(node, dict):
        for key in ("evidence_refs", "related_artifact_ids"):
            v = node.get(key)
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, str) and x:
                        found.add(x)
        for v in node.values():
            _collect_evidence_refs(v, found)
    elif isinstance(node, list):
        for v in node:
            _collect_evidence_refs(v, found)


def register(state: dict, artifact_type: str, artifact: dict, stage: dict,
             content_ref: Optional[str] = None) -> dict:
    """Register a produced artifact. Idempotent per artifact_type (re-register replaces)."""
    reg = state.setdefault("artifact_registry", {})
    existing = reg.get(artifact_type)
    artifact_id = existing["artifact_id"] if existing else _next_id(state)

    # inputs = the stage's declared consumes (required + optional) that are already registered.
    # Optional inputs are real lineage edges when present — omitting them would break the
    # Report -> ... -> Gap trace, since report-generation consumes most artifacts optionally.
    inputs = []
    declared = list(stage.get("consumes", []) or []) + list(stage.get("optional_consumes", []) or [])
    for dep in declared:
        if dep in reg and reg[dep]["artifact_id"] not in inputs:
            inputs.append(reg[dep]["artifact_id"])

    found: set = set()
    _collect_evidence_refs(_payload_of(artifact), found)

    rec = {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "producer_skill": stage.get("skill"),
        "producer_stage": stage.get("id"),
        "input_artifacts": inputs,
        "status": "VALID",
        "created_at": cs.now(),
        "content_ref": content_ref or ("artifacts/%s.json" % artifact_type),
        "fingerprint": transitions.fingerprint(artifact),
        "evidence_refs": sorted(found),
    }
    reg[artifact_type] = rec
    return rec


def by_type(state: dict, artifact_type: str) -> Optional[dict]:
    return state.get("artifact_registry", {}).get(artifact_type)


def by_id(state: dict, artifact_id: str) -> Optional[dict]:
    for rec in state.get("artifact_registry", {}).values():
        if rec["artifact_id"] == artifact_id:
            return rec
    return None


def type_of(state: dict, artifact_id: str) -> Optional[str]:
    rec = by_id(state, artifact_id)
    return rec["artifact_type"] if rec else None


def lineage(state: dict, artifact_type: str, _seen: Optional[set] = None) -> list:
    """Artifact ids from the roots down to `artifact_type` (depth-first, de-duplicated)."""
    _seen = _seen or set()
    rec = by_type(state, artifact_type)
    if rec is None or rec["artifact_id"] in _seen:
        return []
    _seen.add(rec["artifact_id"])
    out = []
    for dep_id in rec["input_artifacts"]:
        dep_type = type_of(state, dep_id)
        if dep_type:
            out.extend(lineage(state, dep_type, _seen))
    out.append(rec["artifact_id"])
    return out


def lineage_types(state: dict, artifact_type: str) -> list:
    ids = lineage(state, artifact_type)
    return [type_of(state, i) for i in ids if type_of(state, i)]


def verify(state: dict) -> tuple:
    """Invariant helper: every registered artifact must still match its fingerprint.

    Returns (ok, problems). This is what turns a silent checkpoint corruption into a loud
    `CHECKPOINT_INVALID` instead of resuming from a mutated artifact.
    """
    problems = []
    for art_type, rec in state.get("artifact_registry", {}).items():
        art = state.get("artifacts", {}).get(art_type)
        if art is None:
            problems.append("%s: registered but missing from state.artifacts" % art_type)
            continue
        if transitions.fingerprint(art) != rec.get("fingerprint"):
            problems.append("%s: fingerprint mismatch (artifact mutated after registration)"
                            % art_type)
        for dep_id in rec.get("input_artifacts", []):
            if by_id(state, dep_id) is None:
                problems.append("%s: unknown input artifact id %s" % (art_type, dep_id))
    return (len(problems) == 0), problems


def ids(state: dict) -> list:
    return [r["artifact_id"] for r in state.get("artifact_registry", {}).values()]
