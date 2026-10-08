# -*- coding: utf-8 -*-
"""FIX-3 Phase 8 — Candidate-C ISOLATED reference implementation +
replay harness (OFFLINE ONLY; zero production wiring).

Candidate-C conjunction (Phase-7 definition, strict):
  ALLOW_UPGRADE iff baseline==PARTIAL AND cited AND hard_prefilter PASS
                   AND risk_boundary PASS AND judge ALLOW_UPGRADE
                   AND post_gate PASS
  else KEEP_BASELINE.  Judge FAIL/timeout/malformed/UNCERTAIN/exception
  => KEEP_BASELINE.  NO fail-open anywhere.

Produces the full six-stage runtime trace per claim, the failure-
injection matrix, known-blocker containment, exhaustive safety-property
grid, and utility measurement. Judge outputs come from the Phase-5/6
RAW caches wherever available (zero extra LLM); a real judge is called
ONLY for corpus claims that reach the judge stage with no cached raw.
"""
from __future__ import annotations

import itertools
import json
import os
import re
import sys
import time
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from runtime.grounding import claim_support as cs  # noqa: E402

OBS = os.path.join(REPO, "tmp", "obs")
CIT = re.compile(r"\[E\d+\]")
HARD = re.compile(
    r"\d|P0\d{2}|demo-|该产品|这款|某产品|保险法|管理办法|监管|银保监|"
    r"令第|施行|保证.{0,6}(续保|赔付|返还)|承诺|"
    r"所有|全部|一律|任何|都.{0,3}(能|可|会|是|有)|必然|一定会|"
    r"每个人|所有人群|所有情况|所有产品|"
    r"您|你家|您家|你的")
RISK = re.compile(
    r"\d+(?:\.\d+)?\s*(?:天|日|万|万元|元|%|岁|周岁|年|倍|次|月)|"
    r"P0\d{2}|demo-|该产品|这款|某产品|重疾险A|医疗险A|"
    r"保险法|管理办法|监管|施行|令第|银保监|"
    r"保证.{0,6}(续保|赔付|返还)|返还|承诺|全额赔付|"
    r"\d{4}年|\d{1,2}月\d{1,2}日|生效|失效|"
    r"不返还|不属于|不予|不赔|都赔|全部覆盖|"
    r"所有|全部|一律|任何|都[是能可会有]|必然|一定|"
    r"您|你家|您家|你的")


