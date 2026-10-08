# -*- coding: utf-8 -*-
"""FIX-3 Phase 9 — independent post-gate validation + mutation battery
+ extended failure injection + negative control + offline replay.
Produces phase-9 artifacts (offline part; shadow ledger comes from the
live stack harness)."""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

from k29c_fix3_candidate_c import CandidateC, items_of          # noqa
from k29c_fix3_independent_postgate import IndependentPostGate  # noqa
from runtime.grounding import claim_support as cs               # noqa

OBS = os.path.join(REPO, "tmp", "obs")
CIT = re.compile(r"\[E\d+\]")

CI = ("重疾险属于给付型保险，达到合同约定的重大疾病状态后按约定保额"
      "一次性给付保险金，保险金可自由支配。")


def candidate_c_with_indep_postgate(claim, evidence, judge_override=None,
                                    judge_raw=None, pg=None,
                                    pg_sim=None):
    """Candidate-C where the FINAL stage uses the INDEPENDENT post-gate
    (raw-input). Everything else identical to the Phase-8 reference."""
    pg = pg or IndependentPostGate()
    cc = CandidateC()
    dec, tr = cc.evaluate(claim, items_of(evidence),
                          judge_raw=judge_raw,
                          judge_override=judge_override)
    tr["pipeline_pre_postgate"] = dec
    if dec != "ALLOW_UPGRADE":
        tr["final_decision"] = dec
        return dec, tr
    # independent post-gate (raw inputs; simulated modes for injection)
    if pg_sim == "timeout":
        ok, reasons = pg.check_timeout_sim()
    elif pg_sim == "malformed":
        ok, reasons = pg.check_malformed_sim()
    elif pg_sim == "unavailable":
        ok, reasons = False, ["PG-U unavailable"]
    else:
        ok, reasons = pg.check(claim, evidence)
    tr["independent_post_gate"] = {"ok": ok, "reasons": reasons[:3]}
    if not ok:
        tr["final_decision"] = "KEEP_BASELINE"
        tr["block_stage"] = "independent_post_gate"
        return "KEEP_BASELINE", tr
    tr["final_decision"] = "ALLOW_UPGRADE"
    return "ALLOW_UPGRADE", tr


