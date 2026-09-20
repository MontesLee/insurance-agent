#!/usr/bin/env python3
"""Agent Quality & Decision Evaluation — Phase 16.

Quality (NOT Phase-15 structural) evaluation over the real pipeline:
gap-quality states, solution alignment, recommendation explainability,
sufficiency/abstention, contradiction handling, paraphrase semantic
invariance, evidence-boundary behavior, report content consistency —
per-case × per-dimension decision matrix with hard gates and mutation
detection. Deterministic; LLM judge never used. Exit 0 PASS / 1 FAIL /
2 BLOCKED.

Reuses (never re-implements): Phase-15 seeding/running machinery and
structural invariants, Phase-14.5 provenance validators. Evaluator is
read-only w.r.t. production (independence asserted by tests).
"""
from __future__ import annotations

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "evals", "business"))

import run_business_eval as biz  # noqa: E402  (evals → evals reuse)
from runtime import orchestrator as orch  # noqa: E402

DATASET = os.path.join(HERE, "dataset", "quality_cases.json")
DIMENSIONS = ("requirement", "risk", "gap", "solution", "candidate",
              "recommendation", "report")
NOT_MEASURABLE = "NOT_MEASURABLE"


def build_quality_seeds(case):
    seeds = biz.build_seeds(case)
    risks = seeds["risk-assessment"]
    rlist = risks.get("risks") or risks["payload"]["risks"]
    for edit in case.get("risk_edits", []):
        for r in rlist:
            if edit.get("risk_selector") != "ALL":
                continue
            for f in edit.get("drop_fields", []):
                r.pop(f, None)
            if "coverage_assessment" in edit:
                r["coverage_assessment"] = edit["coverage_assessment"]
    return seeds


def run_quality_case(case, wf):
    # biz.run_case builds seeds itself; we need risk_edits — replicate
    # the thin run loop with quality seeds.
    seeds = build_quality_seeds(case)
    qc = dict(case)
    qc.pop("risk_edits", None)
    # temporarily monkeypatch-free approach: inline run
    import tempfile, shutil
    run_dir = tempfile.mkdtemp(prefix="q16_%s_" % case["case_id"],
                               dir=os.path.join(REPO, "tmp"))
    svc = None
    if case.get("registry_mutation"):
        svc = biz.registry_mutation_service(case["registry_mutation"])
        biz.set_default_service(svc)
    try:
        state = orch.seed_case(wf, case["case_id"], seeds,
                               provided_by="upstream-dialogue")
        kb = biz.KB_EMPTY if case.get("kb") == "empty" else None
        rep = orch.run(state, wf, gate_policy="stop", kb_dir=kb,
                       checkpoint_root=run_dir)
        apps = 0
        while isinstance(rep, dict) and \
                rep.get("status") == "PAUSED_NEEDS_REVIEW" and apps < 3:
            orch.approve(state, rep["stopped_at"])
            apps += 1
            rep = orch.run(state, wf, gate_policy="stop", kb_dir=kb,
                           checkpoint_root=run_dir)
    finally:
        if svc is not None:
            biz.reset_default_service()
        shutil.rmtree(run_dir, ignore_errors=True)
    return state, rep, seeds


def _pl(state, art):
    return ((state.get("artifacts", {}) or {}).get(art) or {}) \
        .get("payload", {})


