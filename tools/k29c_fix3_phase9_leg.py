# -*- coding: utf-8 -*-
"""FIX-3 Phase 9 — Candidate-C shadow leg callable (runtime observation
ONLY; imported by the ops launcher, never by production gates)."""
from __future__ import annotations


def cc_shadow_decision(claim_text, raw_evidence, judge_raw,
                       deterministic, pg):
    from k29c_fix3_candidate_c import CandidateC, items_of
    cc = CandidateC()
    dec, tr = cc.evaluate(claim_text, items_of(raw_evidence),
                          judge_raw=None)
    # pipeline decided stages from ITS OWN re-derivation; the live
    # shadow's judge_raw (if an ALLOW candidate) is applied at the
    # judge stage via override when the conjunction reaches it
    if dec == "KEEP_BASELINE" and tr.get("block_stage") == "semantic_judge":
        dec2, tr2 = cc.evaluate(claim_text, items_of(raw_evidence),
                                judge_raw=judge_raw)
        dec, tr = dec2, tr2
        tr["reused_live_judge_raw"] = True
    out = {"pipeline_pre_postgate": tr.get("final_decision"),
           "block_stage": tr.get("block_stage"),
           "baseline": tr.get("baseline", {}).get("decision")}
    if dec == "ALLOW_UPGRADE":
        ok, reasons = pg.check(claim_text, raw_evidence)
        out["independent_post_gate"] = {"ok": ok, "reasons": reasons[:2]}
        out["candidate_c_final"] = "ALLOW_UPGRADE" if ok else "KEEP_BASELINE"
    else:
        out["candidate_c_final"] = dec if dec != "BASELINE_PASS" else \
            "BASELINE_PASS"
    out["production_final"] = "REFUSED(gate)"  # production gate verdict
    return out
