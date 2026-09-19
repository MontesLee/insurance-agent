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


def _data_key():
    """R-04 + P0.1: at-rest encryption key (env/keyfile). In
    CONTROLLED_PILOT/PRODUCTION a key is MANDATORY — missing or invalid
    keys BLOCK the write (never a silent plaintext fallback). In
    DEMO/EVALUATION modes None = the documented plaintext mode."""
    from runtime import mode as _rt_mode
    from runtime.state.dataprotection import load_data_key
    key = load_data_key()
    if key is None and _rt_mode.encryption_required():
        raise RuntimeError(
            "ENCRYPTION_REQUIRED: %s mode requires "
            "INSURANCE_AGENT_DATA_KEY or INSURANCE_AGENT_KEYFILE — "
            "refusing to write client data in plaintext" % _rt_mode.mode())
    return key


def save(state: dict, root: str) -> str:
    """Write case_state.json + one file per artifact. Returns the case dir.

    Phase 13 R-04: when INSURANCE_AGENT_DATA_KEY / INSURANCE_AGENT_KEYFILE
    is configured, client data is Fernet-encrypted at rest (atomic write);
    backups then carry ciphertext only."""
    from runtime.state.dataprotection import write_protected
    key = _data_key()
    d = case_dir(root, state["case_id"])
    art_dir = os.path.join(d, "artifacts")
    os.makedirs(art_dir, exist_ok=True)
    write_protected(os.path.join(d, "case_state.json"), cs.to_json(state), key)
    for art_type, art in state.get("artifacts", {}).items():
        safe = art_type.replace("/", "_")
        write_protected(os.path.join(art_dir, safe + ".json"),
                        json.dumps(art, ensure_ascii=False, indent=2), key)
    return d


def load(root: str, case_id: str) -> Optional[dict]:
    from runtime.state.dataprotection import read_protected
    p = os.path.join(case_dir(root, case_id), "case_state.json")
    if not os.path.exists(p):
        return None
    text = read_protected(p, _data_key())
    return json.loads(text) if text is not None else None


def load_artifact(root: str, case_id: str, artifact_type: str) -> Optional[dict]:
    p = os.path.join(case_dir(root, case_id), "artifacts", artifact_type.replace("/", "_") + ".json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)
