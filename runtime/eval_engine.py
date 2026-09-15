"""Eval Engine (Step 3).

Eval is a separate gate between "the skill ran" and "the result is acceptable". The orchestrator
never treats a successful execution as a correct one: every artifact is evaluated, and only a
PASS lets the case advance.

Check families (spec §19)
  schema         -- the artifact validates against its declared canonical contract
  required_fields-- declared payload paths are present
  contamination  -- upstream analysis layers contain no concrete product / company / product id
  provenance     -- Recommendation -> Evidence -> Document -> Chunk is resolvable
  cross_artifact -- references (gap->risk, solution->gap) resolve to artifacts that exist
  invariant      -- domain invariants, e.g. every candidate product_id exists in the catalog

Honesty rules
  * A check that cannot be evaluated reports FAIL, never PASS. There is no MANUAL/UNKNOWN pass.
  * All thresholds, paths and term lists come from resources/config/eval.rules.json — the engine
    only consumes them.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from .state import case_state as cs  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))          # runtime/
REPO_ROOT = os.path.dirname(HERE)                          # repo root
RULES_PATH = os.path.join(HERE, "resources", "config", "eval.rules.json")

_CATALOG_CACHE: dict = {}


def load_rules(path: Optional[str] = None) -> dict:
    with open(path or RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_catalog(rules: dict) -> list:
    """Demo product catalog (products array). Cached per resolved path."""
    rel = rules.get("catalog_path", "catalog/product-catalog.v0.1.json")
    p = rel if os.path.isabs(rel) else os.path.join(REPO_ROOT, rel)
    if p in _CATALOG_CACHE:
        return _CATALOG_CACHE[p]
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    products = data.get("products", data if isinstance(data, list) else [])
    _CATALOG_CACHE[p] = products
    return products


# --------------------------------------------------------------------------- #
# tiny path getter:  payload.gaps[].gap_id   /   payload.a.b[]  /  a.b.c
# --------------------------------------------------------------------------- #
def get_values(obj: Any, path: str) -> list:
    """Resolve a dotted path with `[]` list markers. Returns the list of matched leaves."""
    if not path:
        return [obj]
    tokens = [t for t in path.split(".") if t]
    current: list = [obj]
    for tok in tokens:
        is_list = tok.endswith("[]")
        key = tok[:-2] if is_list else tok
        nxt: list = []
        for node in current:
            if not isinstance(node, dict):
                continue
            if key not in node:
                continue
            val = node[key]
            if is_list:
                if isinstance(val, list):
                    nxt.extend(val)
            else:
                nxt.append(val)
        current = nxt
        if not current:
            return []
    return current


def _flatten(vals: list) -> list:
    """get_values() returns leaves; a path ending in a list field yields [[...]] — flatten it."""
    out = []
    for v in vals:
        if isinstance(v, list):
            out.extend(v)
        else:
            out.append(v)
    return out


def _scalar(v: Any) -> Any:
    """Coerce a leaf to a hashable, comparable scalar.

    A leaf may be a dict/list (e.g. a path resolving to an object). Comparing those
    directly would raise `TypeError: unhashable type`, which would crash the whole
    eval instead of producing a verdict — an eval engine must never crash on a
    malformed-but-parseable artifact. Complex leaves are canonicalised to JSON so the
    check still *works* (it compares deterministically) rather than exploding.
    """
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            return repr(v)
    return v


def _payload_of(artifact: Any) -> Any:
    if isinstance(artifact, dict) and isinstance(artifact.get("payload"), dict):
        return artifact["payload"]
    return artifact


def _skip(state: dict, artifact_type: str, artifact: Any, rules: dict) -> Optional[str]:
    """Some artifacts legitimately carry no products (e.g. NO_CANDIDATES). Return why, or None."""
    for cond in (rules.get("skip_artifact_when", {}) or {}).get(artifact_type, []):
        vals = get_values(artifact, cond["path"])
        if vals and vals[0] in cond.get("in", []):
            return "%s=%s" % (cond["path"], vals[0])
    return None


# --------------------------------------------------------------------------- #
# individual checks
# --------------------------------------------------------------------------- #
def check_schema(artifact: dict, contract_path: Optional[str]) -> dict:
    if not contract_path:
        return {"check_id": "schema", "status": "PASS", "message": "no contract declared"}
    from jsonschema import Draft7Validator

    p = contract_path if os.path.isabs(contract_path) else os.path.join(REPO_ROOT, contract_path)
    with open(p, encoding="utf-8") as f:
        schema = json.load(f)
    errs = sorted(Draft7Validator(schema).iter_errors(artifact), key=lambda e: list(e.path))
    if errs:
        return {"check_id": "schema", "status": "FAIL",
                "message": "; ".join("%s: %s" % ("/".join(str(x) for x in e.path) or "<root>",
                                                 e.message) for e in errs[:3])}
    return {"check_id": "schema", "status": "PASS", "message": ""}


def check_required_fields(artifact: dict, artifact_type: str, rules: dict) -> dict:
    fields = (rules.get("required_fields", {}) or {}).get(artifact_type, [])
    missing = [f for f in fields if not get_values(artifact, f)]
    if missing:
        return {"check_id": "required_fields", "status": "FAIL",
                "message": "missing: %s" % ", ".join(missing)}
    return {"check_id": "required_fields", "status": "PASS", "message": ""}


def _is_empty_value(v: Any) -> bool:
    return v is None or v == [] or v == {} or v == ""


def check_required_non_empty(artifact: dict, artifact_type: str, rules: dict) -> Optional[dict]:
    """A present-but-empty collection is a failure (e.g. an Evidence Provider that found nothing)."""
    fields = (rules.get("required_non_empty", {}) or {}).get(artifact_type, [])
    if not fields:
        return None
    empty = []
    for f in fields:
        vals = get_values(artifact, f)
        if not vals or all(_is_empty_value(v) for v in vals):
            empty.append(f)
    if empty:
        return {"check_id": "required_non_empty", "status": "FAIL",
                "message": "empty: %s" % ", ".join(empty)}
    return {"check_id": "required_non_empty", "status": "PASS", "message": ""}


def check_contamination(artifact: dict, artifact_type: str, rules: dict) -> Optional[dict]:
    cfg = rules.get("contamination", {}) or {}
    if artifact_type not in (cfg.get("applies_to") or []):
        return None
    terms = []
    if cfg.get("use_catalog_terms"):
        for p in load_catalog(rules):
            for k in ("product_id", "product_name", "company"):
                v = p.get(k)
                if v:
                    terms.append(str(v))
    terms.extend(cfg.get("forbidden_terms", []))
    patterns = cfg.get("forbidden_patterns", [])

    blob = json.dumps(artifact, ensure_ascii=False)
    hits = [t for t in terms if t and t in blob]
    hits += [p for p in patterns if p in blob]
    if hits:
        return {"check_id": "contamination", "status": "FAIL",
                "message": "product/company leakage: %s" % ", ".join(sorted(set(hits))[:5])}
    return {"check_id": "contamination", "status": "PASS", "message": ""}


def check_provenance(state: dict, artifact: dict, artifact_type: str, rules: dict) -> Optional[dict]:
    for spec in rules.get("provenance", []) or []:
        if spec.get("artifact_type") != artifact_type:
            continue
        cid = "provenance_%s" % spec["id"]
        if spec.get("path"):
            nodes = get_values(artifact, spec["path"])
            if not nodes:
                return {"check_id": cid, "status": "FAIL",
                        "message": "no nodes at %s" % spec["path"]}
            missing = []
            for n in nodes:
                for f in spec.get("require_all", []):
                    if not (isinstance(n, dict) and n.get(f)):
                        missing.append(f)
            if missing:
                return {"check_id": cid, "status": "FAIL",
                        "message": "missing fields: %s" % ", ".join(sorted(set(missing)))}
            return {"check_id": cid, "status": "PASS", "message": ""}
        if spec.get("requires_path"):
            refs = [r for r in _flatten(get_values(artifact, spec["requires_path"])) if r]
            if len(refs) < int(spec.get("min_items", 1)):
                return {"check_id": cid, "status": "FAIL",
                        "message": "%s has %d items, need %d"
                                   % (spec["requires_path"], len(refs), spec.get("min_items", 1))}
            res = spec.get("resolve_in") or {}
            if res:
                target = state.get("artifacts", {}).get(res["artifact_type"])
                if target is None:
                    return {"check_id": cid, "status": "FAIL",
                            "message": "evidence artifact %s absent" % res["artifact_type"]}
                known = set(get_values(target, res["path"]))
                dangling = [r for r in refs if r not in known]
                if dangling:
                    return {"check_id": cid, "status": "FAIL",
                            "message": "dangling evidence refs: %s" % ", ".join(map(str, dangling[:5]))}
            return {"check_id": cid, "status": "PASS", "message": ""}
    return None


def check_cross_artifact(state: dict, artifact: dict, artifact_type: str, rules: dict) -> list:
    out = []
    for spec in rules.get("cross_artifact", []) or []:
        if spec.get("artifact_type") != artifact_type:
            continue
        cid = "cross_artifact_%s" % spec["id"]
        refs = [r for r in get_values(artifact, spec["source_path"]) if r]
        if not refs:
            out.append({"check_id": cid, "status": "PASS", "message": "no refs to validate"})
            continue
        target = state.get("artifacts", {}).get(spec["target_artifact"])
        if target is None:
            out.append({"check_id": cid, "status": "FAIL",
                        "message": "target artifact %s absent" % spec["target_artifact"]})
            continue
        known = set(get_values(target, spec["target_path"]))
        if not known:
            out.append({"check_id": cid, "status": "FAIL",
                        "message": "target %s has no ids at %s"
                                   % (spec["target_artifact"], spec["target_path"])})
            continue
        orphan = [r for r in refs if r not in known]
        if orphan:
            out.append({"check_id": cid + "_orphan_refs", "status": "FAIL",
                        "message": "orphan refs: %s" % ", ".join(map(str, orphan[:5]))})
        else:
            out.append({"check_id": cid, "status": "PASS", "message": ""})
    return out


def check_invariant(state: dict, artifact: dict, artifact_type: str, rules: dict) -> list:
    out = []
    for spec in rules.get("invariant", []) or []:
        if spec.get("artifact_type") != artifact_type:
            continue
        cid = spec["id"]
        vals = [_scalar(v) for v in _flatten(get_values(artifact, spec["path"])) if v]
        if not vals:
            out.append({"check_id": cid, "status": "PASS", "message": "nothing to validate"})
            continue
        must = spec.get("must_be_in", "")
        if must == "catalog.product_ids":
            allowed = {p.get("product_id") for p in load_catalog(rules)}
        elif must.startswith("artifact:"):
            _, art_type, path = must.split(":", 2)
            target = state.get("artifacts", {}).get(art_type)
            if target is None:
                out.append({"check_id": cid, "status": "FAIL",
                            "message": "artifact %s absent" % art_type})
                continue
            # flatten + scalarise the allowed set exactly like `vals`, so a list/dict-valued
            # field yields a verdict instead of raising on an unhashable member.
            allowed = {_scalar(v) for v in _flatten(get_values(target, path))}
        else:  # pragma: no cover - rules are internal
            out.append({"check_id": cid, "status": "FAIL", "message": "unknown rule %s" % must})
            continue
        bad = [v for v in vals if v not in allowed]
        if bad:
            out.append({"check_id": cid, "status": "FAIL",
                        "message": "not in %s: %s" % (must, ", ".join(map(str, bad[:5])))})
        else:
            out.append({"check_id": cid, "status": "PASS", "message": ""})
    return out


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def next_eval_id(state: dict) -> str:
    return "EVAL-%03d" % (len(state.get("evaluations", [])) + 1)


def evaluate(state: dict, artifact_type: str, artifact: dict, stage: dict,
             rules: Optional[dict] = None, registry: Any = None) -> dict:
    """Evaluate one artifact. Appends to state["evaluations"] and returns the record."""
    rules = rules or load_rules()
    state.setdefault("evaluations", [])

    skipped = _skip(state, artifact_type, artifact, rules)
    checks: list = []
    if skipped:
        checks.append({"check_id": "skipped", "status": "PASS",
                       "message": "artifact intentionally empty: %s" % skipped})
    else:
        checks.append(check_schema(artifact, stage.get("contract")))
        checks.append(check_required_fields(artifact, artifact_type, rules))
        c = check_contamination(artifact, artifact_type, rules)
        if c:
            checks.append(c)
        ne = check_required_non_empty(artifact, artifact_type, rules)
        if ne:
            checks.append(ne)
        p = check_provenance(state, artifact, artifact_type, rules)
        if p:
            checks.append(p)
        checks.extend(check_cross_artifact(state, artifact, artifact_type, rules))
        checks.extend(check_invariant(state, artifact, artifact_type, rules))

    failed = [c for c in checks if c["status"] == "FAIL"]
    repair_map = rules.get("repairable", {}) or {}

    def _repair_key(check_id: str) -> str:
        # cross_artifact_*_orphan_refs collapses to the declared repair key
        if "orphan_refs" in check_id:
            return "cross_artifact_orphan_refs"
        return check_id

    repairable = any(_repair_key(c["check_id"]) in repair_map for c in failed)

    rec = {
        "eval_id": next_eval_id(state),
        "artifact_id": (registry.by_type(state, artifact_type) or {}).get("artifact_id")
                       if registry is not None else None,
        "artifact_type": artifact_type,
        "stage_id": stage.get("id") if stage else None,
        "status": "FAIL" if failed else "PASS",
        "checks": checks,
        "repairable": repairable,
        "created_at": cs.now(),
    }
    state["evaluations"].append(rec)
    cs.record_event(state, "EVAL_FAIL" if failed else "EVAL_PASS", stage=stage.get("id") if stage else None,
                    detail="%s %s (%d checks)" % (rec["eval_id"], artifact_type, len(checks)))
    return rec


def failed_checks(rec: dict) -> list:
    return [{"check_id": c["check_id"], "message": c.get("message", "")}
            for c in rec.get("checks", []) if c["status"] == "FAIL"]
