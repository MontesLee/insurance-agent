"""Review Card Generator — Phase 27.7.6 v2 (Risk-based Human Review).

OFFLINE tooling over FINISHED runs. It reads a run directory exactly the
way the Web UI does (persisted case_state.json + trace.jsonl — the same
state the runtime produced, no second truth), aggregates it into ONE
human_review_card.json and assigns a review level:

    AUTO_PASS       all checks PASS, no HIGH/MEDIUM flags, sampling not hit
    SUMMARY_REVIEW  review the card only (< 3 min)
    DEEP_REVIEW     validation FAIL or a HIGH flag — open the full chain

It NEVER touches the agent runtime, orchestrator, skills or approvals:
no imports from runtime/* (except none at all — stdlib + yaml/jsonschema),
no state mutation, no LLM. Everything in the card is either verbatim from
the persisted state or a documented aggregation of it.

Honesty rules (inherited from runtime/eval_engine.py §19):
  * a validation dimension with ZERO underlying eval checks reports FAIL
    ("cannot verify"), never PASS — there is no UNKNOWN-pass;
  * UNKNOWN customer fields render as null + an 'unresolved' entry,
    never a guess;
  * every risk flag carries an evidence_ref pointing at its trigger.

Usage:
    python evaluation/human-review/review_card_generator.py <run_dir> \
        [--out PATH] [--stdout] [--rules PATH] [--schema PATH]

    <run_dir>   a webui run dir, e.g. tmp/webui-runs/run_9de5882e
                (contains <case_id>/case_state.json; a missing state is
                handled fail-closed, not crashed)
"""
from __future__ import annotations

import argparse
import fnmatch
import glob
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RULES = os.path.join(HERE, "risk-rules.yaml")
DEFAULT_SCHEMA = os.path.join(HERE, "review-card.schema.json")

GENERATOR_ID = "evaluation/human-review/review_card_generator.py@1.0"

# eval-engine check families -> the four card dimensions. Everything not
# matched by SCHEMA/EVIDENCE lands in LOGIC (the engine owns the full
# vocabulary; the card only groups it).
SCHEMA_CHECK_IDS = {"schema"}
EVIDENCE_CHECK_GLOBS = ["required_non_empty", "provenance_*"]

RISK_HIGHLIGHT_LIMIT = 3


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def find_state(run_dir: str):
    """(state_path, state|None, trace_path|None) — one case per run dir."""
    candidates = sorted(glob.glob(os.path.join(run_dir, "*", "case_state.json")))
    state_path = candidates[0] if candidates else None
    state = None
    if state_path:
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = None
    traces = sorted(glob.glob(os.path.join(run_dir, "*", "trace.jsonl")))
    return state_path, state, (traces[0] if traces else None)


