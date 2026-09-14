#!/usr/bin/env python3
"""Generate the E2E seed fixture from the report-generation V2 dataset (Phase 7).

The E2E case starts at the point where the dialogue-driven PowerShell skills have already
produced their artifacts. We source those artifacts from the report-generation V2 manifest's
`v2_full_chain` case (which embeds a realistic ClientProfile / RequirementAnalysis /
RiskAssessment), so the end-to-end run is grounded in real data rather than invented facts.

Run:  python tests/e2e/_gen_e2e_fixture.py
"""
from __future__ import annotations

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
MANIFEST = os.path.join(REPO_ROOT, ".trae", "skills", "report-generation",
                        "evals", "cases", "v2-dataset-manifest.json")
FIX = os.path.join(HERE, "fixtures")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def main():
    os.makedirs(FIX, exist_ok=True)
    man = json.load(io.open(MANIFEST, encoding="utf-8"))
    case = [c for c in man["cases"] if c["name"] == "v2_full_chain"]
    if not case:
        raise SystemExit("v2_full_chain case not found in %s" % MANIFEST)
    inp = case[0]["input"]

    fixture = {
        "case_id": "CASE-E2E-001",
        "description": (
            "E2E seed: the three dialogue-driven upstream artifacts (ClientProfile / "
            "RequirementAnalysis / RiskAssessment), sourced from the report-generation V2 "
            "manifest's v2_full_chain case. The orchestrator seeds these as `provided` "
            "stages and then runs coverage-gap -> solution -> product-recommendation -> report."
        ),
        "provided_by": "upstream-dialogue",
        "artifacts": {
            "client-profile": inp["client_profile"],
            "requirement-analysis": inp["requirement_analysis"],
            "risk-assessment": inp["risk_analysis"],
        },
    }
    out = os.path.join(FIX, "case-full-chain.json")
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)

    log = os.path.join(FIX, "_gen_log.txt")
    io.open(log, "w", encoding="utf-8").write(
        "generated %s\nfrom %s\ncase=%s\n" % (out, MANIFEST, "v2_full_chain"))
    print("E2E FIXTURE GENERATED ->", out)


if __name__ == "__main__":
    main()
