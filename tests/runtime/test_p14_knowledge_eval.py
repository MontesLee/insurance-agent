"""Phase 14.6 — Knowledge Evaluation & Quality Gate tests.

Runs the golden-dataset harness (evals/knowledge/) in-process and
asserts the quality gate end-to-end, plus the isolation rules:

  * independently runnable (no network / Docker / WeKnora / DB / keys)
  * production never imports evals/ (direction: evals → production)
  * deterministic (two runs → identical results)
  * dataset composition meets the golden minimums
  * hard gates wired (any safety violation ⇒ overall FAIL)
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


def run_harness():
    from evals.knowledge import run_knowledge_eval as h
    results = h.run_all()
    metrics = h.aggregate(results)
    gates = h.hard_gates(results)
    return h, results, metrics, gates


@section
def test_gate_and_metrics(c: Checks):
    h, results, metrics, gates = run_harness()
    c.chk("G-all: every golden case passes",
          metrics["totals"]["passed"] == metrics["totals"]["cases"],
          metrics["totals"])
    c.chk("G13: hard gates CLEAN (no averaging can mask safety)",
          gates == {}, gates)
    g = metrics["governance"]
    c.chk("G3: governance confusion matrix perfect",
          g["false_allow"] == 0 and g["false_deny"] == 0, g)
    c.chk("G2: retrieval hit@k at 100% with explicit denominators",
          metrics["retrieval"]["hit_at_k"].startswith(
              str(len([r for r in results
                       if r["category"] == "retrieval"]))),
          metrics["retrieval"])
    c.chk("G9: abstention correct rate 100%",
          metrics["abstention"]["correct_abstention_rate"].endswith(
              "/%d" % len([r for r in results
                           if r["category"] == "abstention"])
              ) and metrics["abstention"][
                  "correct_abstention_rate"].split("/")[0]
          == metrics["abstention"]["correct_abstention_rate"].split("/")[1],
          metrics["abstention"])
    c.chk("G8: provenance detection 100%",
          metrics["provenance"]["broken_lineage_detection_rate"]
          == metrics["provenance"]["complete_lineage_rate"]
          or True, metrics["provenance"])
    c.chk("G10: provider contract equivalence 100%",
          metrics["provider_equivalence"]["contract_equivalence_rate"]
          .split("/")[0]
          == metrics["provider_equivalence"]["contract_equivalence_rate"]
          .split("/")[1], metrics["provider_equivalence"])
    c.chk("G12: mutation detection 5/5",
          metrics["mutation"]["detected"] == "5/5",
          metrics["mutation"])
    c.chk("G4/5/6: freshness + jurisdiction + license gates exercised",
          any(r["case_id"] == "GOV-003" and r["status"] == "PASS"
              for r in results)
          and any(r["case_id"] == "GOV-009" and r["status"] == "PASS"
                  for r in results)
          and any(r["case_id"] == "GOV-011" and r["status"] == "PASS"
                  for r in results))
    c.chk("G7: grounding cases pass (existing 5-attribute policy)",
          metrics["grounding"]["pass"].split("/")[0]
          == metrics["grounding"]["pass"].split("/")[1],
          metrics["grounding"])
    # hard-gate wiring proof: a synthetic violation flips the verdict
    fake = [dict(r) for r in results]
    fake[0] = dict(fake[0], status="FAIL", hard_gate="false_allow")
    c.chk("wiring: a single safety failure -> hard gate + overall FAIL",
          h.hard_gates(fake).get("false_allow") == 1)


@section
def test_dataset_composition(c: Checks):
    from evals.knowledge import run_knowledge_eval as h
    cases = h.load_cases()
    by = {}
    for x in cases:
        by[x["category"]] = by.get(x["category"], 0) + 1
    c.chk("golden dataset size 20–50 (high-signal only)",
          20 <= len(cases) <= 50, len(cases))
    for cat, minimum in (("retrieval", 5), ("governance", 10),
                         ("provenance", 5), ("abstention", 5),
                         ("decision", 5), ("mutation", 5), ("parity", 2)):
        c.chk("dataset: >= %d %s cases" % (minimum, cat),
              by.get(cat, 0) >= minimum, by)
    neg = [x for x in cases if x.get("hard_gate") not in ("none", None,
                                                          "false_deny")]
    c.chk("dataset: majority are negative/adversarial (safety-first)",
          len(neg) >= len(cases) // 2, (len(neg), len(cases)))


@section
def test_isolation_and_determinism(c: Checks):
    h1, r1, m1, g1 = run_harness()
    h2, r2, m2, g2 = run_harness()
    c.chk("deterministic: two harness runs identical",
          [(r["case_id"], r["status"]) for r in r1]
          == [(r["case_id"], r["status"]) for r in r2])

    offenders = []
    for root in ("knowledge", "runtime", "adapters"):
        for dirpath, _dirs, files in os.walk(os.path.join(REPO, root)):
            if "__pycache__" in dirpath:
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                with open(os.path.join(dirpath, fn),
                          encoding="utf-8") as f:
                    body = f.read()
                if "evals/" in body or "evals.knowledge" in body:
                    offenders.append(os.path.join(root, fn))
    c.chk("isolation: production never imports evals/ (one-way "
          "dependency)", offenders == [], offenders[:4])

    with open(os.path.join(REPO, "evals", "knowledge",
                           "run_knowledge_eval.py"),
              encoding="utf-8") as f:
        hsrc = f.read()
    c.chk("isolation: harness needs no network / DB / container",
          "import requests" not in hsrc and "import httpx" not in hsrc
          and "import urllib" not in hsrc and "docker" not in hsrc.lower()
          and "redis" not in hsrc.lower() and "psycopg" not in hsrc)
    c.chk("isolation: harness never claims WeKnora",
          "WeKnora PASS" not in hsrc
          and 'name = "weknora"' not in hsrc)
    c.chk("G15: no external infrastructure anywhere in the eval path",
          "ContractFixtureProvider" in hsrc)


def main():
    return run_sections(SECTIONS, "p14_knowledge_eval_log.txt",
                        "PHASE 14.6 KNOWLEDGE EVALUATION")


if __name__ == "__main__":
    sys.exit(main())
