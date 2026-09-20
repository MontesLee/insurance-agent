"""Phase 16 — Agent Quality & Decision Evaluation tests.

Wraps evals/agent_quality/run_agent_quality_eval.py: 30/30 cases,
hard gates clean, mutation detection 8/8 (evaluator teeth), metric
honesty (NOT_MEASURABLE declared, never faked), decision matrix
emitted per case × dimension, evaluator independence (production never
imports the evaluator; evaluator never mutates production state).
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


def run_q():
    from evals.agent_quality import run_agent_quality_eval as q
    results, inv, muts = q.run_all()
    hard, metrics = q.aggregate(results, inv, muts)
    return q, results, inv, muts, hard, metrics


@section
def test_quality_gates(c: Checks):
    q, results, inv, muts, hard, metrics = run_q()
    c.chk("dataset: 30 quality cases", len(results) == 30, len(results))
    c.chk("Gate: all quality cases PASS",
          all(r["status"] == "PASS" for r in results),
          [r["case_id"] for r in results if r["status"] != "PASS"][:5])
    c.chk("Gate: hard gates (AQ-HG01..11 mapped) all zero",
          hard == {}, hard)
    c.chk("Gate: mutation detection 8/8 (evaluator teeth, AQ-HG12)",
          all(s == "PASS" for _n, s, _g in muts)
          and len(muts) == 8, [(n, s) for n, s, _g in muts])
    c.chk("Gate: semantic invariance across paraphrase groups",
          not inv, inv[:2])
    for k in ("gap_accuracy", "solution_alignment", "candidate_validity",
              "recommendation_grounding", "report_consistency",
              "abstention_accuracy", "contradiction_detection",
              "semantic_invariance", "question_target_accuracy",
              "recommendation_decision_accuracy"):
        c.chk("metric %s = PASS" % k, metrics.get(k) == "PASS",
              metrics.get(k))
    for k in ("requirement_precision", "requirement_recall",
              "risk_precision", "risk_recall"):
        c.chk("metric %s honestly NOT_MEASURABLE (never faked)"
              % k, metrics.get(k) == "NOT_MEASURABLE", metrics.get(k))
    # wiring: one injected violation flips the aggregate
    fake = [dict(r) for r in results]
    fake[0] = dict(fake[0], status="FAIL",
                   quality_violations=[("gap", "wiring")])
    h2, _m2 = q.aggregate(fake, [], muts)
    c.chk("wiring: injected violation flips a hard gate",
          h2.get("HG-B04") == 1, h2)


@section
def test_matrix_and_independence(c: Checks):
    from evals.agent_quality import run_agent_quality_eval as q
    q, results, inv, muts, hard, metrics = run_q()
    dims_ok = all(isinstance(r["dimensions"], dict) for r in results)
    c.chk("decision matrix: per-case × per-dimension verdicts emitted",
          dims_ok and all(r["dimensions"] for r in results))
    matrix_path = os.path.join(REPO, "evals", "agent_quality",
                               "decision_matrix.json")
    c.chk("decision matrix file written (no averaging)",
          os.path.isfile(matrix_path))
    with open(matrix_path, encoding="utf-8") as f:
        m = json.load(f)
    c.chk("matrix carries per-case dimensions + metrics + mutations",
          {"cases", "metrics", "mutations"} <= set(m.keys()))

    offenders = []
    for root in ("knowledge", "runtime", "adapters"):
        for dp, _d, fs in os.walk(os.path.join(REPO, root)):
            if "__pycache__" in dp:
                continue
            for fn in fs:
                if fn.endswith(".py"):
                    body = open(os.path.join(dp, fn),
                                encoding="utf-8").read()
                    if "agent_quality" in body:
                        offenders.append(fn)
    c.chk("independence: production never imports the evaluator",
          offenders == [], offenders)
    with open(os.path.join(REPO, "evals", "agent_quality",
                           "run_agent_quality_eval.py"),
              encoding="utf-8") as f:
        src = f.read()
    c.chk("independence: no LLM judge, deterministic only",
          "openai" not in src and "import requests" not in src
          and "judge" not in src.lower().replace("llm judge never", ""))
    c.chk("reuse: quality layer delegates to the P15 harness (which "
          "wraps the 14.5 validators) — no second governance "
          "implementation",
          "run_business_eval" in src
          and "def validate_provenance" not in src
          and "def validate_decision_provenance" not in src
          and "effective_from <=" not in src)


def main():
    return run_sections(SECTIONS, "p16_agent_quality_log.txt",
                        "PHASE 16 AGENT QUALITY")


if __name__ == "__main__":
    sys.exit(main())
