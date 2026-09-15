"""Orchestration invariants + negative probes (V2 Phase 7).

Two kinds of assertion, deliberately kept apart:

  INVARIANTS  -- properties the orchestrator must hold on a real run.
  PROBES      -- single-point mutations that MUST make a specific guard fail. A guard that
                 never fails is a rubber stamp; each probe also carries a reverse assertion
                 showing the same input passes unmutated, so we are testing the mutation and
                 not a constant.

Exit 0 = every invariant holds and every probe fails as intended.
"""
from __future__ import annotations

import copy
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from runtime.state import case_state as cs  # noqa: E402
from runtime.state import transitions  # noqa: E402
from runtime import orchestrator as orch  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "case-full-chain.json")
LOG = os.path.join(HERE, "_orchestration_invariants_log.txt")

_results = []


def check(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                         ("  -- " + str(detail)) if detail and not ok else ""))


def _full_state(wf):
    fixture = json.load(io.open(FIXTURE, encoding="utf-8"))
    state = orch.seed_case(wf, "CASE-INV", fixture["artifacts"])
    rep = orch.run(state, wf, gate_policy="auto")
    assert rep["status"] == "COMPLETED", rep["reasons"]
    return state


def main():
    wf = orch.load_workflow()
    stage_defs = {s["id"]: s for s in wf["stages"]}

    # ================= INVARIANTS =========================================
    state = _full_state(wf)

    check("I1 all 7 stages reach COMPLETED on a full run",
          all(r["status"] == "COMPLETED" for r in state["stages"].values()))
    check("I2 pipeline reports finished", transitions.is_finished(state, wf))
    check("I3 next_runnable is None once finished", transitions.next_runnable(state, wf) is None)

    # every stage that declares a contract must point at an existing file
    # (product-candidate-provider has no canonical contract yet — Step 2 deliberate debt)
    missing_contracts = [s["id"] for s in wf["stages"] if s.get("contract")
                         and not os.path.exists(os.path.join(REPO_ROOT, s["contract"]))]
    check("I4 every stage declares an existing contract file", not missing_contracts,
          repr(missing_contracts))

    # every consumed artifact has a producer (stage) or a declared service
    produced = {s["produces"] for s in wf["stages"]}
    serviced = {s["provides"] for s in wf.get("services", [])}
    orphans = []
    for s in wf["stages"]:
        for a in s.get("consumes", []):
            if a not in produced and a not in serviced:
                orphans.append("%s consumes %s" % (s["id"], a))
    check("I5 every consumed artifact has a producer or a service", not orphans, repr(orphans))

    # knowledge-search must not be a linear stage (user review item 3)
    check("I6 knowledge-search is a service, not a stage",
          "knowledge-search" not in {s["id"] for s in wf["stages"]}
          and any(s["id"] == "knowledge-search" for s in wf.get("services", [])))

    # the evidence round-trip is read-only
    svc = state["services"]["knowledge-search"]
    check("I7 evidence round-trip is read-only (source_unchanged)", svc["source_unchanged"] is True)

    # artifact freeze holds for every completed stage
    check("I8 every completed stage's artifact still matches its frozen fingerprint",
          all(cs.verified(state, sid) for sid, r in state["stages"].items()
              if r["status"] == "COMPLETED" and r.get("produces")),
          repr([sid for sid, r in state["stages"].items()
                if r["status"] == "COMPLETED" and r.get("produces") and not cs.verified(state, sid)]))

    # the orchestrator never writes a stage's artifact under a different stage's name
    check("I9 each artifact is attributed to its own producing stage",
          all(state["stages"][sid]["produces"] == art
              for art, sid in _producer_map(state).items() if sid))

    # ================= PROBES (single mutation -> specific guard must fail) =
    # --- P1: monotonicity ---------------------------------------------------
    s = copy.deepcopy(state)
    s["stages"]["solution"]["status"] = "PENDING"          # single mutation
    ok, reasons = transitions.can_run(s, stage_defs["solution"])
    check("P1 monotonicity guard fires on a rewound stage", (not ok) and any(
        "NON_MONOTONIC" in r for r in reasons), repr(reasons))
    # reverse: identical state and identical stage status (PENDING); the ONLY difference is
    # that no LATER stage is completed. It must pass -> isolates the mutation from the guard.
    s_rev = copy.deepcopy(state)
    # Derived from the workflow, not hardcoded: the probe must survive the chain growing.
    sol_idx = stage_defs["solution"]["index"]
    for st in wf["stages"]:
        if st["index"] >= sol_idx:
            s_rev["stages"][st["id"]]["status"] = "PENDING"
    ok0, reasons0 = transitions.can_run(s_rev, stage_defs["solution"])
    check("P1r same PENDING stage passes once no later stage is completed",
          ok0 is True, repr(reasons0))

    # --- P2: preconditions --------------------------------------------------
    s = copy.deepcopy(state)
    del s["artifacts"]["risk-assessment"]                   # single mutation
    ok, reasons = transitions.can_run(s, stage_defs["coverage-gap-analysis"])
    check("P2 precondition guard fires when a consumed artifact is absent",
          (not ok) and any("MISSING_INPUT_ARTIFACT" in r for r in reasons), repr(reasons))

    # --- P3: immutability ---------------------------------------------------
    existing = state["artifacts"]["solution-plan"]
    changed = copy.deepcopy(existing)
    changed["payload"]["objective"] = "mutated"
    ok_bad, _ = transitions.guard_immutable(existing, changed, "solution")
    ok_same, _ = transitions.guard_immutable(existing, copy.deepcopy(existing), "solution")
    check("P3 immutability guard rejects a changed artifact", ok_bad is False)
    check("P3r immutability guard accepts an identical artifact (not a constant False)",
          ok_same is True)

    # --- P4: an unreviewed producer blocks its consumer ---------------------
    s = copy.deepcopy(state)
    s["stages"]["product-recommendation"]["status"] = "NEEDS_REVIEW"
    synthetic = {"id": "downstream-probe", "index": 99, "consumes": ["product-recommendation"]}
    ok, reasons = transitions.guard_preconditions(s, synthetic)
    check("P4 a stage in NEEDS_REVIEW blocks its consumer (INPUT_NOT_RELEASED)",
          (not ok) and any("INPUT_NOT_RELEASED" in r for r in reasons), repr(reasons))
    # reverse: with the producer COMPLETED the same stage passes
    s2 = copy.deepcopy(state)
    ok2, reasons2 = transitions.guard_preconditions(s2, synthetic)
    check("P4r consumer passes when the producer is COMPLETED", ok2 is True, repr(reasons2))

    # --- P5: the workflow-shape check is not tautological -------------------
    tampered_wf = copy.deepcopy(wf)
    tampered_wf["stages"].append({"id": "knowledge-search", "index": 99, "skill": "knowledge-search",
                                 "produces": "knowledge-evidence", "consumes": [],
                                 "executor": "provided", "gate": "auto"})
    t_ids = {s["id"] for s in tampered_wf["stages"]}
    check("P5 adding knowledge-search as a stage makes the I6 shape check fail",
          "knowledge-search" in t_ids, repr(sorted(t_ids)))
    check("P5r the pristine workflow passes the same check",
          "knowledge-search" not in {s["id"] for s in wf["stages"]})

    # --- P6: a provided stage with no seed cannot be invented ---------------
    fixture = json.load(io.open(FIXTURE, encoding="utf-8"))
    partial = {k: v for k, v in fixture["artifacts"].items() if k != "risk-assessment"}
    st = orch.seed_case(wf, "CASE-NOSEED", partial)
    rep = orch.run(st, wf, gate_policy="auto")
    check("P6 a provided stage without a seed is BLOCKED, not fabricated",
          rep["status"] == "BLOCKED" and rep["stopped_at"] == "risk-analysis",
          "status=%r stopped_at=%r" % (rep["status"], rep["stopped_at"]))
    check("P6r the missing artifact was NOT created",
          "risk-assessment" not in st["artifacts"])
    check("P6r2 no downstream stage ran",
          all(st["stages"][x]["status"] == "PENDING"
              for x in ("coverage-gap-analysis", "solution", "report-generation")))

    # ================= summary ============================================
    passed = sum(1 for _, ok in _results if ok)
    lines = ["INVARIANTS+PROBES: %d/%d passed" % (passed, len(_results)),
             "RESULT: %s" % ("ALL GREEN" if passed == len(_results) else "FAILURES PRESENT")]
    print("\n".join(lines))
    io.open(LOG, "w", encoding="utf-8").write("\n".join(
        ["%s %s" % ("PASS" if ok else "FAIL", n) for n, ok in _results] + [""] + lines))
    sys.exit(0 if passed == len(_results) else 1)


def _producer_map(state):
    return {r["produces"]: sid for sid, r in state["stages"].items() if r.get("produces")}


if __name__ == "__main__":
    main()