def load_rules(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------- #
# customer summary — verbatim projection of client-profile
# --------------------------------------------------------------------------- #
_PROFILE_FIELDS = {
    "family_profile": ["age", "gender", "marital_status", "children", "housing"],
    "employment_profile": ["occupation"],
    "financial_profile": ["annual_income", "annual_expense", "mortgage",
                          "insurance_budget"],
    "existing_protection": ["social_security", "existing_insurance"],
}


def build_customer_summary(state):
    """{field: value|None} + unresolved list. UNKNOWN/conflicted -> null."""
    if not state:
        return {f: None for group in _PROFILE_FIELDS.values() for f in group}, []
    payload = ((state.get("artifacts") or {}).get("client-profile") or {}).get("payload") or {}
    out, unresolved = {}, []
    for group, fields in _PROFILE_FIELDS.items():
        for f in fields:
            node = (payload.get(group) or {}).get(f) or {}
            value, status = node.get("value"), node.get("status")
            out[f] = value if status == "KNOWN" else None
            if status != "KNOWN":
                unresolved.append("%s=%s" % (f, status or "MISSING"))
    for c in payload.get("conflicts") or []:
        # conflict entries are verbatim upstream records; surface their key
        key = c.get("field") if isinstance(c, dict) else c
        if key:
            unresolved.append("conflict:%s" % key)
    for m in payload.get("missing_from_upstream") or []:
        key = m.get("field") if isinstance(m, dict) else m
        if key:
            unresolved.append("missing:%s" % key)
    return out, unresolved


# --------------------------------------------------------------------------- #
# agent summary — verbatim projection of the business outcome
# --------------------------------------------------------------------------- #
def build_agent_summary(state):
    if not state:
        return {
            "case_status": "UNKNOWN",
            "objective": [],
            "recommendation_status": None,
            "primary": None,
            "recommendation": [],
            "risk_highlights": [],
            "waiting_for_user": None,
        }
    arts = state.get("artifacts") or {}
    req = (arts.get("requirement-analysis") or {}).get("payload") or {}
    objective = ["%s · %s (%s)" % (r.get("requirement_id"), r.get("summary"),
                                   r.get("priority"))
                 for r in req.get("requirements") or [] if r.get("requirement_id")]

    rec = (arts.get("product-recommendation") or {}).get("payload") or {}
    prim_node = rec.get("primary_recommendation") or {}
    product = prim_node.get("product") or {}
    primary = None
    if prim_node.get("candidate_id"):
        primary = {
            "candidate_id": prim_node.get("candidate_id"),
            "product_id": product.get("product_id"),
            "product_name": product.get("product_name"),
        }

    risks = (arts.get("risk-assessment") or {}).get("payload") or {}
    highlights = sorted(
        risks.get("risks") or [],
        key=lambda r: (str(r.get("severity") or ""),
                       _as_number((r.get("coverage_assessment") or {})
                                  .get("unprotected_amount")) or 0),
        reverse=True,
    )[:RISK_HIGHLIGHT_LIMIT]
    risk_highlights = [{
        "risk_id": r.get("risk_id"),
        "risk_name": r.get("risk_name"),
        "severity": r.get("severity"),
        "residual_risk": r.get("residual_risk"),
        "unprotected_amount": (r.get("coverage_assessment") or {})
                              .get("unprotected_amount"),
    } for r in highlights]

    waiting = state.get("waiting_for_user") or None
    return {
        "case_status": state.get("status") or "UNKNOWN",
        "objective": objective,
        "recommendation_status": rec.get("status"),
        "primary": primary,
        "recommendation": [product["product_name"]] if product.get("product_name") else [],
        "risk_highlights": risk_highlights,
        "waiting_for_user": waiting,
    }


def _as_number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# automatic validation — aggregation of the eval records + trace integrity
# --------------------------------------------------------------------------- #
def _dimension(checks, globs, exact_ids):
    """PASS iff at least one underlying check matched and all matched PASS."""
    matched = [c for c in checks
               if c.get("check_id") in exact_ids
               or any(fnmatch.fnmatch(c.get("check_id", ""), g)
                      for g in globs)]
    if not matched:
        return "FAIL"   # cannot verify — honesty rule, never a silent PASS
    return "PASS" if all(c.get("status") == "PASS" for c in matched) else "FAIL"


def _trace_check(state, evals):
    """Execution integrity: did the case reach an orderly, by-design terminal?"""
    if not state:
        return "FAIL", "case state not persisted (run stopped before checkpoint)"
    status = state.get("status")
    tasks = state.get("tasks") or []
    if status == "COMPLETED":
        bad = [t for t in tasks if t.get("status") != "PASS"]
        if bad:
            return "FAIL", "%d task(s) not PASS at COMPLETED" % len(bad)
        return "PASS", ""
    if status == "NEEDS_REVIEW":
        # by-design stop: an eval-driven block or an explicit review stage
        if any(e.get("status") == "FAIL" for e in evals) or any(
                ev.get("type") == "STAGE_NEEDS_REVIEW"
                for ev in state.get("events") or []):
            return "PASS", "stopped by design (blocked -> human review)"
        return "FAIL", "NEEDS_REVIEW without a blocking eval or review stage"
    if status == "WAITING_FOR_USER":
        if state.get("waiting_for_user"):
            return "PASS", "stopped by design (asking the user)"
        return "FAIL", "WAITING_FOR_USER without a waiting_for_user record"
    return "FAIL", "terminal status %r is not an orderly reviewable state" % status


def build_automatic_validation(state, evals):
    flat = []
    for e in evals:
        for c in e.get("checks") or []:
            flat.append({
                "eval_id": e.get("eval_id"),
                "artifact_type": e.get("artifact_type"),
                "check_id": c.get("check_id", ""),
                "status": c.get("status"),
                "message": c.get("message", ""),
            })
    schema_status = _dimension(flat, (), SCHEMA_CHECK_IDS) if flat else "FAIL"
    evidence_status = _dimension(flat, tuple(EVIDENCE_CHECK_GLOBS), set()) if flat else "FAIL"
    logic_status = _dimension(
        flat, (),
        {c["check_id"] for c in flat
         if c["check_id"] not in SCHEMA_CHECK_IDS
         and not any(fnmatch.fnmatch(c["check_id"], g)
                     for g in EVIDENCE_CHECK_GLOBS)}) if flat else "FAIL"
    trace_status, trace_msg = _trace_check(state, evals)

    failed_checks = [{k: c[k] for k in
                      ("eval_id", "artifact_type", "check_id", "message")}
                     for c in flat if c["status"] == "FAIL"]
    if trace_status == "FAIL":
        failed_checks = failed_checks + [{
            "eval_id": None, "artifact_type": None,
            "check_id": "trace_check", "message": trace_msg,
        }]
    return {
        "schema_check": schema_status,
        "trace_check": trace_status,
        "evidence_check": evidence_status,
        "logic_check": logic_status,
        "eval_summary": {
            "total": len(evals),
            "passed": sum(1 for e in evals if e.get("status") == "PASS"),
            "failed": sum(1 for e in evals if e.get("status") == "FAIL"),
            "failed_eval_ids": [e.get("eval_id") for e in evals
                                if e.get("status") == "FAIL"],
        },
        "failed_checks": failed_checks,
    }, trace_msg


# --------------------------------------------------------------------------- #
# risk flags — deterministic predicates, bindings from risk-rules.yaml
# --------------------------------------------------------------------------- #
def _rule(rules, group, rule_id):
    for r in rules.get(group) or []:
        if r.get("id") == rule_id:
            return r
    return {}


def _eval_failed_refs(flat, check_globs, artifact_types):
    """Refs of failed eval checks matching the globs (optionally per artifact)."""
    types = set(artifact_types or [])
    out = []
    for c in flat:
        if c["status"] != "FAIL":
            continue
        if types and c["artifact_type"] not in types:
            continue
        if any(fnmatch.fnmatch(c["check_id"], g) for g in check_globs):
            out.append("eval:%s:%s" % (c["eval_id"], c["check_id"]))
    return out


def build_risk_flags(rules, state, evals, validation):
    flat = validation["_flat"]  # injected by caller (see generate_card)
    flags = []

    def flag(rule, severity, ref):
        flags.append({
            "type": rule.get("id"),
            "severity": severity,
            "message": rule.get("message", rule.get("id")),
            "evidence_ref": ref or None,
        })

    # ---- HIGH ----------------------------------------------------------- #
    r = _rule(rules, "high_risk", "missing_evidence")
    refs = _eval_failed_refs(flat, r.get("check_ids", []), r.get("artifact_types"))
    if refs:
        flag(r, "HIGH", refs[0])

    r = _rule(rules, "high_risk", "false_product_information")
    refs = _eval_failed_refs(flat, r.get("check_ids", []), r.get("artifact_types"))
    if refs:
        flag(r, "HIGH", refs[0])

    r = _rule(rules, "high_risk", "unresolved_task_failure")
    bad = [t for t in (state or {}).get("tasks") or [] if t.get("status") != "PASS"] \
        if state else []
    if not state:
        # absent state cannot prove task integrity — fail closed
        bad = [{"task_id": None}]
    if bad:
        flag(r, "HIGH", "task:%s:status=%s" % (
            bad[0].get("task_id"), bad[0].get("status")))

    r = _rule(rules, "high_risk", "case_not_finalized")
    if (not state) or ((state.get("status") or "") not in (r.get("statuses") or [])):
        flag(r, "HIGH", "case:status=%s" % ((state or {}).get("status") or "NOT_PERSISTED"))

    # ---- MEDIUM ---------------------------------------------------------- #
    r = _rule(rules, "medium_risk", "no_primary_recommendation")
    rec_status, has_primary = None, False
    if state:
        rec = ((state.get("artifacts") or {}).get("product-recommendation") or {}).get("payload") or {}
        rec_status = rec.get("status")
        has_primary = bool((rec.get("primary_recommendation") or {}).get("candidate_id"))
    if not has_primary:
        flag(r, "MEDIUM", "rec:status=%s" % (rec_status or "ABSENT"))

    r = _rule(rules, "medium_risk", "insufficient_customer_context")
    unresolved = validation["_unresolved"]
    if unresolved:
        flag(r, "MEDIUM", "profile:%s" % ",".join(unresolved[:3]))

    r = _rule(rules, "medium_risk", "high_exposure")
    min_amt = float(r.get("min_unprotected_amount", 0) or 0)
    min_sev = r.get("min_severity", "CRITICAL")
    hit = None
    for rk in ((state or {}).get("artifacts") or {}).get("risk-assessment", {}) \
            .get("payload", {}).get("risks") or []:
        amt = _as_number((rk.get("coverage_assessment") or {}).get("unprotected_amount"))
        if rk.get("severity") == min_sev or rk.get("residual_risk") == min_sev \
                or (amt is not None and amt >= min_amt):
            hit = "risk:%s:severity=%s,gap=%s" % (rk.get("risk_id"),
                                                  rk.get("severity"),
                                                  (rk.get("coverage_assessment") or {})
                                                  .get("unprotected_amount"))
            break
    if hit:
        flag(r, "MEDIUM", hit)

    r = _rule(rules, "medium_risk", "repair_used")
    repaired = [t for t in ((state or {}).get("tasks") or [])
                if (t.get("attempt") or 1) > 1]
    if repaired:
        flag(r, "MEDIUM", "task:%s:attempt=%s" % (repaired[0].get("task_id"),
                                                  repaired[0].get("attempt")))
    return flags


# --------------------------------------------------------------------------- #
# sampling + decision
# --------------------------------------------------------------------------- #
def sampling_hit(rules, case_id, run_id):
    rate = float((rules.get("sampling") or {}).get("rate", 0) or 0)
    seed = "%s:%s" % (case_id, run_id)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return rate, int(digest[:8], 16) % 10000 < rate * 10000, seed


def decide(validation, flags, sampled):
    """Strict order: validation FAIL > HIGH > (MEDIUM | sampling)."""
    reasons = []
    for dim in ("schema_check", "trace_check", "evidence_check", "logic_check"):
        if validation[dim] == "FAIL":
            reasons.append("validation FAIL: %s" % dim)
    validation_status = "FAIL" if reasons else "PASS"
    highs = [f for f in flags if f["severity"] == "HIGH"]
    mediums = [f for f in flags if f["severity"] == "MEDIUM"]
    for f in highs:
        reasons.append("HIGH flag: %s" % f["type"])
    for f in mediums:
        reasons.append("MEDIUM flag: %s" % f["type"])
    if sampled:
        reasons.append("random audit sampling triggered")
    if validation_status == "FAIL" or highs:
        return {"required": True, "level": "DEEP_REVIEW", "reasons": reasons}, validation_status
    if mediums or sampled:
        return {"required": True, "level": "SUMMARY_REVIEW", "reasons": reasons}, validation_status
    return {"required": False, "level": "AUTO_PASS", "reasons": [
        "all checks PASS, no HIGH/MEDIUM flags, sampling not triggered"]}, validation_status


# --------------------------------------------------------------------------- #
# card assembly
# --------------------------------------------------------------------------- #
def generate_card(run_dir: str, rules_path: str = DEFAULT_RULES) -> dict:
    rules = load_rules(rules_path)
    state_path, state, trace_path = find_state(run_dir)
    run_id = os.path.basename(os.path.normpath(run_dir))
    case_id = (state or {}).get("case_id") or \
        os.path.basename(os.path.normpath(os.path.dirname(state_path or ""))) \
        if state_path else "UNKNOWN"
    evals = (state or {}).get("evaluations") or []

    customer, unresolved = build_customer_summary(state)
    customer["unresolved"] = unresolved
    agent = build_agent_summary(state)
    validation, _trace_msg = build_automatic_validation(state, evals)
    flat = [c for e in evals for c in
            [{"eval_id": e.get("eval_id"), "artifact_type": e.get("artifact_type"),
              "check_id": c.get("check_id", ""), "status": c.get("status"),
              "message": c.get("message", "")} for c in (e.get("checks") or [])]]
    validation["_flat"] = flat
    validation["_unresolved"] = unresolved
    flags = build_risk_flags(rules, state, evals, validation)
    validation.pop("_flat", None)
    validation.pop("_unresolved", None)

    rate, sampled, seed = sampling_hit(rules, case_id, run_id)
    action, validation_status = decide(validation, flags, sampled)

    card = {
        "schema_version": "1.0",
        "card_id": "HRC-%s" % hashlib.sha1(
            ("%s:%s" % (case_id, run_id)).encode("utf-8")).hexdigest()[:8],
        "case_id": case_id,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": GENERATOR_ID,
        "source": {
            "state_path": os.path.relpath(state_path, os.getcwd())
            .replace(os.sep, "/") if state_path else None,
            "trace_path": os.path.relpath(trace_path, os.getcwd())
            .replace(os.sep, "/") if trace_path else None,
            "state_persisted": state is not None,
        },
        "customer_summary": customer,
        "agent_summary": agent,
        "automatic_validation": validation,
        "risk_flags": flags,
        "review_action": action,
        "validation_status": validation_status,
        "sampling": {"rate": rate, "triggered": sampled, "seed": seed},
    }
    return card


def validate_card(card: dict, schema_path: str = DEFAULT_SCHEMA) -> None:
    """Fail loud: an invalid card must never be written to disk."""
    from jsonschema import Draft7Validator
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    errors = sorted(Draft7Validator(schema).iter_errors(card),
                    key=lambda e: list(e.path))
    if errors:
        raise ValueError("generated card violates its own schema: %s"
                         % "; ".join("%s: %s" % ("/".join(map(str, e.path)) or "<root>",
                                                 e.message) for e in errors[:3]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", help="run directory, e.g. tmp/webui-runs/run_xxx")
    ap.add_argument("--out", default=None,
                    help="output path (default: <run_dir>/human_review_card.json)")
    ap.add_argument("--stdout", action="store_true",
                    help="print the card instead of writing it")
    ap.add_argument("--rules", default=DEFAULT_RULES)
    ap.add_argument("--schema", default=DEFAULT_SCHEMA)
    args = ap.parse_args(argv)

    if not os.path.isdir(args.run_dir):
        print("error: run dir not found: %s" % args.run_dir, file=sys.stderr)
        return 2
    card = generate_card(args.run_dir, args.rules)
    validate_card(card, args.schema)
    text = json.dumps(card, ensure_ascii=False, indent=2)
    if args.stdout:
        print(text)
    else:
        out = args.out or os.path.join(args.run_dir, "human_review_card.json")
        with open(out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("review card written: %s (level=%s validation=%s flags=%d)"
              % (out, card["review_action"]["level"], card["validation_status"],
                 len(card["risk_flags"])), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
