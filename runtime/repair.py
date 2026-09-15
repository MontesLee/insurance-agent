"""Repair Loop (Step 3).

Repair rules (spec §20-23)
  * at most 2 repairs (max_attempts = 3 executions: initial + 2);
  * repair is LOCAL — only the failed stage re-runs, upstream is never rolled back;
  * repair knows WHY it failed: the failed checks are injected and select the action;
  * repair never edits a produced artifact (artifacts are frozen). It either patches the STAGE
    INPUT and re-runs, or discards a stale output and re-derives it from current upstream;
  * exhausted budget -> NEEDS_REVIEW, with the failure and the repair trail preserved.

Action catalogue comes from resources/config/repair.rules.json.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import eval_engine as ev

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "resources", "config", "repair.rules.json")


def load_rules(path: Optional[str] = None) -> dict:
    with open(path or RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _key(check_id: str) -> str:
    if "orphan_refs" in check_id:
        return "cross_artifact_orphan_refs"
    return check_id


def plan(failed_checks: list, eval_rules: dict) -> Optional[str]:
    """Choose the repair action for a set of failed checks. None = not repairable."""
    mapping = eval_rules.get("repairable", {}) or {}
    for fc in failed_checks:
        action = mapping.get(_key(fc["check_id"]))
        if action:
            return action
    return None


# --------------------------------------------------------------------------- #
# actions
# --------------------------------------------------------------------------- #
def _drop_invalid_products(state: dict, stage_input: dict, eval_rules: dict) -> tuple:
    """Remove candidates whose product_id is not in the catalog, from the stage input only."""
    catalog = {p.get("product_id") for p in ev.load_catalog(eval_rules)}
    changed = []
    for key, val in list(stage_input.items()):
        if not isinstance(val, dict):
            continue
        cands = val.get("candidates")
        if not isinstance(cands, list):
            continue
        kept, dropped = [], []
        for c in cands:
            if isinstance(c, dict) and c.get("product_id") in catalog:
                kept.append(c)
            else:
                dropped.append(c.get("product_id") or c.get("candidate_id"))
        if dropped:
            val = dict(val)
            val["candidates"] = kept
            adm = [c.get("candidate_id") for c in kept if c.get("admissible")]
            if "admissible_candidate_ids" in val:
                val["admissible_candidate_ids"] = adm
            stage_input[key] = val
            changed.extend(map(str, dropped))
    if not changed:
        return False, "no invalid candidates found in stage input"
    return True, "dropped invalid products: %s" % ", ".join(changed)


_ACTIONS = {
    "DROP_INVALID_PRODUCTS": _drop_invalid_products,
}


def apply(state: dict, stage_input: dict, action: str, eval_rules: dict) -> tuple:
    """Apply a repair action to a COPY of the stage input. Returns (changed, detail)."""
    if action in ("RERUN_FROM_UPSTREAM", "RERUN_STAGE"):
        # Nothing to patch: the stale output is discarded and the stage re-derives from the
        # current upstream artifacts. This is the honest repair for stale references.
        return True, "re-derive from current upstream artifacts"
    fn = _ACTIONS.get(action)
    if fn is None:
        return False, "unknown repair action: %s" % action
    return fn(state, stage_input, eval_rules)


def repairable_checks(failed_checks: list, eval_rules: dict) -> list:
    mapping = eval_rules.get("repairable", {}) or {}
    return [fc for fc in failed_checks if _key(fc["check_id"]) in mapping]
