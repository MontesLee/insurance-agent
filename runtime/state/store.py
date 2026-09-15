"""File-backed CaseState persistence (Phase 7).

One case == one directory:

    <root>/<case_id>/
        case_state.json      the CaseState (state/ only)
        artifacts/<type>.json   the canonical artifacts (inspectable on their own)

Persisting artifacts separately keeps them readable/diffable without loading the whole
state, and gives a place for the human review gate to inspect exactly what was produced.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from . import case_state as cs


def case_dir(root: str, case_id: str) -> str:
    return os.path.join(root, case_id)


def save(state: dict, root: str) -> str:
    """Write case_state.json + one file per artifact. Returns the case dir."""
    d = case_dir(root, state["case_id"])
    art_dir = os.path.join(d, "artifacts")
    os.makedirs(art_dir, exist_ok=True)
    with open(os.path.join(d, "case_state.json"), "w", encoding="utf-8") as f:
        f.write(cs.to_json(state))
    for art_type, art in state.get("artifacts", {}).items():
        safe = art_type.replace("/", "_")
        with open(os.path.join(art_dir, safe + ".json"), "w", encoding="utf-8") as f:
            json.dump(art, f, ensure_ascii=False, indent=2)
    return d


def load(root: str, case_id: str) -> Optional[dict]:
    p = os.path.join(case_dir(root, case_id), "case_state.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_artifact(root: str, case_id: str, artifact_type: str) -> Optional[dict]:
    p = os.path.join(case_dir(root, case_id), "artifacts", artifact_type.replace("/", "_") + ".json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)
