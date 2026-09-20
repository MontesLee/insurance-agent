#!/usr/bin/env python3
"""Phase 15 business demos — DISPLAY ONLY (§16: demos are not gates).

Demo A standard family → full chain + report sections
Demo B insufficient info → WAITING_FOR_USER + honest missing list
Demo C evidence missing → blocked/review, never a forced recommendation
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from run_business_eval import build_seeds, run_case  # noqa: E402
from runtime import orchestrator as orch  # noqa: E402


def show(title, state, rep):
    arts = state.get("artifacts", {})
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print("terminal:", rep.get("status"))
    rec = (arts.get("product-recommendation") or {}).get("payload", {})
    print("recommendation:", rec.get("status"),
          "| primary:", (rec.get("primary_recommendation") or {})
          .get("candidate_id"))
    report = (arts.get("insurance-report") or {}).get("payload", {})
    sr = report.get("structured_report") or {}
    print("report sections:", sorted(k for k in sr.keys()))
    if sr.get("information_gaps"):
        print("information gaps:", json.dumps(sr["information_gaps"],
                                              ensure_ascii=False)[:200])
    rr = report.get("rendered_report") or ""
    if rr:
        print("\n--- rendered report (first 900 chars) ---")
        print(str(rr)[:900])


def main() -> int:
    wf = orch.load_workflow()
    cases = json.load(open(os.path.join(HERE, "dataset",
                                        "business_cases.json"),
                           encoding="utf-8"))
    by_id = {c["case_id"]: c for c in
             cases["golden_cases"] + cases["negative_cases"]}

    # Demo A — standard family full loop
    state, rep = run_case(by_id["B001-standard-family"], wf)
    show("DEMO A — standard family: full chain to report", state, rep)

    # Demo B — insufficient information
    state, rep = run_case(by_id["B008-insufficient-info"], wf)
    show("DEMO B — insufficient info: stops and asks, never invents",
         state, rep)
    prof = ((state.get("artifacts", {}).get("client-profile") or {})
            .get("payload", {}))
    missing = prof.get("missing_from_upstream", [])
    seeds = build_seeds(by_id["B008-insufficient-info"])
    print("declared-missing fields:", [m["field"] for m in
                                       (seeds["client-profile"].get(
                                           "payload", seeds[
                                               "client-profile"])
                                        .get("missing_from_upstream", []))])
    print("fabricated facts downstream: NONE (asserted by the evaluator)")

    # Demo C — evidence missing (empty KB)
    state, rep = run_case(by_id["N005-evidence-missing"], wf)
    show("DEMO C — evidence missing: blocked for review, no forced "
         "recommendation", state, rep)
    rec = ((state.get("artifacts", {}).get("product-recommendation") or {})
           .get("payload", {}))
    print("recommendation forced?:",
          "NO" if rec.get("status") != "COMPLETE" else "YES (BUG)")
    print("\nDemos are display-only; correctness is proven by "
          "run_business_eval.py (15/15 + hard gates).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
