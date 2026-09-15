"""Step 3 — Mutation tests (anti-rubber-stamp proofs).

Every test tampers ONE field in a real, passing artifact (or checkpoint) and asserts the
Eval Engine / Checkpoint validator CATCHES it. A guard that can never be made to fail is a
rubber stamp, so each mutation also carries an implicit reverse: the unmutated artifact passes
in the same code path (we are testing the mutation, not a constant).

Exit 0 = every mutation is detected and every reverse passes.
"""
from __future__ import annotations

import copy
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (REPO_ROOT,):
    if p not in sys.path:
        sys.path.insert(0, p)

from runtime.state import case_state as cs  # noqa: E402
from runtime import orchestrator as orch  # noqa: E402
from runtime import artifact_registry as reg  # noqa: E402
from runtime import checkpoint as cp  # noqa: E402
from runtime import eval_engine as ev  # noqa: E402

FIXTURE = os.path.join(REPO_ROOT, "tests", "e2e", "fixtures", "case-full-chain.json")
LOG = os.path.join(HERE, "_step3_mutation_log.txt")

_results = []


def check(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                         ("  -- " + str(detail)) if detail and not ok else ""))


def _full_state(wf, rules):
    fixture = json.load(io.open(FIXTURE, encoding="utf-8"))
    state = orch.seed_case(wf, "CASE-MUT", fixture["artifacts"])
    rep = orch.run(state, wf, gate_policy="auto")
    assert rep["status"] == "COMPLETED", rep.get("reasons")
    return state


def _eval(state, artifact_type, artifact, contract, rules):
    stage = {"id": artifact_type, "produces": artifact_type, "contract": contract}
    return ev.evaluate(state, artifact_type, artifact, stage, rules=rules, registry=reg)


