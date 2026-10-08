# -*- coding: utf-8 -*-
"""K.29-C FIX-3 Phase 3 — B+D four-arm offline simulation (OFFLINE ONLY).

Arms:
  C1  = current rule (every fact clause SUPPORTED)
  B   = C3v2 guarded guidance exemption (whitelist + hard guards)
  D   = recommendation premise defense: clauses typed C-RECOMMENDATION /
        C-UNCERTAIN carrying numeric anchors are re-judged under full
        C-FACT rules (premise must be SUPPORTED) — F-1 closure
  BD  = B and D combined

Surfaces: golden-104 (attack) · v2-frozen-82 (labels) · taxonomy-134
(record flips) · probes-7 · B-arm answer scan (D exposure).

Reads production code (shadow judge) READ-ONLY; no production writes.
Output: tmp/obs/k29c_fix3_simulation.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

from k29c_calibration_study import (  # noqa: E402
    judge, clause_guarded_guidance_v2, norm, NUM_RE, HIGH_RISK_RE,
    META_RE, GUIDE_RE)
from runtime.grounding.shadow.claims import split_claims  # noqa: E402
from runtime.grounding import claim_support as cs         # noqa: E402

GOLDEN = os.path.join(REPO, "tests", "golden", "claim-evidence-shadow.v1.json")
V2 = os.path.join(REPO, "tests", "golden", "k29c_fix3_benchmark_v2_frozen.jsonl")
TAX = os.path.join(REPO, "tests", "golden", "k29c_claim_taxonomy.json")
OUT = os.path.join(REPO, "tmp", "obs", "k29c_fix3_simulation.json")
ARMS = ["C1", "B", "D", "BD"]


def clause_pass(arm, text, ctype, anchors, evidence, verdict=None):
    """One clause under one arm."""
    exempt_type = ctype not in ("C-FACT",)
    d_applies = (arm in ("D", "BD")
                 and ctype in ("C-RECOMMENDATION", "C-UNCERTAIN")
                 and (anchors or NUM_RE.search(text)))
    if d_applies:
        # premise defense: judge under full C-FACT rules (fails closed)
        v = verdict if verdict is not None else judge(
            text, "C-FACT", anchors, evidence)
        return v == "SUPPORTED"
    if exempt_type:
        return True                       # unchanged type exemption path
    if verdict is None:
        verdict = judge(text, ctype, anchors, evidence)
    if arm in ("B", "BD") and clause_guarded_guidance_v2(text, anchors):
        return True                       # guarded exemption
    return verdict == "SUPPORTED"


def case_pass(arm, claim_text, evidence, verdicts=None):
    clauses = split_claims(cs._CITATION_RE.sub("", claim_text))
    if not clauses:
        return True
    for i, c in enumerate(clauses):
        v = verdicts[i] if verdicts else None
        if not clause_pass(arm, c["claim_text"], c["claim_type"],
                           c["anchors"], evidence, v):
            return False
    return True


def clause_verdicts(claim_text, evidence):
    out = []
    for c in split_claims(cs._CITATION_RE.sub("", claim_text)):
        if c["claim_type"] == "C-FACT":
            out.append(judge(c["claim_text"], c["claim_type"],
                             c["anchors"], evidence))
        else:
            out.append(None)
    return out


def risk_profile(text):
    p = []
    if NUM_RE.search(text):
        p.append("numeric")
    if re.search(r"P0\d{2}|demo-|这款|该产品|某产品|P00\d", text):
        p.append("product")
    if re.search(r"保险法|管理办法|监管|银保监|令第|施行|办法", text):
        p.append("regulatory")
    if re.search(r"保证.{0,6}(续保|赔付|返还)|承诺", text):
        p.append("payout")
    return p


def main():
    out = {"ts": "2026-10-02", "arms": ARMS}

    # ---------- surface 1: golden attack corpus ----------
    corpus = json.load(open(GOLDEN, encoding="utf-8"))
    gold_rows = []
    for case in corpus["cases"]:
        if isinstance(case["expected"], dict):
            continue
        ev = case.get("evidence") or []
        vs = clause_verdicts(case["claim_text"], ev)
        row = {"case_id": case["case_id"], "class": case["class"],
               "expected": case["expected"]}
        for arm in ARMS:
            row[arm] = case_pass(arm, case["claim_text"], ev, vs)
        gold_rows.append(row)
    gold = {}
    for arm in ARMS:
        esc = [r for r in gold_rows if r[arm] and r["expected"] in
               ("UNSUPPORTED", "CONTRADICTED")]
        fref = [r for r in gold_rows if not r[arm] and
                r["expected"] == "SUPPORTED"]
        gold[arm] = {"escape": len(esc),
                     "escape_cases": [r["case_id"] for r in esc],
                     "false_refusal": len(fref)}
    out["golden"] = {"n": len(gold_rows), "per_arm": gold}

    # ---------- surface 2: v2 frozen ----------
    v2 = [json.loads(l) for l in open(V2, encoding="utf-8").readlines()[1:]]
    v2_rows = []
    for c in v2:
        ev = c["evidence"]
        vs = clause_verdicts(c["claim"], ev)
        row = {"case_id": c["case_id"], "family": c["family"],
               "expected_gate": c["expected_gate"],
               "flags": c.get("high_risk_flags", [])}
        for arm in ARMS:
            row[arm] = case_pass(arm, c["claim"], ev, vs)
        v2_rows.append(row)
    v2_agg = {}
    for arm in ARMS:
        esc_by_fam = defaultdict(list)
        for r in v2_rows:
            if r[arm] and r["expected_gate"] == "REJECT":
                esc_by_fam[r["family"]].append(r["case_id"])
        acc_by_fam = defaultdict(int)
        for r in v2_rows:
            if r[arm] and r["expected_gate"] == "ACCEPT":
                acc_by_fam[r["family"]] += 1
        v2_agg[arm] = {
            "escape_by_family": {k: v for k, v in esc_by_fam.items()},
            "total_escape": sum(len(v) for v in esc_by_fam.values()),
            "accept_by_family": {k: v for k, v in acc_by_fam.items()},
            "F2_escape": len(esc_by_fam.get("F2", [])),
            "F4_escape": len(esc_by_fam.get("F4", [])),
            "F5_escape": len(esc_by_fam.get("F5", [])),
            "F6_escape": len(esc_by_fam.get("F6", []))}
    out["v2"] = {"n": len(v2_rows), "per_arm": v2_agg, "rows": v2_rows}

    # ---------- surface 3: taxonomy record flips ----------
    tax = json.load(open(TAX, encoding="utf-8"))
    claims_by_rec = defaultdict(list)
    for c in tax["claims"]:
        claims_by_rec[(c["case_id"], c["slot"])].append(c)
    bench = {}
    for f, slot in (("A_fixed_main_all", "main"), ("A_fixed_flash_all", "flash")):
        recs = [json.loads(l) for l in open(os.path.join(
            REPO, "tmp", "obs", "k29b", f + ".jsonl"), encoding="utf-8")]
        refuted = [r for r in recs
                   if r.get("failure_reason") == "citation_gate_rejected"]
        flips = {a: [] for a in ARMS}
        newly = {a: [] for a in ARMS}
        for r in refuted:
            cl = claims_by_rec.get((r["case_id"], slot), [])
            if any("no_citation" in v for v in (r.get("gate_violations") or [])):
                continue
            for a in ARMS:
                ok = all(clause_pass(a, c["text"], "C-FACT",
                                     cs.numeric_anchors(
                                         cs._CITATION_RE.sub("", c["text"])),
                                     None, norm(c["support"]))
                         for c in cl)
                if ok and cl:
                    flips[a].append(r["case_id"])
                    for c in cl:
                        if norm(c["support"]) != "SUPPORTED":
                            newly[a].append(c)
        bench[slot] = {
            "refused": len(refuted),
            "flips": {a: {"n": len(v), "cases": v}
                      for a, v in flips.items()},
            "newly_passing": {a: {
                "n": len(v),
                "risk": dict(Counter(
                    p for c in v for p in risk_profile(c["text"]))),
                "by_type": dict(Counter(c["type"] for c in v))}
                for a, v in newly.items()}}
    out["benchmark"] = bench

    # ---------- surface 4: probes ----------
    probes = []
    for pr in tax["c3_c4_probes"]:
        ev = pr["evidence"]
        row = {"id": pr["id"], "target": pr["target"],
               "expected_gate": pr["expected_gate"]}
        for a in ARMS:
            row[a] = case_pass(a, pr["claim"], ev)
        probes.append(row)
    out["probes"] = probes

    # ---------- surface 5: B-arm answers (D exposure scan) ----------
    d_exposure = 0
    for f in ("B_main_all", "B_flash_all"):
        for line in open(os.path.join(REPO, "tmp", "obs", "k29b",
                                      f + ".jsonl"), encoding="utf-8"):
            r = json.loads(line)
            if r.get("grounding") != "generated":
                continue
            for c in split_claims(r.get("answer") or ""):
                if (c["claim_type"] in ("C-RECOMMENDATION", "C-UNCERTAIN")
                        and NUM_RE.search(c["claim_text"])):
                    d_exposure += 1
    out["d_exposure_B_arm_answers"] = d_exposure

    # ---------- summary ----------
    print("=== GOLDEN (attack surface, n=%d) ===" % out["golden"]["n"])
    for a in ARMS:
        g = gold[a]
        print("  %-3s escape=%d %-24s false_refusal=%d" % (
            a, g["escape"], str(g["escape_cases"])[:24], g["false_refusal"]))
    print("=== V2 FROZEN (n=%d) ===" % out["v2"]["n"])
    for a in ARMS:
        v = v2_agg[a]
        print("  %-3s escapes: F2=%d F4=%d F5=%d F6=%d total=%d | accepts(F1/F3): %s" % (
            a, v["F2_escape"], v["F4_escape"], v["F5_escape"], v["F6_escape"],
            v["total_escape"],
            {k: x for k, x in v["accept_by_family"].items()
             if k in ("F1", "F3")}))
    print("=== BENCHMARK FLIPS ===")
    for slot, b in bench.items():
        print("  slot=%s refused=%d" % (slot, b["refused"]))
        for a in ARMS:
            print("    %-3s flips=%d %s | newly risk=%s" % (
                a, b["flips"][a]["n"], ",".join(b["flips"][a]["cases"])[:30],
                b["newly_passing"][a]["risk"]))
    print("=== PROBES ===")
    for p in probes:
        print("  %-8s expect=%-6s C1=%-5s B=%-5s D=%-5s BD=%-5s" % (
            p["id"], p["expected_gate"], p["C1"], p["B"], p["D"], p["BD"]))
    print("D exposure (REC+number clauses in B-arm answers):", d_exposure)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