# ------------------------------------------------------------------ #
# quality assertions (beyond P15 structural checks)
# ------------------------------------------------------------------ #
def quality_checks(case, state, rep, seeds):
    v = []          # (dimension, detail)
    exp = case.get("expected", {})
    arts = state.get("artifacts", {}) or {}
    gaps = _pl(state, "coverage-gap-analysis").get("gaps") or []
    sols = _pl(state, "solution-plan").get("solutions") or []
    rec = _pl(state, "product-recommendation")
    cand = _pl(state, "product-candidates")

    def fail(dim, msg):
        v.append((dim, msg))

    # terminal / stop stage
    terms = exp.get("terminal")
    if terms:
        allowed = terms if isinstance(terms, list) else [terms]
        if rep.get("status") not in allowed:
            fail("sufficiency" if case["group"] in ("sufficiency",
                                                    "contradiction")
                 else "gap", "terminal %s not in %s"
                 % (rep.get("status"), allowed))
    if exp.get("stop_stage") and rep.get("stopped_at") != exp["stop_stage"]:
        fail("sufficiency", "stopped_at %s != %s" % (rep.get("stopped_at"),
                                                     exp["stop_stage"]))
    # gap quality
    if "gap_count" in exp and len(gaps) != exp["gap_count"]:
        fail("gap", "gap count %d != %d" % (len(gaps), exp["gap_count"]))
    if "gap_statuses_include" in exp:
        statuses = {g.get("current_coverage", {}).get("status")
                    for g in gaps}
        if exp["gap_statuses_include"] not in statuses:
            fail("gap", "no %s gap (statuses=%s)"
                 % (exp["gap_statuses_include"], sorted(map(str, statuses))))
    # solution quality
    if "solution_count" in exp and len(sols) != exp["solution_count"]:
        fail("solution", "solution count %d != %d"
             % (len(sols), exp["solution_count"]))
    if "solution_domains_exclude" in exp:
        doms = {s.get("solution_type", "").upper() for s in sols}
        for d in exp["solution_domains_exclude"]:
            if d.upper() in doms:
                fail("solution", "excluded domain %s present" % d)
    if "multi_domain" in exp:
        doms = {s.get("solution_type", "").lower() for s in sols}
        for d in exp["multi_domain"]:
            if d.lower() not in doms:
                fail("solution", "multi-risk domain %s missing" % d)
    # recommendation quality
    want = exp.get("recommendation_status")
    if want:
        allowed = want if isinstance(want, list) else [want]
        if rec and rec.get("status") not in allowed:
            fail("recommendation", "status %s not in %s"
                 % (rec.get("status"), allowed))
    notbe = exp.get("recommendation_must_not_be")
    if notbe and rec and rec.get("status") == notbe:
        fail("recommendation", "forbidden status %s" % notbe)
    if exp.get("explainability_fields"):
        pr = rec.get("primary_recommendation") or {}
        if rec.get("status") == "COMPLETE":
            for f in exp["explainability_fields"]:
                if not pr.get(f):
                    fail("recommendation", "explainability field %s "
                         "missing/empty" % f)
        else:
            fail("recommendation", "expected COMPLETE for explainability")
    if exp.get("primary_in_admissible"):
        pr = rec.get("primary_recommendation") or {}
        adm = set(cand.get("admissible_candidate_ids") or [])
        if rec.get("status") == "COMPLETE" and adm and \
                pr.get("candidate_id") not in adm:
            fail("recommendation", "primary not in admissible set")
    if exp.get("evidence_items") == 0:
        ev = _pl(state, "knowledge-evidence").get("evidence") or []
        if ev:
            fail("recommendation", "expected 0 evidence items, got %d"
                 % len(ev))
    # sufficiency: missing fields
    if exp.get("missing_fields"):
        cp = (arts.get("client-profile") or {}).get("payload",
                                                    arts.get(
                                                        "client-profile")
                                                    or {})
        missing = {m.get("field")
                   for m in cp.get("missing_from_upstream", [])} \
            if isinstance(cp, dict) else set()
        for f in exp["missing_fields"]:
            if f not in missing:
                fail("sufficiency", "field %s not recorded missing" % f)
    # contradiction SAFETY: never silently resolved. If the run
    # stopped for human review the conflict is escalated (correct);
    # losing the conflicts[] detail in the stored artifact is the
    # recorded finding F-17 (audit fidelity), but a COMPLETED run
    # with dropped conflicts would be a hard contradiction failure.
    if case["group"] == "contradiction"             and rep.get("status") not in ("WAITING_FOR_USER",
                                          "PAUSED_NEEDS_REVIEW"):
        _cpa = arts.get("client-profile") or {}
        prof = _cpa.get("payload", _cpa) if isinstance(_cpa, dict) else {}
        if isinstance(prof, dict) and not prof.get("conflicts"):
            fail("contradiction", "run completed AND conflicts[] "
                 "dropped (silent resolution)")
    # report content consistency (RPT-Q1..7)
    report = _pl(state, "insurance-report")
    if report:
        sr = report.get("structured_report") or {}
        rj = json.dumps(sr, ensure_ascii=False)
        gap_ids = {g.get("gap_id") for g in gaps}
        rep_gap_ids = {g.get("gap_id")
                       for g in (sr.get("coverage_gaps") or [])
                       if isinstance(g, dict)}
        if rep_gap_ids - gap_ids:
            fail("report", "report gaps %s not produced upstream"
                 % sorted(rep_gap_ids - gap_ids))
        risk_ids = {r.get("risk_id")
                    for r in (seeds["risk-assessment"].get("risks")
                              or seeds["risk-assessment"]["payload"]
                              ["risks"])}
        if risk_ids and not any(rid in rj for rid in risk_ids):
            fail("report", "report risk section cites no seeded risk")
        sol_types = {s.get("solution_type") for s in sols}
        rj_types = {t for t in ("MEDICAL", "CRITICAL_ILLNESS", "ACCIDENT",
                                "SAVINGS") if t in rj}
        if sol_types and rj_types and not (sol_types & rj_types):
            fail("report", "report solution section cites no produced "
                 "solution type")
        ev_ids = {e.get("evidence_id")
                  for e in (_pl(state, "knowledge-evidence")
                            .get("evidence") or [])}
        if ev_ids:
            cited = sum(1 for e in ev_ids if e in rj)
            if cited == 0 and rec.get("status") == "COMPLETE":
                fail("report", "report evidence section cites no stored "
                     "evidence id")
        if rec.get("status") == "NO_CANDIDATES":
            for pid in biz.catalog_ids():
                if pid in rj:
                    fail("report", "NO_CANDIDATES but report mentions "
                         "product %s" % pid)
    return v