def main():
    wf = orch.load_workflow()
    rules = ev.load_rules()
    state = _full_state(wf, rules)

    # ===== M-A: product_id tamper -> invariant catalog_exists FAILs =====================
    cand = copy.deepcopy(state["artifacts"]["product-candidates"])
    prod = cand.get("payload", cand) if isinstance(cand, dict) else cand
    target = next((c for c in prod.get("candidates", []) if c.get("admissible")),
                  prod["candidates"][0])
    target["product_id"] = "P999-NOT-IN-CATALOG"
    rec = _eval(state, "product-candidates", cand, None, rules)
    fails = [c for c in rec["checks"] if c["status"] == "FAIL"]
    catalog_fail = any("catalog_exists" in c["check_id"] for c in fails)
    check("M-A tampering product_id to a non-catalog id fails catalog_exists invariant",
          catalog_fail, [c["check_id"] for c in fails])
    rec_ok = _eval(state, "product-candidates",
                   copy.deepcopy(state["artifacts"]["product-candidates"]), None, rules)
    check("M-Ar the original product_id passes catalog_exists (not a constant)",
          not any("catalog_exists" in c["check_id"] and c["status"] == "FAIL"
                  for c in rec_ok["checks"]))

    # ===== M-B: evidence_ref tamper -> provenance recommendation_evidence FAILs =======
    # The real recommendation here is INCOMPLETE_EVIDENCE (some catalog products lack KB
    # evidence), which the eval rule INTENTIONALLY skips. Provenance is only enforced for a
    # COMPLETE recommendation, so we exercise the guard on that status using the real ids.
    real = state["artifacts"]["product-recommendation"]
    rec_skip = _eval(state, "product-recommendation", real,
                     "contracts/product-recommendation.schema.json", rules)
    check("M-B0 an INCOMPLETE_EVIDENCE recommendation is skipped, not falsely evaluated",
          any(c["check_id"] == "skipped" for c in rec_skip["checks"]),
          [c["check_id"] for c in rec_skip["checks"]])

    ke = state["artifacts"]["knowledge-evidence"]
    kep = ke.get("payload", ke)
    real_ids = [e.get("evidence_id") for e in (kep.get("evidence") or []) if e.get("evidence_id")]
    compl = {"artifact_type": "product-recommendation",
             "payload": {"status": "COMPLETE", "evidence_refs": real_ids}}
    rec_c = _eval(state, "product-recommendation", compl,
                  "contracts/product-recommendation.schema.json", rules)
    check("M-B (forward) a COMPLETE recommendation with resolving refs passes provenance",
          not any("provenance_recommendation_evidence" in c["check_id"] and c["status"] == "FAIL"
                  for c in rec_c["checks"]))

    tampered = copy.deepcopy(compl)
    tampered["payload"]["evidence_refs"] = real_ids + ["EVD-FABRICATED-REF"]
    recb = _eval(state, "product-recommendation", tampered,
                 "contracts/product-recommendation.schema.json", rules)
    prov_fail = any("provenance_recommendation_evidence" in c["check_id"] and c["status"] == "FAIL"
                    for c in recb["checks"])
    check("M-B fabricating an evidence_ref fails provenance (dangling ref)",
          prov_fail, [c["check_id"] for c in recb["checks"] if c["status"] == "FAIL"])

    # ===== M-C: gap->risk tamper -> cross_artifact orphan FAILs ========================
    gap_art = copy.deepcopy(state["artifacts"]["coverage-gap-analysis"])
    gp = gap_art.get("payload", gap_art) if isinstance(gap_art, dict) else gap_art
    g0 = gp["gaps"][0]
    g0["related_risk_ids"] = list(g0.get("related_risk_ids") or []) + ["R9-FABRICATED"]
    recc = _eval(state, "coverage-gap-analysis", gap_art,
                 "contracts/coverage-gap-analysis.schema.json", rules)
    orphan_fail = any("cross_artifact_gap_risk_refs" in c["check_id"] and c["status"] == "FAIL"
                      for c in recc["checks"])
    check("M-C fabricating a gap->risk ref fails cross_artifact (orphan ref)",
          orphan_fail, [c["check_id"] for c in recc["checks"] if c["status"] == "FAIL"])
    recc_r = _eval(state, "coverage-gap-analysis",
                   copy.deepcopy(state["artifacts"]["coverage-gap-analysis"]),
                   "contracts/coverage-gap-analysis.schema.json", rules)
    check("M-Cr original gap->risk refs resolve (cross_artifact passes)",
          not any("cross_artifact_gap_risk_refs" in c["check_id"] and c["status"] == "FAIL"
                  for c in recc_r["checks"]))

    # ===== M-D: checkpoint tamper -> CHECKPOINT_INVALID ================================
    tmpd = tempfile.mkdtemp(prefix="step3-cp-")
    try:
        fixture = json.load(io.open(FIXTURE, encoding="utf-8"))
        st = orch.seed_case(wf, "CASE-CP", fixture["artifacts"])
        orch.run(st, wf, gate_policy="auto", checkpoint_root=tmpd)
        loaded0, errs0 = cp.load(tmpd, "CASE-CP")
        check("M-D0 a valid checkpoint loads cleanly", loaded0 is not None, errs0)

        cpath = os.path.join(cp.store.case_dir(tmpd, "CASE-CP"), "case_state.json")
        raw = json.load(open(cpath, encoding="utf-8"))
        raw["artifacts"]["client-profile"]["payload"]["family_profile"]["age"]["value"] = "999"
        json.dump(raw, open(cpath, "w"), ensure_ascii=False)
        loaded1, errs1 = cp.load(tmpd, "CASE-CP")
        check("M-D tampering a checkpointed artifact fails validation (CHECKPOINT_INVALID)",
              loaded1 is None and any("CHECKPOINT_INVALID" in e for e in errs1), errs1)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    lines = ["STEP3 MUTATION: %d/%d passed" % (passed, len(_results)),
             "RESULT: %s" % ("ALL GREEN" if passed == len(_results) else "FAILURES PRESENT")]
    print("\n".join(lines))
    io.open(LOG, "w", encoding="utf-8").write(
        "\n".join(["%s %s" % ("PASS" if ok else "FAIL", n) for n, ok in _results] + [""] + lines))
    sys.exit(0 if passed == len(_results) else 1)


if __name__ == "__main__":
    main()
