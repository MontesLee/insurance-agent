# -*- coding: utf-8 -*-
"""FIX-3 Phase 5 — Frozen Benchmark v2 validation through the REAL
production claim_support.check() (not the offline shadow replicas).

Arms = flag configurations on the production code:
  C1  = levers OFF (pre-FIX-3 behavior + unconditional debt hardening)
  B   = exemption_v2 ON
  D   = premise_scan ON
  BD  = both ON

Hard gates (OD-FIX3-6): candidate-ADDED escapes (vs C1) must be 0 for
F2 / F4-numeric / R3 / R4 / numeric / contradiction / product /
date-time classes. Output: tmp/obs/k29c_fix3_phase5_validation.json
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from runtime.grounding import claim_support as cs   # noqa: E402
from runtime.grounding import gate as ggate         # noqa: E402

V2 = os.path.join(REPO, "tests", "golden",
                  "k29c_fix3_benchmark_v2_frozen.jsonl")
OUT = os.path.join(REPO, "tmp", "obs", "k29c_fix3_phase5_validation.json")

RISK_RES = {
    "numeric": re.compile(r"\d"),
    "product": re.compile(r"P0\d{2}|demo-|该产品|这款|某产品|百万医疗险|重疾险A"),
    "regulatory": re.compile(r"保险法|管理办法|监管|施行|令第|银保监"),
    "payout": re.compile(r"续保|返还|赔付|承诺|给付"),
}


def rules(arm):
    r = copy.deepcopy(ggate.load_rules())
    r.setdefault("claim_support", {})["enabled"] = True
    r["claim_support"]["exemption_v2"] = {"enabled": arm in ("B", "BD")}
    r["claim_support"]["premise_scan"] = {"enabled": arm in ("D", "BD")}
    return r


def risk_class(c):
    out = [k for k, rx in RISK_RES.items() if rx.search(c["claim"])]
    out += [f for f in c.get("high_risk_flags", []) if f not in out]
    return set(out)


def main():
    cases = [json.loads(l) for l in open(V2, encoding="utf-8").readlines()[1:]]
    arms = ["C1", "B", "D", "BD"]
    rows = []
    for c in cases:
        # v2 evidence dicts already match _items_from_evidence input
        ev = c["evidence"]
        row = {"case_id": c["case_id"], "family": c["family"],
               "gold": c["expected_gate"], "risk": sorted(risk_class(c))}
        for arm in arms:
            try:
                row[arm] = cs.check(c["claim"], ev, rules(arm))["ok"]
            except Exception as e:  # noqa: BLE001 — fail-closed record
                row[arm] = False
                row["error_%s" % arm] = repr(e)[:80]
        rows.append(row)

    agg = {}
    for arm in arms:
        esc = defaultdict(list)
        acc = defaultdict(int)
        for r in rows:
            if r[arm] and r["gold"] == "REJECT":
                esc[r["family"]].append(r["case_id"])
            if r[arm] and r["gold"] == "ACCEPT":
                acc[r["family"]] += 1
        agg[arm] = {
            "escapes_by_family": {k: v for k, v in esc.items()},
            "total_escapes": sum(len(v) for v in esc.values()),
            "escapes": sorted(x for v in esc.values() for x in v),
            "accepts_by_family": dict(acc)}
    # candidate-ADDED escapes vs C1
    c1_esc = set(agg["C1"]["escapes"])
    for arm in ("B", "D", "BD"):
        added = sorted(set(agg[arm]["escapes"]) - c1_esc)
        closed = sorted(c1_esc - set(agg[arm]["escapes"]))
        agg[arm]["added_escapes_vs_C1"] = added
        agg[arm]["closed_escapes_vs_C1"] = closed

    # hard gates (OD-FIX3-6)
    gates = {}
    for arm in ("B", "D", "BD"):
        added = agg[arm]["added_escapes_vs_C1"]
        added_rows = [r for r in rows if r["case_id"] in added]
        gates[arm] = {
            "candidate_added_escapes": len(added),
            "numeric_escape": sum(1 for r in added_rows
                                  if "numeric" in r["risk"]
                                  or "number" in r["risk"]),
            "contradiction_escape": sum(
                1 for r in added_rows if r["family"] == "F2"),
            "product_escape": sum(1 for r in added_rows
                                  if "product" in r["risk"]),
            "regulatory_escape": sum(1 for r in added_rows
                                      if "regulatory" in r["risk"]),
            "date_escape": sum(1 for r in added_rows
                               if "date" in str(r["risk"])),
            "F4_escape": sum(1 for r in added_rows if r["family"] == "F4"),
            "HARD_GATE": "PASS" if not added else "FAIL"}
    # R3/R4: no benchmark replay here (A-fixed data) — covered by the
    # simulation tool on A-fixed records; this gate reports v2-only.

    out = {"ts": "2026-10-02", "n": len(rows), "per_arm": agg,
           "hard_gates": gates, "rows": rows}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("n =", len(rows))
    for arm in arms:
        a = agg[arm]
        print("%-3s escapes=%d %s | accepts=%s" % (
            arm, a["total_escapes"],
            {k: len(v) for k, v in a["escapes_by_family"].items()},
            a["accepts_by_family"]))
        if arm != "C1":
            g = gates[arm]
            print("     added=%d closed=%d HARD_GATE=%s" % (
                len(a["added_escapes_vs_C1"]),
                len(a["closed_escapes_vs_C1"]), g["HARD_GATE"]))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
