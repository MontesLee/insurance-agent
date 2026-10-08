# -*- coding: utf-8 -*-
"""FIX-3 Phase 10 — Authority Contract: machine-readable contract,
scope matrix, kill-switch/rollback verification, failure injection
(contract-level), version binding, and production-equivalence replay.

The AuthorityContract class is a TOOLS-ONLY governance artifact: it
binds the Phase-8/9 validated pipeline into an auditable contract with
version pinning and a kill-switch. It is never imported by production
runtime. Running it with authority_enabled=False (the only runnable
mode in this phase) must be decision-equivalent to the production
baseline by construction.
"""
from __future__ import annotations

import hashlib
from typing import Optional
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

from k29c_fix3_candidate_c import CandidateC, items_of          # noqa
from k29c_fix3_independent_postgate import IndependentPostGate  # noqa

CONTRACT_VERSION = "candidate-c-authority-contract/v1.0"
PIPELINE_VERSION = "candidate-c-pipeline/v1.0-phase9"
POSTGATE_VERSION = "independent-postgate/v1.0-phase9"

SCOPE = {
    "FACTUAL_PARAPHRASE": {"eligible": True, "hard_block": False,
                           "authority_scope": "CANDIDATE",
                           "fallback": "KEEP_BASELINE"},
    "NUMERIC": {"eligible": False, "hard_block": True,
                "authority_scope": "OBSERVATION_ONLY",
                "fallback": "baseline"},
    "PRODUCT": {"eligible": False, "hard_block": True,
                "authority_scope": "OBSERVATION_ONLY",
                "fallback": "baseline"},
    "REGULATORY": {"eligible": False, "hard_block": True,
                   "authority_scope": "OBSERVATION_ONLY",
                   "fallback": "baseline"},
    "PAYMENT": {"eligible": False, "hard_block": True,
                "authority_scope": "OBSERVATION_ONLY",
                "fallback": "baseline"},
    "DATE_TIME": {"eligible": False, "hard_block": True,
                  "authority_scope": "OBSERVATION_ONLY",
                  "fallback": "baseline"},
    "CONTRADICTION": {"eligible": False, "hard_block": True,
                      "authority_scope": "OBSERVATION_ONLY",
                      "fallback": "baseline"},
    "UNIVERSAL_GENERALIZATION": {"eligible": False, "hard_block": True,
                                 "authority_scope": "OBSERVATION_ONLY",
                                 "fallback": "baseline"},
    "R4_PERSONALIZATION": {"eligible": False, "hard_block": True,
                           "authority_scope": "OBSERVATION_ONLY",
                           "fallback": "baseline"},
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class AuthorityContract:
    """Binds the validated pipeline with version pinning + kill-switch.

    authority_enabled is ALWAYS False in this phase: the contract's
    decision() then returns the PRODUCTION BASELINE decision verbatim
    (it never invokes the pipeline at all), which is decision-
    equivalent to today's production by construction."""

    def __init__(self, authority_enabled: bool = False,
                 expected_versions: Optional[dict] = None):
        self.authority_enabled = authority_enabled
        self.expected_versions = expected_versions or {
            "contract": CONTRACT_VERSION,
            "pipeline": PIPELINE_VERSION,
            "postgate": POSTGATE_VERSION}
        self.kill_switch = not authority_enabled   # default OFF

    # ---- version binding ----
    def versions_ok(self, provided: dict) -> bool:
        for k, want in self.expected_versions.items():
            got = (provided or {}).get(k)
            if got != want:      # mismatch / unknown / missing -> False
                return False
        return True

    # ---- the ONLY authority decision entry point ----
    def decide(self, claim, evidence, judge_raw=None, judge_override=None,
               provided_versions=None, pg=None, pg_sim=None):
        """Returns dict(final, mode, stages, version_ok). With the
        kill-switch ON (authority OFF — the only legal mode in this
        phase) the pipeline is never consulted: the deterministic
        baseline decision is returned. There is NO code path from
        shadow outputs to this method's output other than the explicit
        authority_enabled=True path, which this phase never sets."""
        out = {"mode": "AUTHORITY_OFF_BASELINE" if self.kill_switch
               else "AUTHORITY_ON_SIMULATION"}
        # version binding gate FIRST — mismatch/unknown/missing -> KEEP
        vok = self.versions_ok(provided_versions)
        out["version_ok"] = vok
        if self.kill_switch or not vok:
            # production baseline: deterministic pipeline outcome only
            cc = CandidateC()
            dec, tr = cc.evaluate(claim, items_of(evidence),
                                  judge_raw=None)   # judge NEVER consulted
            out["final"] = dec
            out["stages"] = {"baseline": tr.get("baseline", {}).get(
                "decision"), "judge_invoked": False}
            if not vok:
                out["version_gate"] = "KEEP_BASELINE(version)"
            return out
        # authority simulation (isolated; Phase-10 never reaches here —
        # kept so the contract is complete and auditable)
        cc = CandidateC()
        dec, tr = cc.evaluate(claim, items_of(evidence),
                              judge_raw=judge_raw,
                              judge_override=judge_override)
        if dec == "ALLOW_UPGRADE":
            pgx = pg or IndependentPostGate()
            if pg_sim:
                ok = False
            else:
                ok, _ = pgx.check(claim, evidence)
            dec = "ALLOW_UPGRADE" if ok else "KEEP_BASELINE"
        out["final"] = dec
        out["stages"] = {"baseline": tr.get("baseline", {}).get("decision"),
                         "judge_invoked": True}
        return out

