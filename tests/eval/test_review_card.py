"""Phase 27.7.6 v2 — Review Card Generator tests.

Covers the four required scenarios plus the honesty rules:
  1. all-pass case                  -> AUTO_PASS
  2. medium-risk case               -> SUMMARY_REVIEW
  3. high-risk case                 -> DEEP_REVIEW
  4. missing-evidence case          -> validation FAIL (+ DEEP_REVIEW)
  5. fail-closed on absent state    -> all checks FAIL, never a crash
  6. sampling override              -> rate 1.0 forces SUMMARY_REVIEW
  7. schema conformance             -> generated cards AND the committed
                                       example validate against
                                       review-card.schema.json
  8. no-fabrication                 -> UNKNOWN profile fields are null +
                                       unresolved, never guessed
  9. determinism                    -> same input, same card (ex timestamp)

Fixtures are synthetic case_state.json files written to tmp/ — the tests
never touch real run dirs and never invoke the runtime.
Dual-mode: `pytest tests/eval -q` or `python tests/eval/test_review_card.py`.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import yaml  # noqa: E402

LAYER = os.path.join(REPO, "evaluation", "human-review")
SCHEMA_PATH = os.path.join(LAYER, "review-card.schema.json")
RULES_PATH = os.path.join(LAYER, "risk-rules.yaml")
EXAMPLE_PATH = os.path.join(LAYER, "review-card-example.json")

_spec = importlib.util.spec_from_file_location(
    "review_card_generator",
    os.path.join(LAYER, "review_card_generator.py"))
GEN = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GEN)

TMP_ROOT = os.path.join(REPO, "tmp", "eval-human-review")


# --------------------------------------------------------------------------- #
# fixture builders — minimal but faithful case_state shapes
# --------------------------------------------------------------------------- #
def _check(cid, status="PASS", msg=""):
    return {"check_id": cid, "status": status, "message": msg}


def _eval(n, artifact_type, checks, status=None):
    failed = any(c["status"] == "FAIL" for c in checks)
    return {"eval_id": "EVAL-%03d" % n, "artifact_type": artifact_type,
            "stage_id": artifact_type, "status": status or ("FAIL" if failed else "PASS"),
            "checks": checks, "repairable": False,
            "created_at": "2026-09-24T00:00:00+00:00"}


def _known(v):
    return {"value": v, "status": "KNOWN"}


def _unknown(reason):
    return {"value": None, "status": "UNKNOWN", "reason": reason}


def make_state(case_id="tc-001", status="COMPLETED", evals=None, tasks=None,
               rec_status="COMPLETE", primary="C001", profile=None,
               risks=None, waiting=None):
    evals = evals if evals is not None else [
        _eval(1, "client-profile", [_check("schema"), _check("required_fields")]),
        _eval(2, "knowledge-evidence",
              [_check("schema"), _check("required_non_empty"),
               _check("provenance_evidence_document_chunk")]),
        _eval(3, "product-recommendation",
              [_check("schema"), _check("required_fields"),
               _check("required_non_empty"),
               _check("provenance_recommendation_evidence")]),
    ]
    tasks = tasks if tasks is not None else [
        {"task_id": "TASK-%03d" % i, "status": "PASS", "attempt": 1}
        for i in range(1, len(evals) + 1)
    ]
    profile = profile if profile is not None else {
        "family_profile": {"age": _known("35"), "marital_status": _known("已婚"),
                           "children": _known("1孩"), "housing": _known("自有"),
                           "gender": _known("男")},
        "employment_profile": {"occupation": _known("工程师")},
        "financial_profile": {"annual_income": _known("80万"),
                              "annual_expense": _known("36万"),
                              "mortgage": _known("200万"),
                              "insurance_budget": _known("3万")},
        "existing_protection": {"social_security": _known("职工社保"),
                                "existing_insurance": _known("百万医疗险")},
    }
    profile.setdefault("conflicts", [])
    profile.setdefault("missing_from_upstream", [])
    risks = risks if risks is not None else [{
        "risk_id": "R1-001", "risk_name": "医疗费用", "severity": "HIGH",
        "residual_risk": "HIGH",
        "coverage_assessment": {"unprotected_amount": 500000},
    }]
    rec = {"status": rec_status}
    if primary:
        rec["primary_recommendation"] = {
            "candidate_id": primary,
            "product": {"product_id": "P001", "product_name": "demo-医疗险A"},
            "provenance": [{"type": "knowledge", "ref": "01_medical_002"}],
        }
    return {
        "case_id": case_id, "status": status,
        "artifacts": {
            "client-profile": {"payload": profile},
            "requirement-analysis": {"payload": {"requirements": [
                {"requirement_id": "REQ-MED", "summary": "大额医疗支出保障",
                 "priority": "P1_HIGH"}]}},
            "risk-assessment": {"payload": {"risks": risks}},
            "knowledge-evidence": {"payload": {"status": "success", "evidence": [
                {"evidence_id": "01_medical_002", "content": "…", "source": "kb"}]}},
            "product-recommendation": {"payload": rec},
        },
        "evaluations": evals,
        "tasks": tasks,
        "events": [{"at": "2026-09-24T00:00:00+00:00", "type": "CASE_CREATED",
                    "stage": None, "detail": ""}],
        "waiting_for_user": waiting or {},
    }


def stage_run(name, state=None):
    """Write a run dir with optional case_state; returns its path."""
    run_dir = os.path.join(TMP_ROOT, name)
    if os.path.isdir(run_dir):
        shutil.rmtree(run_dir)
    case_dir = os.path.join(run_dir, "tc-case")
    os.makedirs(case_dir)
    if state is not None:
        with open(os.path.join(case_dir, "case_state.json"), "w",
                  encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    with open(os.path.join(case_dir, "trace.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"trace_id": "T-1", "case_id": "tc-case",
                            "event": "CASE_STARTED"}) + "\n")
    return run_dir


def rules_with(rate=None):
    """Default rules with sampling.rate patched (isolated from hash luck)."""
    with open(RULES_PATH, encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    if rate is not None:
        rules["sampling"]["rate"] = rate
    p = os.path.join(TMP_ROOT, "rules-%s.yaml" % rate)
    os.makedirs(TMP_ROOT, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(rules, f, allow_unicode=True)
    return p


RULES_OFF = None   # filled by setup() (rate 0.0)
RULES_ON = None    # filled by setup() (rate 1.0)


def setup():
    global RULES_OFF, RULES_ON
    os.makedirs(TMP_ROOT, exist_ok=True)
    RULES_OFF = rules_with(rate=0.0)
    RULES_ON = rules_with(rate=1.0)


def card_of(run_dir, rules=None):
    card = GEN.generate_card(run_dir, rules or RULES_OFF)
    GEN.validate_card(card, SCHEMA_PATH)
    return card


def cleanup():
    if os.path.isdir(TMP_ROOT):
        shutil.rmtree(TMP_ROOT, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 1 — all-pass -> AUTO_PASS
# --------------------------------------------------------------------------- #
def test_all_pass_case_auto_pass():
    setup()
    try:
        run_dir = stage_run("hr-allpass", make_state())
        c = card_of(run_dir)
        assert c["automatic_validation"]["schema_check"] == "PASS"
        assert c["automatic_validation"]["trace_check"] == "PASS"
        assert c["automatic_validation"]["evidence_check"] == "PASS"
        assert c["automatic_validation"]["logic_check"] == "PASS"
        assert c["risk_flags"] == [], "happy case must carry no flags"
        assert c["review_action"]["level"] == "AUTO_PASS"
        assert c["review_action"]["required"] is False
        assert c["validation_status"] == "PASS"
        assert c["agent_summary"]["primary"]["candidate_id"] == "C001"
        assert c["customer_summary"]["age"] == "35"
    finally:
        cleanup()


# --------------------------------------------------------------------------- #
# 2 — medium risk -> SUMMARY_REVIEW (two independent medium triggers)
# --------------------------------------------------------------------------- #
def test_medium_risk_case_summary_review():
    setup()
    try:
        # (a) NO_CANDIDATES: business outcome "no product" -> medium flag
        run_dir = stage_run("hr-medium",
                            make_state(rec_status="NO_CANDIDATES", primary=None))
        c = card_of(run_dir)
        types = [f["type"] for f in c["risk_flags"]]
        assert "no_primary_recommendation" in types
        assert all(f["severity"] == "MEDIUM" for f in c["risk_flags"])
        assert c["review_action"]["level"] == "SUMMARY_REVIEW"
        assert c["review_action"]["required"] is True
        assert c["validation_status"] == "PASS"
        # (b) high exposure: CRITICAL risk with 2,000,000 gap
        run_dir2 = stage_run("hr-exposure", make_state(
            case_id="tc-002", risks=[{
                "risk_id": "R2-001", "risk_name": "重疾", "severity": "CRITICAL",
                "residual_risk": "CRITICAL",
                "coverage_assessment": {"unprotected_amount": 2000000}}]))
        c2 = card_of(run_dir2)
        types2 = [f["type"] for f in c2["risk_flags"]]
        assert "high_exposure" in types2
        assert c2["review_action"]["level"] == "SUMMARY_REVIEW"
        ref = [f["evidence_ref"] for f in c2["risk_flags"]
               if f["type"] == "high_exposure"][0]
        assert "R2-001" in ref, "flag must carry its risk evidence ref"
    finally:
        cleanup()


# --------------------------------------------------------------------------- #
# 3 — high risk (unfinished case) -> DEEP_REVIEW while all evals PASS
# --------------------------------------------------------------------------- #
def test_high_risk_case_deep_review():
    setup()
    try:
        state = make_state(status="WAITING_FOR_USER",
                           waiting={"reason": "INSUFFICIENT_INFORMATION",
                                    "next_questions": ["年龄?"]})
        # a waiting case never produced rec/candidates: only upstream evals
        state["evaluations"] = [
            _eval(1, "client-profile", [_check("schema"), _check("required_fields")]),
            _eval(2, "requirement-analysis", [_check("schema"), _check("required_fields")]),
        ]
        state["artifacts"].pop("product-recommendation")
        state["artifacts"].pop("knowledge-evidence")
        run_dir = stage_run("hr-waiting", state)
        c = card_of(run_dir)
        types = [f["type"] for f in c["risk_flags"]]
        assert "case_not_finalized" in types
        assert [f for f in c["risk_flags"] if f["type"] == "case_not_finalized"][0] \
            ["severity"] == "HIGH"
        assert c["review_action"]["level"] == "DEEP_REVIEW"
        # trace orderly (stopped by design) yet the case is unresolved — both true
        assert c["automatic_validation"]["trace_check"] == "PASS"
        assert c["agent_summary"]["waiting_for_user"]["reason"] == \
            "INSUFFICIENT_INFORMATION"
    finally:
        cleanup()


# --------------------------------------------------------------------------- #
# 4 — missing evidence -> validation FAIL (+ missing_evidence HIGH)
# --------------------------------------------------------------------------- #
def test_missing_evidence_case_fail():
    setup()
    try:
        evals = [
            _eval(1, "client-profile", [_check("schema"), _check("required_fields")]),
            _eval(2, "knowledge-evidence", [
                _check("schema"),
                _check("required_non_empty", "FAIL", "empty: payload.evidence"),
                _check("provenance_evidence_document_chunk", "FAIL",
                       "dangling evidence refs: 01_medical_002"),
                _check("provenance_recommendation_evidence", "FAIL",
                       "evidence artifact knowledge-evidence absent")]),
        ]
        state = make_state(status="NEEDS_REVIEW", evals=evals,
                           rec_status=None, primary=None)
        state["artifacts"].pop("product-recommendation")
        run_dir = stage_run("hr-noev", state)
        c = card_of(run_dir)
        assert c["validation_status"] == "FAIL"
        assert c["automatic_validation"]["evidence_check"] == "FAIL"
        assert c["review_action"]["level"] == "DEEP_REVIEW"
        sev = {f["type"]: f["severity"] for f in c["risk_flags"]}
        assert sev.get("missing_evidence") == "HIGH"
        refs = [f["evidence_ref"] for f in c["risk_flags"]
                if f["type"] == "missing_evidence"][0]
        assert refs.startswith("eval:EVAL-002:")
        # the failing checks are listed with their source for deep review
        ids = [fc["check_id"] for fc in
               c["automatic_validation"]["failed_checks"]]
        assert "required_non_empty" in ids
        assert any(cid.startswith("provenance_") for cid in ids)
        assert any(r.startswith("validation FAIL") for r in
                   c["review_action"]["reasons"])
    finally:
        cleanup()


# --------------------------------------------------------------------------- #
# 5 — fail-closed: absent state never crashes, never guesses PASS
# --------------------------------------------------------------------------- #
def test_absent_state_fails_closed():
    setup()
    try:
        run_dir = stage_run("hr-nostate", state=None)
        c = card_of(run_dir)
        for dim in ("schema_check", "trace_check", "evidence_check", "logic_check"):
            assert c["automatic_validation"][dim] == "FAIL", dim
        assert c["validation_status"] == "FAIL"
        assert c["review_action"]["level"] == "DEEP_REVIEW"
        assert c["source"]["state_persisted"] is False
        # no fabricated customer data
        assert c["customer_summary"]["age"] is None
        assert c["agent_summary"]["case_status"] == "UNKNOWN"
    finally:
        cleanup()


# --------------------------------------------------------------------------- #
# 6 — sampling override: rate 1.0 upgrades a clean case to SUMMARY_REVIEW
# --------------------------------------------------------------------------- #
def test_sampling_forces_summary_review():
    setup()
    try:
        run_dir = stage_run("hr-sample", make_state())
        c = GEN.generate_card(run_dir, RULES_ON)
        GEN.validate_card(c, SCHEMA_PATH)
        assert c["sampling"]["triggered"] is True
        assert c["sampling"]["rate"] == 1.0
        assert c["review_action"]["level"] == "SUMMARY_REVIEW"
        assert any("sampling" in r for r in c["review_action"]["reasons"])
        # determinism: same seed always re-samples the same way
        c2 = GEN.generate_card(run_dir, RULES_ON)
        assert c2["sampling"]["seed"] == c["sampling"]["seed"]
    finally:
        cleanup()


# --------------------------------------------------------------------------- #
# 7 — schema conformance incl. the committed example (real pilot data)
# --------------------------------------------------------------------------- #
def test_example_card_conforms_to_schema():
    from jsonschema import Draft7Validator
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    with open(EXAMPLE_PATH, encoding="utf-8") as f:
        example = json.load(f)
    errors = list(Draft7Validator(schema).iter_errors(example))
    assert not errors, "example card drifted from schema: %r" % errors[:2]
    assert example["review_action"]["level"] == "AUTO_PASS"


# --------------------------------------------------------------------------- #
# 8 — no fabrication: UNKNOWN profile fields are null + surfaced
# --------------------------------------------------------------------------- #
def test_unknown_profile_fields_are_null_and_flagged():
    setup()
    try:
        profile = {
            "family_profile": {"age": _unknown("未提供年龄"),
                               "marital_status": _known("已婚")},
            "financial_profile": {"annual_income": _unknown("未提供收入")},
            "existing_protection": {},
        }
        state = make_state(case_id="tc-unk", profile=profile)
        run_dir = stage_run("hr-unknown", state)
        c = card_of(run_dir)
        assert c["customer_summary"]["age"] is None
        assert c["customer_summary"]["annual_income"] is None
        assert c["customer_summary"]["marital_status"] == "已婚"
        assert "age=UNKNOWN" in c["customer_summary"]["unresolved"]
        types = [f["type"] for f in c["risk_flags"]]
        assert "insufficient_customer_context" in types
    finally:
        cleanup()


# --------------------------------------------------------------------------- #
# 9 — determinism: identical input -> identical verdict (ex timestamp)
# --------------------------------------------------------------------------- #
def test_generation_is_deterministic():
    setup()
    try:
        run_dir = stage_run("hr-det", make_state())
        c1 = card_of(run_dir)
        c2 = card_of(run_dir)
        for c in (c1, c2):
            c.pop("generated_at")
        assert c1 == c2
    finally:
        cleanup()


def main() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS %s" % t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL %s: %r" % (t.__name__, e))
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