class CandidateC:
    """Isolated reference implementation — never imported by runtime."""

    def __init__(self, judge_fn=None):
        self.judge_fn = judge_fn or (lambda claim, ev: {
            "decision": "KEEP_BASELINE", "reason": "no-judge"})

    def evaluate(self, claim, evidence_items, judge_raw=None,
                 judge_override=None, trace=None):
        """One claim -> (final_decision, trace). evidence_items =
        normalized support items (cs._items_from_evidence output)."""
        t = trace if trace is not None else {"claim": claim[:100]}
        bare = CIT.sub("", claim)
        # stage 1: baseline (deterministic, production read-only)
        anchors = cs.numeric_anchors(bare)
        ctype = cs.classify_claim(bare)
        base = cs.judge_claim(bare, ctype, anchors, evidence_items or [])
        baseline = base["support_status"]
        t["baseline"] = {"decision": baseline,
                         "reason": base["support_reason"][:50]}
        # stage 2: cited
        cited = bool(CIT.search(claim)) and bool(evidence_items)
        t["cited"] = {"decision": cited}
        # stage 3: hard prefilter
        pre_ok = not HARD.search(bare)
        t["hard_prefilter"] = {"decision": pre_ok}
        # stage 4: risk boundary
        risk_ok = not RISK.search(bare)
        t["risk_boundary"] = {"decision": risk_ok}
        # early deterministic pass / conjunction gate
        if baseline == "SUPPORTED":
            t["final_decision"] = "BASELINE_PASS"
            return "BASELINE_PASS", t
        if baseline == "NOT_APPLICABLE":
            # Phase-8 rule (C2 strict reading): a TYPE EXEMPTION must not
            # bypass the hard boundary — a hard-class claim exempted by
            # claim type (e.g. personalized RECOMMENDATION, BF3-01) is
            # vetoed here; only evidence-backed SUPPORTED passes.
            if HARD.search(bare) or RISK.search(bare):
                t["final_decision"] = "KEEP_BASELINE"
                t["block_stage"] = "prefilter-exempt-hardclass"
                return "KEEP_BASELINE", t
            t["final_decision"] = "BASELINE_PASS"
            return "BASELINE_PASS", t
        if baseline == "CONTRADICTED":
            t["final_decision"] = "KEEP_BASELINE"
            t["block_stage"] = "baseline-contradicted"
            return "KEEP_BASELINE", t
        if not (baseline == "PARTIAL" and cited and pre_ok and risk_ok):
            t["final_decision"] = "KEEP_BASELINE"
            t["block_stage"] = ("baseline-not-partial" if baseline !=
                                "PARTIAL" else
                                "cited" if not cited else
                                "hard_prefilter" if not pre_ok else
                                "risk_boundary")
            return "KEEP_BASELINE", t
        # stage 5: semantic judge
        if judge_override is not None:
            jd = judge_override
            t["semantic_judge"] = {"decision": jd, "reason": "INJECTED"}
        elif judge_raw is not None:
            jd = self._map_raw(judge_raw)
            t["semantic_judge"] = {"decision": jd, "reason": "cached-raw"}
        else:
            jd = self.judge_fn(claim, evidence_items)
            t["semantic_judge"] = {"decision": jd.get("decision"),
                                   "reason": jd.get("decision_reason",
                                                   "live")[:40]}
        if jd != "ALLOW_UPGRADE":
            t["final_decision"] = "KEEP_BASELINE"
            t["block_stage"] = "semantic_judge"
            return "KEEP_BASELINE", t
        # stage 6: post-gate (independent veto re-scan)
        post_ok = (not HARD.search(bare)) and (not RISK.search(bare)) \
            and baseline != "CONTRADICTED"
        t["post_gate"] = {"decision": post_ok}
        if not post_ok:
            t["final_decision"] = "KEEP_BASELINE"
            t["block_stage"] = "post_gate"
            return "KEEP_BASELINE", t
        t["final_decision"] = "ALLOW_UPGRADE"
        return "ALLOW_UPGRADE", t

    @staticmethod
    def _map_raw(raw):
        if not isinstance(raw, dict) or raw.get("error"):
            return "KEEP_BASELINE"
        if raw.get("exempt") or raw.get("contradiction"):
            return "KEEP_BASELINE"
        if raw.get("entailment") == "yes":
            c = raw.get("confidence")
            c = float(c) if isinstance(c, (int, float)) else 0.0
            return "ALLOW_UPGRADE" if c >= 0.7 else "UNCERTAIN"
        return "KEEP_BASELINE"


# ---------------- corpus loaders ----------------
def load_v2():
    cases = [json.loads(l) for l in open(os.path.join(
        REPO, "tests", "golden", "k29c_fix3_benchmark_v2_frozen.jsonl"),
        encoding="utf-8").readlines()[1:]]
    raws = {}
    for line in open(os.path.join(OBS, "k29c_fix3_phase5_replay.jsonl"),
                     encoding="utf-8"):
        r = json.loads(line)
        if r["slot"] == "flash" and r["rep"] == 1:
            raws[r["case_id"]] = r.get("raw")
    return cases, raws


def load_p6():
    cases = [json.loads(l) for l in open(os.path.join(
        REPO, "tests", "golden", "k29c_fix3_phase6_corpora.jsonl"),
        encoding="utf-8")]
    raws = {r["case_id"]: r.get("raw") for r in json.load(open(
        os.path.join(OBS, "k29c_fix3_phase6_raw_rows.json"),
        encoding="utf-8"))}
    return cases, raws


def load_golden():
    corpus = json.load(open(os.path.join(
        REPO, "tests", "golden", "claim-evidence-shadow.v1.json"),
        encoding="utf-8"))
    return [c for c in corpus["cases"]
            if not isinstance(c["expected"], dict)]


def load_blockers():
    """The four known blockers with their historical raws."""
    p6, p6r = load_p6()
    v2, v2r = load_v2()
    out = []
    for cid in ("F5-05",):
        c = next(x for x in v2 if x["case_id"] == cid)
        out.append(("F5-05", c["claim"], c["evidence"], v2r.get(cid)))
    for cid in ("BF1-16", "BF2-01", "BF3-01"):
        c = next(x for x in p6 if x["case_id"] == cid)
        out.append((cid, c["claim"], c["evidence"], p6r.get(cid)))
    return out


def items_of(evidence):
    return cs._items_from_evidence(evidence)