# ------------------------------------------------------------------ #
# paraphrase invariance
# ------------------------------------------------------------------ #
def invariance_violations(group_results):
    v = []
    groups = {}
    for r in group_results:
        groups.setdefault(r["paraphrase_group"], []).append(r)
    for g, members in groups.items():
        sigs = {json.dumps(m["signature"], ensure_ascii=False,
                           sort_keys=True) for m in members}
        if len(sigs) != 1:
            v.append(("invariance", "group %s diverged: %s"
                      % (g, [m["signature"] for m in members])))
    return v


def case_signature(state, rep):
    gaps = _pl(state, "coverage-gap-analysis").get("gaps") or []
    sols = _pl(state, "solution-plan").get("solutions") or []
    rec = _pl(state, "product-recommendation")
    return {
        "terminal": rep.get("status"),
        "gaps": sorted((g.get("domain"), g.get("gap_level"),
                        g.get("current_coverage", {}).get("status"))
                       for g in gaps),
        "solutions": sorted(s.get("solution_type") for s in sols),
        "recommendation": rec.get("status"),
    }


# ------------------------------------------------------------------ #
# mutation tests (§27) — the evaluator must DETECT injected defects
# ------------------------------------------------------------------ #
def mutation_tests(wf):
    results = []

    def fresh(case):
        state, rep, seeds = run_quality_case(case, wf)
        return (copy.deepcopy(state.get("artifacts", {})), seeds)

    # base A: full requirement set (list-sensitive mutations)
    case_a = {"case_id": "MUT-A", "mutations": [], "requirements": "ALL",
              "risks": "ALL", "expected": {}}
    arts_a, seeds_a = fresh(case_a)
    # base B: medical-only, recommendation COMPLETE (evidence-sensitive)
    case_b = {"case_id": "MUT-B", "mutations": [],
              "requirements": ["medical"], "risks": ["R1"],
              "expected": {}}
    arts_b, seeds_b = fresh(case_b)

    def check(name, mutated_arts, mutated_seeds, want_gate, base_case):
        st = {"artifacts": mutated_arts}
        viols = biz.structural_checks(st, mutated_seeds, base_case)
        # quality-level report consistency: report gap ids must be a
        # SUBSET of produced gap ids (catches report tampering)
        rep = (mutated_arts.get("insurance-report") or {}).get("payload", {})
        sr = (rep or {}).get("structured_report") or {}
        produced = {g.get("gap_id") for g in
                    ((mutated_arts.get("coverage-gap-analysis") or {})
                     .get("payload", {}) or {}).get("gaps", [])}
        cited = {g.get("gap_id") for g in (sr.get("coverage_gaps") or [])
                 if isinstance(g, dict)}
        if cited - produced:
            viols.append(("HG-B12", "report cites unproduced gaps %s"
                          % sorted(cited - produced)))
        gates = {g for g, _ in viols}
        ok = any(g.startswith(want_gate) for g in gates)
        results.append((name, "PASS" if ok else "FAIL", sorted(gates)))

    # M01 — one requirement deleted from seeds (gap now cites unseeded)
    s = copy.deepcopy(seeds_a)
    rl = s["requirement-analysis"].get("requirements") \
        or s["requirement-analysis"]["payload"]["requirements"]
    rl[:] = [r for r in rl if r.get("requirement_type") != "medical"]
    check("M01-delete-requirement", arts_a, s, "HG-B02", case_a)
    # M02 — gap cites a phantom requirement
    a = copy.deepcopy(arts_a)
    g = a["coverage-gap-analysis"]["payload"]["gaps"][0]
    g["related_requirement_ids"] = list(g["related_requirement_ids"]) + ["REQ-PHANTOM"]
    check("M02-fabricated-requirement", a, seeds_a, "HG-B02", case_a)
    # M03 — risk deleted from seeds
    s = copy.deepcopy(seeds_a)
    rl3 = s["risk-assessment"].get("risks")         or s["risk-assessment"]["payload"]["risks"]
    rl3[:] = [r for r in rl3 if r.get("risk_category") != "R1"]
    check("M03-delete-risk", arts_a, s, "HG-B03", case_a)
    # M04 — solution cites an unproduced gap
    a = copy.deepcopy(arts_a)
    a["solution-plan"]["payload"]["solutions"][0]["related_gap_ids"] = ["GAP-PHANTOM"]
    check("M04-fabricated-gap", a, seeds_a, "HG-B04", case_a)
    # M05 — phantom candidate product
    a = copy.deepcopy(arts_a)
    a["product-candidates"]["candidates"].append(
        {"candidate_id": "C999", "product_id": "P999",
         "product_type": "medical"})
    check("M05-phantom-candidate", a, seeds_a, "HG-B11", case_a)
    # M06 — fabricated product id injected anywhere
    a = copy.deepcopy(arts_b)
    a["product-recommendation"]["payload"]["evidence_refs"] = list(
        a["product-recommendation"]["payload"].get("evidence_refs") or []) \
        + ["P999"]
    check("M06-injected-product", a, seeds_b, "HG-B05", case_b)
    # M07 — COMPLETE recommendation with its evidence deleted
    a = copy.deepcopy(arts_b)
    a["product-recommendation"]["payload"]["evidence_refs"] = []
    check("M07-deleted-evidence", a, seeds_b, "HG-B06", case_b)
    # M08 — report section fabricated beyond upstream
    a = copy.deepcopy(arts_b)
    a["insurance-report"]["payload"]["structured_report"]["coverage_gaps"] = [
        {"gap_id": "GAP-PHANTOM"}]
    check("M08-tampered-report", a, seeds_b, "HG-B12", case_b)
    return results


