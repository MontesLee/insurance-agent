#!/usr/bin/env python3
"""Insurance Agent — Portfolio Demo (3 scenarios, REAL system).

Demo A: Normal Decision — full chain from client to report
Demo B: Evidence Tampering — 1-byte hash mutation → provenance DENY
Demo C: Insufficient Evidence — zero-overlap query → agent abstention

All three scenarios exercise the REAL runtime: real governance rules,
real provenance validators, real knowledge retrieval (WeKnora if
configured, deterministic engine otherwise). No faked results.

Usage: python demo/portfolio_demo/run_all.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import shutil
import copy

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, REPO)

WEKNORA_LIVE = bool(os.environ.get("INSURANCE_AGENT_WEKNORA_URL", "")
                    and os.environ.get("INSURANCE_AGENT_WEKNORA_API_KEY", "")
                    and os.environ.get(
                        "INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID", ""))


def hdr(title):
    print("\n" + "=" * 60)
    print("  %s" % title)
    print("=" * 60)


def sub(label):
    print("\n--- %s ---" % label)


def main() -> int:
    results = {}

    # ================================================================= #
    hdr("Insurance Agent Portfolio Demo")
    print("  Backend: %s" % ("REAL WeKnora v0.8.0 (live HTTP)"
                              if WEKNORA_LIVE else
                              "deterministic engine (offline mode)"))
    print("  Mode:    %s" % ("live" if WEKNORA_LIVE else "offline"))

    # ================================================================= #
    # Demo A — Normal Decision (full chain)
    # ================================================================= #
    hdr("[2] Demo A — Normal Decision")
    try:
        from runtime import orchestrator as orch
        from runtime import tasks as tk
        from runtime.state import case_state as cs

        wf = orch.load_workflow()
        fixture = json.load(open(os.path.join(
            REPO, "tests", "e2e", "fixtures", "case-full-chain.json"),
            encoding="utf-8"))
        seeds = copy.deepcopy(fixture["artifacts"])
        # Single medical requirement for a clean COMPLETE path
        reqs = seeds["requirement-analysis"].get("requirements") \
            or seeds["requirement-analysis"]["payload"]["requirements"]
        (seeds["requirement-analysis"] if "requirements"
         in seeds["requirement-analysis"]
         else seeds["requirement-analysis"]["payload"])["requirements"] = \
            [r for r in reqs if r.get("requirement_type") == "medical"]
        risks = seeds["risk-assessment"].get("risks") \
            or seeds["risk-assessment"]["payload"]["risks"]
        (seeds["risk-assessment"] if "risks" in seeds["risk-assessment"]
         else seeds["risk-assessment"]["payload"])["risks"] = \
            [r for r in risks if r.get("risk_category") == "R1"]

        root = tempfile.mkdtemp(prefix="pf_demo_a_", dir=os.path.join(
            REPO, "tmp"))
        try:
            state = orch.seed_case(wf, "DEMO-A", seeds,
                                   provided_by="upstream-dialogue")
            rep = orch.run(state, wf, gate_policy="stop",
                           checkpoint_root=root)
            while isinstance(rep, dict) and \
                    rep.get("status") == "PAUSED_NEEDS_REVIEW":
                orch.approve(state, rep["stopped_at"])
                rep = orch.run(state, wf, gate_policy="stop",
                              checkpoint_root=root)

            arts = state.get("artifacts", {})
            rec = (arts.get("product-recommendation") or {}) \
                .get("payload", {})
            ev = (arts.get("knowledge-evidence") or {}) \
                .get("payload", {}).get("evidence", [])
            rep_art = (arts.get("insurance-report") or {}) \
                .get("payload", {})

            print("  Terminal:       %s" % rep.get("status"))
            print("  Recommendation: %s" % rec.get("status"))
            print("  Primary:        %s" % (
                (rec.get("primary_recommendation") or {})
                .get("candidate_id", "—")))
            print("  Evidence items: %d" % len(ev))
            if ev:
                e = ev[0]
                print("  Evidence chain:")
                print("    document_id:  %s" % e.get("document_id"))
                print("    chunk_id:     %s…" %
                      str(e.get("chunk_id", ""))[:16])
                print("    source_id:    %s" % e.get("source_id"))
                print("    version_id:   %s" % e.get("version_id"))
                print("    authority:    %s" % e.get("authority_level"))
                print("    license:      %s" % e.get("license_status"))
                print("    hash:         %s…" %
                      str(e.get("content_hash", ""))[:16])
                print("    retrieved_at: %s" % e.get("retrieved_at"))

            # verify provenance on the real evidence
            from knowledge.governance import SourceRegistry
            from knowledge.governance.provenance import validate_provenance
            from knowledge.service import default_service
            reg = default_service().registry()
            ok, why = validate_provenance(ev[0], reg) if ev else (True, [])
            print("  Provenance:     %s" % ("VALID" if ok else
                                            "INVALID: %s" % why[:1]))

            results["demo_a"] = "PASS" if rep.get("status") == \
                "COMPLETED" else "FAIL"
        finally:
            shutil.rmtree(root, ignore_errors=True)
    except Exception as e:  # noqa: BLE001
        print("  ERROR: %s" % str(e)[:120])
        results["demo_a"] = "ERROR"

    # ================================================================= #
    # Demo B — Evidence Tampering (the key demo)
    # ================================================================= #
    hdr("[3] Demo B — Evidence Tampering Detection")
    try:
        from knowledge.governance import SourceRegistry
        from knowledge.governance.provenance import validate_provenance
        from knowledge.service import default_service, KnowledgeService

        svc = default_service()
        items, gov, dec, ctx = svc.build_evidence(
            "健康保险 等待期 免赔额")
        if not items:
            # offline mode with fixtures
            items, gov, dec, ctx = svc.build_evidence(
                "百万医疗险 等待期")

        if items:
            valid = items[0]
            print("  Original evidence:")
            print("    document_id:  %s" % valid["document_id"])
            print("    content_hash: %s…" %
                  valid["content_hash"][:16])
            ok_before, _ = validate_provenance(valid, svc.registry())
            print("    provenance:   %s" % ("VALID" if ok_before
                                            else "INVALID"))

            sub("Tampering: flip 1 byte in the content hash")
            tampered = copy.deepcopy(valid)
            tampered["content_hash"] = \
                ("0" if valid["content_hash"][0] != "0" else "1") \
                + valid["content_hash"][1:]
            print("    tampered:     %s…" % tampered["content_hash"][:16])

            ok_after, why = validate_provenance(tampered,
                                                svc.registry())
            print("\n  EXPECTED: Evidence rejected")
            print("  RESULT:   %s" % ("DENY" if not ok_after else
                                      "ACCEPTED (BUG!)"))
            print("  REASON:   %s" % (why[0] if why else "?"))
            results["demo_b"] = "PASS" if not ok_after else "FAIL"
        else:
            print("  ERROR: no evidence produced to tamper")
            results["demo_b"] = "ERROR"
    except Exception as e:  # noqa: BLE001
        print("  ERROR: %s" % str(e)[:120])
        results["demo_b"] = "ERROR"

    # ================================================================= #
    # Demo C — Insufficient Evidence (abstention)
    # ================================================================= #
    hdr("[4] Demo C — Insufficient Evidence / Abstention")
    try:
        from knowledge.service import default_service
        svc = default_service()
        query = "德甲联赛积分榜欧冠名额"
        print("  Query: %s" % query)
        print("  (completely unrelated to insurance knowledge)")

        items, gov, dec, ctx = svc.build_evidence(query)
        print("\n  Backend returned:  %d raw candidates" %
              gov.retrieval_metadata.get("backend_hits",
                                         gov.retrieval_metadata.get(
                                             "candidate_count", 0)))
        print("  Agent allowed:      %d governed evidence items" %
              len(items))
        print("  Status:             %s" % gov.status)

        print("\n  EXPECTED:    INSUFFICIENT_EVIDENCE")
        print("  RESULT:      %s" % ("ABSTAIN" if not items
                                     else "EVIDENCE PRODUCED (BUG!)"))
        print("  Recommendation:     withheld (no unsupported claim)")
        print("\n  Note: Abstention belongs to the Agent policy layer,")
        print("        not the retrieval backend. The backend may return")
        print("        keyword matches; the agent's relevance threshold")
        print("        and governance rules decide what becomes evidence.")
        results["demo_c"] = "PASS" if not items else "FAIL"
    except Exception as e:  # noqa: BLE001
        print("  ERROR: %s" % str(e)[:120])
        results["demo_c"] = "ERROR"

    # ================================================================= #
    hdr("PORTFOLIO DEMO COMPLETE")
    print("  Demo A (Normal Decision):       %s" % results.get("demo_a"))
    print("  Demo B (Evidence Tampering):    %s" % results.get("demo_b"))
    print("  Demo C (Insufficient Evidence): %s" % results.get("demo_c"))
    print("=" * 60)
    return 0 if all(v == "PASS" for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
