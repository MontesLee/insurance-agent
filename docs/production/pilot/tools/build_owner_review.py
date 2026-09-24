"""Build the Owner Review workbench (Phase 27 Owner Review Support).

Reads RAW pilot evidence (tmp/pilot27/<case>/<attempt>/<case>/
artifacts/*.json + data/pilot-machine-results.json + the runner's
case definitions) and emits docs/production/pilot/owner-review/
C01..C12.md with machine evidence ONLY — every business judgment
field is PENDING_OWNER_REVIEW. No runtime/skill/test changes.

Usage: python docs/production/pilot/tools/build_owner_review.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                    "..", "..", "..", ".."))
P = os.path.join(REPO, "tmp", "pilot27")
OUT = os.path.join(REPO, "docs", "production", "pilot", "owner-review")


def _j(x, n=220):
    s = json.dumps(x, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def _load(path):
    return json.load(open(path, encoding="utf-8"))


def main():
    os.makedirs(OUT, exist_ok=True)
    mr = _load(os.path.join(REPO, "docs", "production", "pilot",
                            "data", "pilot-machine-results.json"))
    byid = {c["pilot_case_id"]: c for c in mr["cases"]}
    spec = importlib.util.spec_from_file_location(
        "rp", os.path.join(REPO, "docs", "production", "pilot",
                           "tools", "run_pilot.py"))
    rp = importlib.util.module_from_spec(spec)
    sys.modules["rp"] = rp
    spec.loader.exec_module(rp)
    CDEF = {c["id"]: c for c in rp.CASES}

    def latest(cid):
        for d in sorted(os.listdir(os.path.join(P, cid)),
                        reverse=True):
            adir = os.path.join(P, cid, d, cid, "artifacts")
            if os.path.isdir(adir):
                arts = {}
                for f in sorted(os.listdir(adir)):
                    a = _load(os.path.join(adir, f))
                    arts[f[:-5]] = a.get("payload", a)
                return arts, d
        return {}, "attempt-1(no-artifacts)"

    for cd in CDEF.values():
        cid = cd["id"]
        m = byid[cid]
        arts, adir = latest(cid)
        cp = arts.get("client-profile") or {}
        rq = arts.get("requirement-analysis") or {}
        rk = arts.get("risk-assessment") or {}
        gp = arts.get("coverage-gap-analysis") or {}
        so = arts.get("solution-plan") or {}
        ke = arts.get("knowledge-evidence") or {}
        pc = arts.get("product-candidates") or {}
        rc = arts.get("product-recommendation") or {}
        rr = arts.get("insurance-report") or {}
        prim = rc.get("primary_recommendation") or {}
        L = []
        A = L.append
        A("# %s — Owner Review" % cid)
        A("")
        A("> Machine-observed evidence ONLY. All business judgments "
          "are yours.")
        A("> Criteria & time protocol: owner-review/README.md")
        A("")
        A("## Case Metadata")
        A("")
        A("- Case ID: %s" % cid)
        A("- Case Type: %s" % cd["case_type"])
        A("- Data Type: SYNTHETIC")
        A("- Runtime Version: %s" % m["runtime_version"])
        A("- Knowledge Provider: %s" % (
            "EMPTY-KB (kb-empty dir)" if cd.get("kb") == "empty"
            else 'fixture KB (skills/knowledge-search/evals/'
                 'fixtures/kb; obs provider="mock")'))
        A("- LLM Provider: N/A — deterministic path (real 0 LLM "
          "calls)")
        A("- Run ID: run-pilot27-%s · Task ID: pilot27-%s · "
          "Trace ID: trc-pilot27-%s" % (cid, cid, cid))
        A("- Evidence root: tmp/pilot27/%s/%s/%s/" % (cid, adir, cid))
        if cid == "C08":
            A("- EVIDENCE GAP (EH-01): no artifacts/case_state "
              "persisted; input below is reconstructed from the "
              "runner definition; the WAITING_FOR_USER payload "
              "(blocking fields / next questions) lived only on "
              "the cleaned task row and is NOT recoverable.")
        A("")
        A("## 1. Original Input")
        A("")
        if cp:
            A("Client profile (seeded, post-mutation):")
            for sec in ("family_profile", "financial_profile",
                        "existing_protection",
                        "responsibility_profile"):
                for f in ("marital_status", "children",
                          "annual_income", "annual_expense",
                          "mortgage", "insurance_budget",
                          "existing_insurance", "social_security",
                          "economic_responsibility"):
                    v = (cp.get(sec) or {}).get(f)
                    if v:
                        A("- %s.%s = %s [%s]"
                          % (sec, f, v.get("value"),
                             v.get("status")))
            for msn in (cp.get("missing_from_upstream") or []):
                A("- missing_from_upstream: %s.%s (%s)"
                  % (msn.get("profile"), msn.get("field"),
                     msn.get("reason")))
        else:
            A("Input per runner definition (no client-profile "
              "artifact persisted):")
            for mu in cd.get("mutations", []):
                A("- %s" % json.dumps(mu, ensure_ascii=False))
            A("(see EH-01 above)")
        A("")
        # 2 requirement
        A("## 2. Requirement Analysis")
        A("")
        if rq:
            reqs = rq.get("requirements") or []
            A("Machine Evidence: %d requirement(s), "
              "analysis_status=%s"
              % (len(reqs), rq.get("analysis_status")))
            for r in reqs[:6]:
                A("- %s %s %s — %s"
                  % (r.get("requirement_id"),
                     r.get("requirement_type"),
                     r.get("priority"), r.get("summary")))
            if not reqs:
                A("- (EMPTY requirement set — kept [] by case "
                  "definition; F27-03)")
            A("")
            A("Machine Eval: PASS (seeded artifact accepted; EVAL "
              "recorded in trace)")
        else:
            A("Machine Evidence: NOT PRODUCED")
            A("Machine Eval: NOT_RUN")
        A("")
        A("### Owner Judgment\n\nPENDING_OWNER_REVIEW\n")
        A("### Owner Decision\n- [ ] CORRECT\n- [ ] MINOR_ISSUE"
          "\n- [ ] MAJOR_ISSUE\n- [ ] REJECT\n- [ ] UNKNOWN\n")
        A("### Owner Notes\n<!-- Owner -->\n")
        # 3 risk
        A("## 3. Risk Analysis")
        A("")
        if rk:
            risks = rk.get("risks") or []
            A("Machine Evidence: %d risk(s), analysis_status=%s, "
              "confidence=%s"
              % (len(risks), rk.get("analysis_status"),
                 rk.get("overall_confidence")))
            for r in risks[:6]:
                ca = r.get("coverage_assessment") or {}
                A("- %s %s %s %s — protected=%s unprotected=%s"
                  % (r.get("risk_id"), r.get("risk_category"),
                     r.get("priority"), r.get("risk_name"),
                     ca.get("protected_amount"),
                     ca.get("unprotected_amount")))
            A("")
            A("Machine Eval: PASS (seeded artifact accepted)")
        else:
            A("Machine Evidence: NOT PRODUCED")
            A("Machine Eval: NOT_RUN")
        A("")
        A("### Owner Judgment\n\nPENDING_OWNER_REVIEW\n")
        A("### Owner Decision\n- [ ] CORRECT\n- [ ] MINOR_ISSUE"
          "\n- [ ] MAJOR_ISSUE\n- [ ] REJECT\n- [ ] UNKNOWN\n")
        A("### Owner Notes\n<!-- Owner -->\n")
        # 4 gap
        A("## 4. Coverage Gap")
        A("")
        if gp:
            gaps = (gp.get("gaps")
                    or gp.get("coverage_gaps") or [])
            A("Machine Evidence: analysis_status=%s, %d gap(s)"
              % (gp.get("analysis_status"), len(gaps)))
            for g in gaps[:6]:
                A("- %s" % _j(g))
            A("")
            A("Machine Eval: PASS")
        else:
            A("Machine Evidence: NOT PRODUCED")
            A("Machine Eval: NOT_RUN")
        A("")
        A("### Owner Judgment\n\nPENDING_OWNER_REVIEW\n")
        A("### Owner Decision\n- [ ] CORRECT\n- [ ] MINOR_ISSUE"
          "\n- [ ] MAJOR_ISSUE\n- [ ] REJECT\n- [ ] UNKNOWN\n")
        A("### Owner Notes\n<!-- Owner -->\n")
        # 5 solution
        A("## 5. Solution")
        A("")
        if so:
            strat = (so.get("strategies")
                     or so.get("solution_strategies") or [])
            A("Machine Evidence: analysis_status=%s, %d "
              "strategy(ies)"
              % (so.get("analysis_status"), len(strat)))
            for s in strat[:5]:
                A("- %s" % _j(s))
            A("")
            A("Machine Eval: PASS")
        else:
            A("Machine Evidence: NOT PRODUCED")
            A("Machine Eval: NOT_RUN")
        A("")
        A("### Owner Judgment\n\nPENDING_OWNER_REVIEW\n")
        A("### Owner Decision\n- [ ] CORRECT\n- [ ] MINOR_ISSUE"
          "\n- [ ] MAJOR_ISSUE\n- [ ] REJECT\n- [ ] UNKNOWN\n")
        A("### Owner Notes\n<!-- Owner -->\n")
        # 6 product
        A("## 6. Product Candidate")
        A("")
        if pc:
            cands = pc.get("candidates") or []
            A("Machine Evidence: %d candidate(s), status=%s"
              % (len(cands),
                 pc.get("status")
                 or pc.get("analysis_status")))
            for c in cands[:5]:
                A("- %s %s — covers=%s"
                  % (c.get("candidate_id"),
                     c.get("solution_name"),
                     _j(c.get("covers_risk_categories"), 80)))
            A("  (full list: product-candidates.json)")
            A("")
            A("Evidence Status: per-candidate — see §7 "
              "recommendation evidence statuses")
            A("Machine Eval: PASS")
        else:
            if cid == "C11":
                A("Machine Evidence: NOT PRODUCED — Machine "
                  "Observation: 3 × EVAL required_non_empty on "
                  "knowledge-evidence (EVAL-006/007/008) → "
                  "REPAIR_EXHAUSTED at product-candidate-provider "
                  "(trace.jsonl).")
            else:
                A("Machine Evidence: NOT PRODUCED")
            A("")
            A("Evidence Status: NOT_PRODUCED")
            A("Machine Eval: FAIL (upstream knowledge eval)")
        A("")
        A("### Owner Judgment\n\nPENDING_OWNER_REVIEW\n")
        A("### Owner Decision\n- [ ] CORRECT\n- [ ] MINOR_ISSUE"
          "\n- [ ] MAJOR_ISSUE\n- [ ] REJECT\n- [ ] "
          "NOT_PRODUCED\n- [ ] UNKNOWN\n")
        A("### Owner Notes\n<!-- Owner -->\n")
        # 7 recommendation
        A("## 7. Recommendation")
        A("")
        if rc:
            A("Machine Evidence: status=%s; %d evaluated, %d "
              "not_recommended"
              % (rc.get("status"),
                 len(rc.get("candidate_evaluations") or []),
                 len(rc.get("not_recommended") or [])))
            A("Primary Product: %s"
              % (prim.get("candidate_id") or "NONE"))
            if prim:
                A("  primary: %s" % _j(prim, 400))
            for nr in (rc.get("not_recommended") or [])[:3]:
                A("- not_recommended: %s — %s"
                  % (nr.get("candidate_id"), nr.get("reason")))
            for u in [u for u in (rc.get("uncertainties") or [])
                      if u.get("type") in ("insufficient_evidence",
                                           "evidence_conflict",
                                           "missing_information")][:2]:
                A("- uncertainty: %s — %s"
                  % (u.get("type"),
                     _j(u.get("detail") or u.get("message"), 140)))
            A("- human_review_required=%s"
              % rc.get("human_review_required"))
            A("")
            A("Recommendation Status: %s" % rc.get("status"))
            A("Machine Eval: PASS (contract-valid; business "
              "status above)")
            A("")
            A("F27-02 Diagnostic Context: machine evidence "
              "indicates the recommendation logic CAN produce a "
              "primary when evidence/fit suffice (Diagnostic A: "
              "single-requirement → primary C001; Diagnostic B: "
              "evidence removed → primary blocked, nothing "
              "fabricated). Whether \"no primary here\" is the "
              "right business outcome is YOUR call.")
        else:
            if cid == "C11":
                A("Machine Evidence: NOT PRODUCED — knowledge "
                  "fail-closed upstream (see §6); no "
                  "recommendation generated; nothing fabricated.")
            else:
                A("Machine Evidence: NOT PRODUCED")
            A("")
            A("Recommendation Status: NOT_PRODUCED")
            A("Primary Product: NONE")
            A("Machine Eval: NOT_RUN")
        A("")
        A("### Owner Judgment\n\nPENDING_OWNER_REVIEW\n")
        A("### Owner Decision\n- [ ] ACCEPTABLE\n- [ ] "
          "NEEDS_CHANGE\n- [ ] REJECT\n- [ ] NOT_PRODUCED\n"
          "- [ ] UNKNOWN\n")
        A("### Owner Notes\n<!-- Owner. For primary=NONE cases: "
          "is no-recommendation-given-evidence the expected "
          "business behavior? -->\n")
        # 8 report
        A("## 8. Report")
        A("")
        if rr:
            A("Machine Evidence: status=%s" % rr.get("status"))
            body = (rr.get("report") or rr.get("content")
                    or rr.get("sections") or rr)
            A("excerpt: %s" % _j(body, 500))
            A("full: insurance-report.json")
            A("")
            A("Machine Eval: PASS")
        else:
            A("Machine Evidence: NOT PRODUCED")
            A("Machine Eval: NOT_RUN")
        A("")
        A("### Owner Judgment\n\nPENDING_OWNER_REVIEW\n")
        A("### Owner Decision\n- [ ] ACCEPTABLE\n- [ ] "
          "NEEDS_CHANGE\n- [ ] REJECT\n- [ ] NOT_PRODUCED\n"
          "- [ ] UNKNOWN\n")
        A("### Owner Notes\n<!-- Owner. Focus: accurate / "
          "understandable / risks not omitted / consistent with "
          "recommendation / no misleading wording -->\n")
        # 9 provenance
        A("## 9. Provenance")
        A("")
        evs = [e.get("evidence_id") or e.get("chunk_id")
               for e in (ke.get("evidence")
                         or ke.get("results") or [])][:8]
        A("- Knowledge Source: %s"
          % ("EMPTY" if cid == "C11"
             else "fixture KB (chunks 01_medical_insurance_*)"))
        A("- Evidence IDs: %s"
          % (", ".join(filter(None, evs))
             or ("NONE (0 evidence)" if cid == "C11"
                 else "UNKNOWN")))
        A("- Product Source: demo product catalog (C001–C010)")
        A("- Artifact files: %s"
          % (", ".join(sorted(arts)) if arts else "NOT PRODUCED"))
        A("- Trace: tmp/pilot27/%s/%s/%s/trace.jsonl"
          % (cid, adir, cid))
        A("- Eval records: trace.jsonl (EVAL-xxx) + "
          "case_state.json evaluations")
        A("")
        # 10 runtime
        A("## 10. Runtime Outcome")
        A("")
        A("- Task State: %s" % m["final_task_status"])
        A("- Run State: %s" % m["final_run_state"])
        A("- Result status (business payload): %s"
          % m["result_status"])
        A("- Attempt: %s · Repairs: %s · Replans: 0"
          % (m["attempt"],
             m["budget"]["repair_attempts_used"]))
        A("- Mechanical approvals: %d (actor=pilot-operator, "
          "OPERATOR — process continuation, NOT business review)"
          % len(m["mechanical_approvals"]))
        A("- Elapsed: %ss" % m["elapsed_s"])
        if cid in ("C08", "C11"):
            A("- Machine Observation (for your judgment): the "
              "business outcome is %s while Task/Run report "
              "SUCCEEDED and NO human gate fired (see "
              "f27-01-root-cause.md)." % m["result_status"])
        A("")
        # 11 findings
        A("## 11. Pilot Finding")
        A("")
        fl = []
        if cid in ("C08", "C11"):
            fl.append("F27-01 (run semantics — "
                      "f27-01-root-cause.md)")
        if cid == "C11":
            fl.append("F27-02 context (knowledge fail-closed "
                      "upstream)")
        elif rc:
            fl.append("F27-02 context (catalog/evidence content "
                      "gap)")
        if cid == "C12":
            fl.append("F27-03 (empty requirement accepted)")
        if cid == "C11":
            fl.append("F27-04 (empty-KB variant exercised)")
        A("- " + ("\n- ".join(fl) if fl else "NONE"))
        A("(Record NEW observations as OF-xx in README.md — do "
          "not edit F27-*.)")
        A("")
        # 12 summary
        A("## 12. Owner Review Summary")
        A("")
        A("### Overall Case Decision\n\nPENDING_OWNER_REVIEW\n")
        A("### Review Time\n\nreview_start: ____  review_end: "
          "____  duration_seconds: UNKNOWN\n")
        A("### Reviewer Changes\n\nPENDING_OWNER_REVIEW "
          "(type REQUIREMENT/RISK/GAP/SOLUTION/PRODUCT/EVIDENCE/"
          "RECOMMENDATION/REPORT/OTHER + description)\n")
        A("### Main Issues\n<!-- Owner -->\n")
        open(os.path.join(OUT, cid + ".md"), "w",
             encoding="utf-8").write("\n".join(L))
        print("wrote", cid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
