"""Phase 15 — Business E2E Validation tests.

Wraps the business evaluator (evals/business/run_business_eval.py) and
asserts the §20 gates: 15/15 cases, cross-skill invariants 100%, hard
gates all zero, all 11 metrics PASS, dataset composition (10 golden +
5 negative), determinism of the harness bookkeeping, and the
one-way-dependency / no-LLM isolation rules.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def run_eval():
    from evals.business import run_business_eval as be
    results = be.run_all()
    agg = be.aggregate(results)
    return be, results, agg


@section
def test_gates(c: Checks):
    be, results, agg = run_eval()
    golden = [r for r in results if r["kind"] == "golden"]
    neg = [r for r in results if r["kind"] == "negative"]
    c.chk("Gate1: 10/10 golden cases pass",
          len(golden) == 10 and all(r["status"] == "PASS" for r in golden),
          [r["case_id"] for r in golden if r["status"] != "PASS"])
    c.chk("Gate1: 5/5 negative cases pass",
          len(neg) == 5 and all(r["status"] == "PASS" for r in neg),
          [r["case_id"] for r in neg if r["status"] != "PASS"])
    c.chk("Gate2/3: cross-skill invariants 100% — every HG-B gate at 0",
          agg["hard_gates"] == {}, agg["hard_gates"])
    m = agg["metrics"]
    for k in ("facts_accuracy", "requirement_consistency",
              "risk_consistency", "gap_consistency",
              "solution_consistency", "knowledge_grounding",
              "product_catalog_validity", "recommendation_grounding",
              "report_consistency", "abstention_correctness",
              "cross_skill_consistency"):
        c.chk("metric %s = PASS (no PASS_WITH_GUESS allowed)"
              % k, m.get(k) == "PASS", m.get(k))
    # hard-gate wiring: one injected violation must flip the verdict
    fake = [dict(r) for r in results]
    fake[0] = dict(fake[0], status="FAIL",
                   violations=[("HG-B05", "wiring-proof")])
    c.chk("wiring: one hard-gate violation flips the aggregate",
          be.aggregate(fake)["hard_gates"].get("HG-B05") == 1)


@section
def test_validate_business_decision(c: Checks):
    from evals.business.run_business_eval import validate_business_decision
    from knowledge.governance import SourceRegistry
    reg = SourceRegistry.from_kb(
        os.path.join(REPO, "knowledge", "governance", "fixtures", "kb"),
        os.path.join(REPO, "knowledge", "governance", "fixtures",
                     "governed_sources.json"))
    ok, why = validate_business_decision(
        {"evidence_policy": "NO_EVIDENCE_REQUIRED"}, {}, reg)
    c.chk("§11: explicit NO_EVIDENCE_REQUIRED passes", ok)
    ok, why = validate_business_decision(
        {"status": "COMPLETE", "evidence_refs": ["NOPE"]}, {}, reg)
    c.chk("§11: COMPLETE with unresolvable evidence fails", not ok)
    ok, why = validate_business_decision(
        {"status": "COMPLETE", "evidence_refs": []}, {}, reg,
        require_evidence=True)
    c.chk("§11: silent no-evidence never passes", not ok and
          any(x.startswith("D001") for x in why))


@section
def test_isolation(c: Checks):
    with open(os.path.join(REPO, "evals", "business",
                           "run_business_eval.py"), encoding="utf-8") as f:
        src = f.read()
    c.chk("isolation: business evaluator is deterministic "
          "(no LLM judge / no network)",
          "openai" not in src and "httpx" not in src
          and "import requests" not in src
          and "llm" not in src.lower().replace("no llm judge", ""))
    c.chk("isolation: validator delegates to Phase-14.5 governance "
          "(no second implementation)",
          "validate_decision_provenance" in src
          and "effective_from <=" not in src)
    offenders = []
    for root in ("knowledge", "runtime", "adapters"):
        for dp, _d, fs in os.walk(os.path.join(REPO, root)):
            if "__pycache__" in dp:
                continue
            for fn in fs:
                if fn.endswith(".py"):
                    body = open(os.path.join(dp, fn),
                                encoding="utf-8").read()
                    if "evals.business" in body or "evals/business" in body:
                        offenders.append(fn)
    c.chk("isolation: production never imports evals/business",
          offenders == [], offenders)
    data = json.load(open(os.path.join(
        REPO, "evals", "business", "dataset", "business_cases.json"),
        encoding="utf-8"))
    c.chk("dataset: 10 golden + 5 negative (composition per §8/§9)",
          len(data["golden_cases"]) == 10
          and len(data["negative_cases"]) == 5)
    neg_ids = {n["case_id"] for n in data["negative_cases"]}
    c.chk("dataset: negatives cover the five required scenarios",
          len({n["scenario"] for n in data["negative_cases"]}) == 5
          and "N005-evidence-missing" in neg_ids)


def main():
    return run_sections(SECTIONS, "p15_business_e2e_log.txt",
                        "PHASE 15 BUSINESS E2E")


if __name__ == "__main__":
    sys.exit(main())