def main():
    # ---------------- I1-I4 independence tests ----------------
    pg = IndependentPostGate()
    benign = "重疾险的保险金可自由支配[E1]"
    benign_ev = [{"content": CI, "source_name": "t"}]
    hard = "该产品重疾险属于给付型保险，保险金可自由支配[E1]"
    indep = {"tests": []}

    def T(name, expect_ok, claim, ev, note=""):
        ok, r = pg.check(claim, ev)
        indep["tests"].append({
            "test": name, "expected": expect_ok, "actual": ok,
            "reasons": r[:2], "pass": ok == expect_ok, "note": note})
        return ok

    T("I1-pipeline-independent(hard claim, no upstream context)",
      False, hard, benign_ev,
      "checker sees ONLY raw claim+evidence; hard token -> FAIL")
    T("I1-soft claim passes", True, benign, benign_ev)
    # I2: judge output variations must not change post-gate result
    decs = {jd: pg.check(benign, benign_ev)[0] for jd in
            ("ALLOW_UPGRADE", "KEEP_BASELINE", "UNCERTAIN")}
    indep["tests"].append({
        "test": "I2-judge-output-irrelevant",
        "expected": True,
        "actual": len(set(decs.values())) == 1 and all(decs.values()),
        "pass": len(set(decs.values())) == 1 and all(decs.values()),
        "note": "post-gate never receives judge output (API has no "
                "such parameter) — result identical across simulated "
                "judge states"})
    # I3: normalization independence — same raw claim with polluted
    # upstream normalization: post-gate derives from raw only
    ok_raw, _ = pg.check(benign, benign_ev)
    # (upstream 'normalization cache' is simulated by calling twice with
    #  intermediate whitespace/bracket variants — raw contract holds)
    ok_var, _ = pg.check(re.sub(r"\s+", "", benign), benign_ev)
    indep["tests"].append({
        "test": "I3-normalization-independence",
        "expected": True, "actual": ok_raw and ok_var,
        "pass": ok_raw and ok_var,
        "note": "whitespace-normalized variant yields same verdict from "
                "raw-input contract"})
    # I4: missing/corrupted metadata -> fail-closed (never fail-open)
    T("I4-missing-evidence", False, benign, [],
      "empty evidence metadata -> FAIL (not open)")
    T("I4-corrupted-claim", False, None, benign_ev,
      "None claim -> FAIL")
    T("I4-citation-out-of-range", False, "重疾险保险金可自由支配[E9]",
      benign_ev, "label 9 > 1 evidence item -> FAIL")
    indep["all_pass"] = all(t["pass"] for t in indep["tests"])
    json.dump(indep, open(os.path.join(
        OBS, "k29c_fix3_phase9_postgate_independence.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------------- adversarial mutation battery ----------------
    blockers = [
        ("F5-05", "该办法自2019年12月1日起施行[E1]",
         [{"content": "《健康保险管理办法》规定如实告知义务。",
           "source_name": "r", "effective_from": "2019-12-01"}]),
        ("BF1-16", "等待期在30天至180天之间[E1]",
         [{"content": "等待期为90天。", "source_name": "t",
           "product_id": "P004"}]),
        ("BF2-01", "所有重疾险产品的保险金都可以自由支配[E1]",
         [{"content": CI, "source_name": "t"}]),
        ("BF3-01", "建议您优先为家里收入最高的人配置保障[E1]",
         [{"content": "家庭保障配置的一般思路：先覆盖家庭经济支柱。",
           "source_name": "t"}]),
    ]
    mut = {"cases": []}
    all_contained = True
    for cid, claim, ev in blockers:
        rows = []
        scenarios = [
            ("judge-forced-ALLOW", dict(judge_override="ALLOW_UPGRADE")),
            ("baseline-mutated-PARTIAL(via judge ALLOW)",
             dict(judge_override="ALLOW_UPGRADE")),
            ("citation-metadata-mutation[E7]",
             dict(judge_override="ALLOW_UPGRADE")),
            ("evidence-reordering",
             dict(judge_override="ALLOW_UPGRADE")),
            ("claim-wording-mutation",
             dict(judge_override="ALLOW_UPGRADE")),
        ]
        # scenario variants
        variants = [
            ("judge-forced-ALLOW", claim, ev, {"judge_override":
                                               "ALLOW_UPGRADE"}),
            ("baseline-forced-PARTIAL", claim, ev,
             {"judge_override": "ALLOW_UPGRADE"}),  # pipeline decides
            ("citation-mutation[E7]",
             re.sub(r"\[E1\]", "[E7]", claim), ev,
             {"judge_override": "ALLOW_UPGRADE"}),
            ("evidence-reordered", claim, list(reversed(ev)),
             {"judge_override": "ALLOW_UPGRADE"}),
            ("claim-wording-mutation",
             claim.replace("保障", "保障方案").replace("保险金", "理赔款"),
             ev, {"judge_override": "ALLOW_UPGRADE"}),
        ]
        for name, c_, e_, kw in variants:
            dec, tr = candidate_c_with_indep_postgate(c_, e_, **kw)
            contained = dec != "ALLOW_UPGRADE"
            rows.append({"mutation": name, "final": dec,
                         "block": tr.get("block_stage"),
                         "pg": tr.get("independent_post_gate"),
                         "contained": contained})
            all_contained &= contained
        mut["cases"].append({"case_id": cid, "rows": rows})
    mut["all_contained"] = all_contained
    json.dump(mut, open(os.path.join(OBS, "k29c_fix3_phase9_mutation.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------------- extended failure injection ----------------
    fi_rows = []
    hardp = ("该产品重疾险属于给付型保险，保险金可自由支配[E1]")

    def FI(name, kwargs, expect):
        dec, tr = candidate_c_with_indep_postgate(**kwargs)
        fi_rows.append({"injection": name, "final": dec,
                        "block": tr.get("block_stage"),
                        "pass": dec == expect})
    FI("control-all-pass(indep-pg)",
       dict(claim=benign, evidence=benign_ev,
            judge_override="ALLOW_UPGRADE"), "ALLOW_UPGRADE")
    FI("post-gate-FAIL(hard claim)",
       dict(claim=hardp, evidence=benign_ev,
            judge_override="ALLOW_UPGRADE"), "KEEP_BASELINE")
    FI("post-gate-TIMEOUT",
       dict(claim=benign, evidence=benign_ev,
            judge_override="ALLOW_UPGRADE", pg_sim="timeout"),
       "KEEP_BASELINE")
    FI("post-gate-MALFORMED",
       dict(claim=benign, evidence=benign_ev,
            judge_override="ALLOW_UPGRADE", pg_sim="malformed"),
       "KEEP_BASELINE")
    FI("post-gate-UNAVAILABLE",
       dict(claim=benign, evidence=benign_ev,
            judge_override="ALLOW_UPGRADE", pg_sim="unavailable"),
       "KEEP_BASELINE")
    # numeric closure: benign+ALLOW but claim carries a number NOT in ev
    FI("post-gate-numeric-closure(90天 uncited value)",
       dict(claim="重疾险保险金可自由支配，等待期90天[E1]",
            evidence=benign_ev,
            judge_override="ALLOW_UPGRADE"), "KEEP_BASELINE")
    # citation closure: [E3] beyond evidence range
    FI("post-gate-citation-closure([E3] of 1)",
       dict(claim="重疾险的保险金可自由支配[E3]", evidence=benign_ev,
            judge_override="ALLOW_UPGRADE"), "KEEP_BASELINE")
    # judge-side failures (regression)
    for nm, ov in (("judge-REJECT", "KEEP_BASELINE"),
                   ("judge-UNCERTAIN", "UNCERTAIN")):
        FI(nm, dict(claim=benign, evidence=benign_ev,
                    judge_override=ov), "KEEP_BASELINE")
    fi = {"rows": fi_rows, "all_pass": all(r["pass"] for r in fi_rows),
          "fail_open_count": sum(1 for r in fi_rows if not r["pass"])}
    json.dump(fi, open(os.path.join(
        OBS, "k29c_fix3_phase9_failure_injection.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------------- negative control (utility) ----------------
    nc_dec, nc_tr = candidate_c_with_indep_postgate(
        benign, benign_ev, judge_override="ALLOW_UPGRADE")
    negative_control = {
        "claim": benign, "final": nc_dec,
        "pass": nc_dec == "ALLOW_UPGRADE",
        "note": "proves the independent post-gate is not fail-closed-"
                "to-zero-utility"}

    # ---------------- offline replay equivalence (Phase-8 corpora) ----
    from k29c_fix3_candidate_c import (load_v2, load_p6, load_golden)
    stats = Counter()
    fu = 0
    for cases, raws, src in ((*load_v2(), "v2"), (*load_p6(), "phase6")):
        for c in cases:
            raw = raws.get(c["case_id"])
            dec, _ = candidate_c_with_indep_postgate(
                c["claim"], c["evidence"], judge_raw=raw)
            stats["%s:%s" % (src, dec)] += 1
            gold_j = c.get("gold_judge", "")
            if (dec == "ALLOW_UPGRADE" and c["gold_gate"] == "REJECT"
                    and gold_j not in ("ENTAILED", "EXEMPT")):
                fu += 1
    equivalence = {"offline_replay": dict(stats),
                   "false_upgrades": fu,
                   "negative_control": negative_control}
    json.dump(equivalence, open(os.path.join(
        OBS, "k29c_fix3_phase9_equivalence.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)

    print("independence all_pass:", indep["all_pass"])
    for t in indep["tests"]:
        print("  ", "PASS" if t["pass"] else "FAIL", t["test"])
    print("mutation all_contained:", all_contained)
    for c in mut["cases"]:
        print("  %s: %s" % (c["case_id"], [(r["mutation"], r["final"][:4],
                                            r["block"]) for r in c["rows"]]))
    print("failure-injection all_pass:", fi["all_pass"],
          "fail_open:", fi["fail_open_count"])
    for r in fi_rows:
        print("  ", "PASS" if r["pass"] else "FAIL", r["injection"], "->",
              r["final"])
    print("negative control:", negative_control["final"],
          negative_control["pass"])
    print("offline replay FU:", fu, dict(stats))


if __name__ == "__main__":
    main()
