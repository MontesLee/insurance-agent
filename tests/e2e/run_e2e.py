"""End-to-end run of the insurance-analysis workflow (V2 Phase 7).

Drives ONE client case from the three provided upstream artifacts all the way to the final
InsuranceReport, through the real orchestrator:

    seed(provided) -> coverage-gap -> solution -> product-recommendation -> report-generation

It exercises the parts a unit test cannot:
  * the human-review gate actually PAUSES the pipeline (product-recommendation is parked in
    NEEDS_REVIEW and its consumer cannot start);
  * approval RELEASES the pipeline and it finishes;
  * every artifact produced is validated against ITS canonical contract;
  * the evidence round-trip is read-only (`source_unchanged`);
  * the case persists to disk and reloads identically.

Exit 0 = all checks pass.
"""
from __future__ import annotations

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (REPO_ROOT,):
    if p not in sys.path:
        sys.path.insert(0, p)

from state import case_state as cs  # noqa: E402
from state import store  # noqa: E402
from state import transitions  # noqa: E402
from workflow import orchestrator as orch  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "case-full-chain.json")
LOG = os.path.join(HERE, "_e2e_log.txt")
RUN_ROOT = os.path.join(REPO_ROOT, "tmp", "e2e")

GATE_STAGE = "product-recommendation"      # declares gate: human_review
FINAL_STAGE = "report-generation"
# Step 3: product-candidate-provider (Step 2 skill) is now registered in the workflow.
EXPECTED_STAGES = 8