# ------------------------------------------------------------------ #
# runner
# ------------------------------------------------------------------ #
GATE_MAP = {"requirement": "HG-B02", "risk": "HG-B03", "gap": "HG-B04",
            "solution": "HG-B04", "candidate": "HG-B11",
            "recommendation": "HG-B06", "report": "HG-B12",
            "sufficiency": "HG-B08", "contradiction": "HG-B09",
            "invariance": "HG-B12"}


def run_all():
    wf = orch.load_workflow()
    data = json.load(open(DATASET, encoding="utf-8"))["cases"]
    results = []
    para = []
    for case in data:
        seeds = build_quality_seeds(case)
        try:
            state, rep, seeds2 = run_quality_case(case, wf)
            struct = biz.structural_checks(state, seeds2, case)
            quality = quality_checks(case, state, rep, seeds2)
            dims_ok = {d: True for d in DIMENSIONS}
            for dim, _msg in quality:
                if dim in dims_ok:
                    dims_ok[dim] = False
            gate_fail = bool(struct)
            if case["group"] == "paraphrase":
                para.append({"paraphrase_group": case["paraphrase_group"],
                             "signature": case_signature(state, rep),
                             "case_id": case["case_id"]})
            results.append({
                "case_id": case["case_id"], "group": case["group"],
                "status": "PASS" if not quality and not struct else "FAIL",
                "dimensions": dims_ok,
                "quality_violations": [v for v in quality][:4],
                "structural_violations": [s for s in struct][:3],
                "gate_fail": gate_fail})
        except Exception as e:  # noqa: BLE001 — crash = failure
            results.append({"case_id": case["case_id"],
                            "group": case["group"], "status": "FAIL",
                            "dimensions": {d: False for d in DIMENSIONS},
                            "quality_violations": [("CRASH", str(e)[:150])],
                            "structural_violations": [],
                            "gate_fail": True})
    inv = invariance_violations(para)
    muts = mutation_tests(wf)
    return results, inv, muts