def main():
    lines = []
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok))
        lines.append("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                                    ("  -- " + detail) if (detail and not ok) else ""))

    wf = orch.load_workflow()

    # ---- 0) workflow shape -------------------------------------------------
    ids = [s["id"] for s in wf["stages"]]
    check("workflow has %d linear stages" % EXPECTED_STAGES, len(ids) == EXPECTED_STAGES, repr(ids))
    check("stage order is the canonical data chain",
          ids == ["client-intake", "requirement-analysis", "risk-analysis",
                  "coverage-gap-analysis", "solution", "product-candidate-provider",
                  "product-recommendation", "report-generation"], repr(ids))
    check("knowledge-search is NOT a linear stage (shared provider)",
          "knowledge-search" not in ids)
    check("knowledge-search is declared as a service",
          any(s["id"] == "knowledge-search" for s in wf.get("services", [])))
    idx = {s["id"]: s["index"] for s in wf["stages"]}
    check("stage indices are contiguous from 0", sorted(idx.values()) == list(range(EXPECTED_STAGES)))

    # ---- 1) seed -----------------------------------------------------------
    fixture = json.load(io.open(FIXTURE, encoding="utf-8"))
    state = orch.seed_case(wf, fixture["case_id"], fixture["artifacts"],
                           provided_by=fixture["provided_by"])
    ok, errs = cs.validate(state)
    check("seeded CaseState is schema-valid", ok, "; ".join(errs))
    check("provided stages seeded as COMPLETED",
          all(state["stages"][s]["status"] == "COMPLETED"
              for s in ("client-intake", "requirement-analysis", "risk-analysis")))
    check("seeded artifacts are canonical envelopes",
          all(isinstance(state["artifacts"][a], dict) and "artifact_type" in state["artifacts"][a]
              for a in ("client-profile", "requirement-analysis", "risk-assessment")))

    # ---- 2) run with gate_policy=stop -> must pause at the human gate ------
    rep = orch.run(state, wf, gate_policy="stop")
    check("run PAUSES at the human-review gate", rep["status"] == "PAUSED_NEEDS_REVIEW",
          "status=%r" % rep["status"])
    check("pause is at %s" % GATE_STAGE, rep["stopped_at"] == GATE_STAGE,
          "stopped_at=%r" % rep["stopped_at"])
    check("gated stage is NEEDS_REVIEW",
          state["stages"][GATE_STAGE]["status"] == "NEEDS_REVIEW")
    check("downstream stage did NOT run",
          state["stages"][FINAL_STAGE]["status"] == "PENDING",
          state["stages"][FINAL_STAGE]["status"])
    # The gate must be real: while the stage sits in NEEDS_REVIEW the pipeline cannot advance
    # past it — `next_runnable` still points at the gated stage, so the final stage is never
    # reached even though its own preconditions are already satisfied.
    check("pipeline cannot advance past the unreviewed stage",
          transitions.next_runnable(state, wf) == GATE_STAGE,
          "next_runnable=%r" % transitions.next_runnable(state, wf))
    check("later stage is not runnable while the gate is open",
          not transitions.is_finished(state, wf))
    rep2 = orch.run(state, wf, gate_policy="stop")
    check("re-running while ungated still pauses (gate is not bypassable by retry)",
          rep2["status"] == "PAUSED_NEEDS_REVIEW" and rep2["stopped_at"] == GATE_STAGE,
          "status=%r" % rep2["status"])

    # ---- 3) approve -> resume ---------------------------------------------
    orch.approve(state, GATE_STAGE)
    check("approved stage is COMPLETED", state["stages"][GATE_STAGE]["status"] == "COMPLETED")
    rep3 = orch.run(state, wf, gate_policy="stop")
    check("run COMPLETES after approval", rep3["status"] == "COMPLETED",
          "status=%r reasons=%r" % (rep3["status"], rep3["reasons"]))
    check("all %d stages COMPLETED" % EXPECTED_STAGES,
          all(s["status"] == "COMPLETED" for s in state["stages"].values()),
          repr(cs.statuses(state)))

    # ---- 4) every artifact contract-valid ----------------------------------
    all_valid = True
    checked = []
    for st in wf["stages"]:
        art_type = st.get("produces")
        if art_type not in state["artifacts"]:
            all_valid = False
            checked.append("%s: MISSING" % art_type)
            continue
        if not st.get("contract"):
            # Step 2 added product-candidate-provider: a Skill-level artifact with no canonical
            # contract yet (deliberate debt). It is still Eval-checked via eval.rules.json.
            checked.append("%s ok (no canonical contract; eval-checked)" % art_type)
            continue
        vok, verrs = orch.validate_artifact(state["artifacts"][art_type], st["contract"])
        if not vok:
            all_valid = False
            checked.append("%s: %s" % (art_type, "; ".join(verrs)))
        else:
            checked.append("%s ok" % art_type)
    check("all %d produced artifacts validate against their canonical contract"
          % len(state["artifacts"]), all_valid, " | ".join(checked))

    # ---- 5) the report itself ---------------------------------------------
    report = state["artifacts"]["insurance-report"]
    payload = report["payload"]
    sr = payload.get("structured_report", {})
    check("report status == success", payload.get("status") == "success",
          repr(payload.get("status")))
    check("report 04 is canonical-first (derivation=canonical)",
          sr.get("coverage_gap_derivation") == "canonical",
          repr(sr.get("coverage_gap_derivation")))
    check("report renders coverage gaps", len(sr.get("coverage_gaps", [])) > 0)
    check("report renders solution strategies (from SolutionPlan)",
          len(sr.get("solution_strategies", [])) > 0)
    check("report renders the evidence appendix",
          len(sr.get("evidence_summary", [])) > 0)
    check("report has a rendered markdown body",
          isinstance(payload.get("rendered_report"), str) and len(payload["rendered_report"]) > 0)
    rendered = payload.get("rendered_report", "")
    check("rendered report carries no insurer brand names",
          not any(b in rendered for b in ("平安", "国寿", "太平洋")))

    # ---- 6) evidence round-trip is read-only ------------------------------
    svc = state["services"]["knowledge-search"]
    check("knowledge-search service was called once", svc["calls"] == 1, repr(svc))
    check("evidence round-trip reported source_unchanged", svc["source_unchanged"] is True)
    check("knowledge-evidence artifact stored",
          "knowledge-evidence" in state["artifacts"])

    # ---- 7) immutability of completed artifacts ---------------------------
    sol_before = json.dumps(state["artifacts"]["solution-plan"], sort_keys=True)
    tampered = json.loads(json.dumps(state["artifacts"]["solution-plan"]))
    tampered["payload"]["objective"] = "TAMPERED"
    ok_put, reasons = cs.put_artifact(state, "solution-plan", tampered, "solution")
    check("mutating a completed artifact is REFUSED", ok_put is False, repr(reasons))
    check("original artifact unchanged after refused write",
          json.dumps(state["artifacts"]["solution-plan"], sort_keys=True) == sol_before)

    # ---- 8) persistence round-trip ----------------------------------------
    d = store.save(state, RUN_ROOT)
    reloaded = store.load(RUN_ROOT, fixture["case_id"])
    check("case_state.json persisted", os.path.exists(os.path.join(d, "case_state.json")))
    check("reloaded state equals saved state",
          json.dumps(reloaded, sort_keys=True, ensure_ascii=False)
          == json.dumps(state, sort_keys=True, ensure_ascii=False))
    check("artifacts persisted individually",
          os.path.exists(os.path.join(d, "artifacts", "insurance-report.json")))
    rok, rerrs = cs.validate(reloaded)
    check("reloaded state is schema-valid", rok, "; ".join(rerrs))

    # ---- 9) stage invocation accounting -----------------------------------
    attempts = {sid: r["attempts"] for sid, r in state["stages"].items()}
    python_stages = [s["id"] for s in wf["stages"] if s["executor"] == "python"]
    check("every python stage invoked exactly once",
          all(attempts[s] == 1 for s in python_stages), repr(attempts))

    passed = sum(1 for _, ok in checks if ok)
    lines.append("")
    lines.append("E2E: %d/%d checks passed" % (passed, len(checks)))
    lines.append("E2E RESULT: %s" % ("ALL GREEN" if passed == len(checks) else "FAILURES PRESENT"))
    text = "\n".join(lines)
    print(text)
    io.open(LOG, "w", encoding="utf-8").write(text)
    sys.exit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