def aggregate(results, inv, muts):
    hard = {}
    for r in results:
        for g, _d in r.get("structural_violations", []):
            hard[g] = hard.get(g, 0) + 1
        for dim, _msg in r.get("quality_violations", []):
            g = GATE_MAP.get(dim)
            if g:
                hard[g] = hard.get(g, 0) + 1
    for _d, _m in inv:
        hard["AQ-HG-invariance"] = hard.get("AQ-HG-invariance", 0) + 1
    metrics = {
        "requirement_precision": NOT_MEASURABLE,
        "requirement_recall": NOT_MEASURABLE,
        "risk_precision": NOT_MEASURABLE,
        "risk_recall": NOT_MEASURABLE,
        "requirement_consistency": "PASS" if not hard.get("HG-B02")
        else "FAIL",
        "risk_consistency": "PASS" if not hard.get("HG-B03") else "FAIL",
        "gap_accuracy": "PASS" if not hard.get("HG-B04") else "FAIL",
        "solution_alignment": "PASS" if not hard.get("HG-B04") else "FAIL",
        "candidate_validity": "PASS" if not hard.get("HG-B11")
        and not hard.get("HG-B05") else "FAIL",
        "recommendation_grounding": "PASS" if not hard.get("HG-B06")
        and not hard.get("HG-B07") else "FAIL",
        "recommendation_decision_accuracy": "PASS" if not [
            r for r in results if r["group"] in ("recommendation",
                                                 "boundary")
            and r["status"] == "FAIL"] else "FAIL",
        "question_target_accuracy": "PASS" if not [
            r for r in results if r["group"] == "sufficiency"
            and r["status"] == "FAIL"] else "FAIL",
        "report_consistency": "PASS" if not hard.get("HG-B12") else "FAIL",
        "abstention_accuracy": "PASS" if not [
            r for r in results if r["group"] in ("sufficiency",
                                                 "boundary")
            and r["status"] == "FAIL"] else "FAIL",
        "contradiction_detection": "PASS" if not [
            r for r in results if r["group"] == "contradiction"
            and r["status"] == "FAIL"] else "FAIL",
        "semantic_invariance": "PASS" if not inv else "FAIL",
        "mutation_detection": "%d/%d" % (
            sum(1 for _n, s, _g in muts if s == "PASS"), len(muts)),
    }
    return hard, metrics


def main():
    results, inv, muts = run_all()
    hard, metrics = aggregate(results, inv, muts)
    mut_ok = all(s == "PASS" for _n, s, _g in muts)
    ok = (all(r["status"] == "PASS" for r in results) and not inv
          and not hard and mut_ok)
    blocked = False
    lines = ["", "AGENT QUALITY EVALUATION (Phase 16) — %s"
             % ("ALL GREEN" if ok else "FAILURES PRESENT"),
             "Dataset: %d cases" % len(results), ""]
    for r in results:
        lines.append("[%s] %-14s %-26s %s" % (
            r["status"], r["group"], r["case_id"],
            json.dumps([v for v in r["quality_violations"]
                        + r["structural_violations"]],
                       ensure_ascii=False)[:110]
            if (r["quality_violations"] or r["structural_violations"])
            else ""))
    for name, s, gates in muts:
        lines.append("[MUT %s] %-26s -> %s" % (s, name, gates[:4]))
    lines += ["", "HARD GATES: " + (json.dumps(hard) if hard else "CLEAN"),
              "METRICS: " + json.dumps(metrics, ensure_ascii=False,
                                       indent=1),
              "OVERALL: %s" % ("PASS" if ok else
                               ("BLOCKED" if blocked else "FAIL"))]
    print("\n".join(lines))
    matrix = {"cases": results, "metrics": metrics, "hard_gates": hard,
              "mutations": [{"name": n, "status": s} for n, s, _g in muts],
              "invariance": inv}
    with open(os.path.join(HERE, "decision_matrix.json"), "w",
              encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=1)
    with open(os.path.join(REPO, "tmp", "agent_quality_report.json"),
              "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=1)
    return 0 if ok else (2 if blocked else 1)


if __name__ == "__main__":
    sys.exit(main())
