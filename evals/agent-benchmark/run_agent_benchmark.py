"""Step 4 Phase 3 — Agent Benchmark runner.

Answers the only question that matters for an agent: **can it handle a real client
case CORRECTLY?** — not "does the code run".

For every case in `manifest.json` it runs the WHOLE pipeline (seed -> orchestrator ->
skills -> artifacts -> eval -> repair -> checkpoint -> report) and then checks:

  * behavioural expectations (park on missing/conflicting facts, detect gaps, refuse
    to recommend an ineligible product, keep provenance, block on insufficient evidence);
  * the three safety hard gates (spec §11):
        product_hallucination == 0, critical_provenance_failure == 0,
        invalid_continuation == 0;
  * agent-level metrics (spec §10), all computed from the REAL run.

Adversarial cases inject a fault at the Eval boundary (a tampered artifact) and assert
the agent refuses to push it downstream.

Usage:
    python run_agent_benchmark.py                 # run + print + write results.json/report.md
    python run_agent_benchmark.py --write-baseline # additionally (re)write baseline.json

Exit 0 = no hard-gate violation AND every case met its expectations.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))  # evals/agent-benchmark -> repo root
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from runtime import orchestrator as orch  # noqa: E402
from runtime import eval_engine as ev  # noqa: E402

MANIFEST = os.path.join(HERE, "manifest.json")
RUN_ROOT = os.path.join(REPO, "tmp", "agent-benchmark")
CATALOG = os.path.join(REPO, "catalog", "product-catalog.v0.1.json")

CANONICAL_ARTIFACTS = ["client-profile", "requirement-analysis", "risk-assessment",
                       "coverage-gap-analysis", "solution-plan", "knowledge-evidence",
                       "product-candidates", "product-recommendation", "insurance-report"]

# recommendation statuses the Eval rule deliberately skips for provenance
REC_SKIPPED = {"NO_CANDIDATES", "INCOMPLETE_EVIDENCE", "INSUFFICIENT_EVIDENCE", "INSUFFICIENT_INPUT"}


# --------------------------------------------------------------------------- #
# mutation language
# --------------------------------------------------------------------------- #
def _payload(art):
    return art.get("payload", art) if isinstance(art, dict) else art


def _set_nested(obj, dotted, value):
    """Set obj['a']['b']['c'] from a dotted path (creates missing dicts)."""
    parts = dotted.split(".")
    cur = obj
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def apply_mutations(seeds, mutations):
    cp = seeds["client-profile"]
    prof = cp.get("payload", cp)
    ra = seeds["risk-assessment"]
    for m in mutations:
        op = m["op"]
        if op == "set_unknown":
            fld = prof.setdefault(m["profile"], {}).setdefault(m["field"], {})
            fld["status"] = "UNKNOWN"
            fld["value"] = None
            prof.setdefault("missing_from_upstream", []).append(
                {"field": m["field"], "profile": m["profile"], "reason": m.get("reason", "未提供")})
        elif op == "set_value":
            fld = prof.setdefault(m["profile"], {}).setdefault(m["field"], {})
            fld["value"] = m["value"]
            fld["status"] = "KNOWN"
        elif op == "add_conflict":
            prof.setdefault("conflicts", []).append(
                {"field": m["field"], "candidates": m.get("candidates", [])})
        elif op == "set_risk":
            for r in ra.get("risks", []):
                if r.get("risk_id") == m["risk_id"]:
                    _set_nested(r, m["field"], m["value"])
        elif op == "set_all_risks":
            for r in ra.get("risks", []):
                _set_nested(r, m["field"], m["value"])
        elif op == "keep_risks":
            keep = set(m["risk_ids"])
            ra["risks"] = [r for r in ra.get("risks", []) if r.get("risk_id") in keep]
        elif op == "keep_requirements":
            # Narrow the provided RequirementAnalysis to a subset. Used to model a
            # single-need client so the recommendation layer can actually reach a
            # per-product COMPLETE verdict (the demo catalog is single-domain).
            rq = seeds.get("requirement-analysis") or {}
            body = rq.get("payload", rq)
            keep = set(m["requirement_ids"])
            body["requirements"] = [r for r in (body.get("requirements") or [])
                                    if r.get("requirement_id") in keep]
        else:
            raise ValueError("unknown mutation op: %s" % op)
    return seeds


# --------------------------------------------------------------------------- #
# fault injection (adversarial cases)
# --------------------------------------------------------------------------- #
def _resolve_container(obj, path):
    """Return (container, key) for a path like 'a.b[0].c' so it can be set/deleted."""
    parts = path.split(".")
    cur = obj
    for p in parts[:-1]:
        if p.endswith("]"):
            name, idx = p[:-1].split("[")
            cur = cur[name][int(idx)]
        else:
            cur = cur[p]
    last = parts[-1]
    if last.endswith("]"):
        name, idx = last[:-1].split("[")
        return cur[name], int(idx)
    return cur, last


def _make_fault(ev_module, fault):
    """Wrap evaluate so the produced artifact is tampered right before it is judged.

    `once: true` injects a TRANSIENT defect (only the first evaluation of that stage is
    tampered). That models a repairable upstream glitch: the repair loop re-derives the
    artifact and the next evaluation is clean.
    """
    orig = ev_module.evaluate
    target_type = fault["artifact_type"]
    fired = {"n": 0}

    def patched(state, artifact_type, artifact, stage, rules=None, registry=None):
        if artifact_type == target_type and isinstance(artifact, dict):
            do_tamper = (fired["n"] == 0) if fault.get("once") else True
            if do_tamper:
                fired["n"] += 1
                art = copy.deepcopy(artifact)
                container, key = _resolve_container(art, fault["path"])
                if fault.get("op") == "delete":
                    if isinstance(container, dict):
                        container.pop(key, None)
                else:
                    container[key] = fault["value"]
                artifact = art
        return orig(state, artifact_type, artifact, stage, rules=rules, registry=registry)

    return orig, patched


# --------------------------------------------------------------------------- #
# run one case
# --------------------------------------------------------------------------- #
def run_case(case, wf, base, seeds_file, kb_empty):
    seeds = apply_mutations(copy.deepcopy(base["artifacts"]), case.get("mutations", []))
    kb_dir = kb_empty if case.get("kb") == "empty" else None

    run_dir = os.path.join(RUN_ROOT, case["id"])
    if os.path.exists(run_dir):
        shutil.rmtree(run_dir)
    os.makedirs(run_dir, exist_ok=True)

    state = orch.seed_case(wf, case["id"], seeds, provided_by=base.get("provided_by",
                                                                     "upstream-dialogue"))

    fault = case.get("fault")
    restore = None
    if fault:
        orig, patched = _make_fault(ev, fault)
        ev.evaluate = patched
        restore = orig
    try:
        rep = orch.run(state, wf, gate_policy="stop", kb_dir=kb_dir, checkpoint_root=run_dir)
        approvals = 0
        while rep["status"] == "PAUSED_NEEDS_REVIEW" and approvals < 3:
            orch.approve(state, rep["stopped_at"])
            approvals += 1
            rep = orch.run(state, wf, gate_policy="stop", kb_dir=kb_dir, checkpoint_root=run_dir)
    finally:
        if restore is not None:
            ev.evaluate = restore
    return state, rep


# --------------------------------------------------------------------------- #
# observations
# --------------------------------------------------------------------------- #
def observe(state, rep, catalog_ids):
    arts = state.get("artifacts", {}) or {}
    reg = state.get("artifact_registry", {}) or {}
    obs = {
        "case_status": rep["status"],
        "artifacts": sorted(arts.keys()),
        "has_recommendation": "product-recommendation" in arts,
        "has_report": "insurance-report" in arts,
        "rec_status": None,
        "primary_is_none": None,
        "product_ids": [],
        "evidence_refs": [],
        "evidence_ids": [],
        "unresolved_evidence_refs": [],
        "repairs_attempted": 0,
        "repairs_succeeded": 0,
        "repairs_failed": 0,
        "hallucinated_products": [],
        "trace_failed_events": 0,
        "report_disclosure": {},
        "report_rendered": "",
    }

    # products referenced anywhere the agent claims a product
    pc = _payload(arts.get("product-candidates"))
    if isinstance(pc, dict):
        for c in (pc.get("candidates") or []):
            if isinstance(c, dict) and c.get("product_id"):
                obs["product_ids"].append(c["product_id"])

    ke = _payload(arts.get("knowledge-evidence"))
    if isinstance(ke, dict):
        obs["evidence_ids"] = [e.get("evidence_id") for e in (ke.get("evidence") or [])
                               if isinstance(e, dict)]

    rec = _payload(arts.get("product-recommendation"))
    if isinstance(rec, dict):
        obs["rec_status"] = rec.get("status")
        prim = rec.get("primary_recommendation")
        obs["primary_is_none"] = prim is None
        for holder in [prim] + list(rec.get("alternatives") or []):
            if isinstance(holder, dict):
                for k in ("product_id", "candidate_product_id"):
                    if holder.get(k):
                        obs["product_ids"].append(holder[k])
                # the recommended product is carried nested as product.product_id -- the
                # hallucination hard gate MUST see it, otherwise a fabricated product in
                # the headline recommendation would slip past a rate that reads 0.
                nested = holder.get("product")
                if isinstance(nested, dict) and nested.get("product_id"):
                    obs["product_ids"].append(nested["product_id"])
        obs["evidence_refs"] = list(rec.get("evidence_refs") or [])
        obs["unresolved_evidence_refs"] = [r for r in obs["evidence_refs"]
                                           if r not in set(obs["evidence_ids"])]

    rep_payload = _payload(arts.get("insurance-report"))
    if isinstance(rep_payload, dict):
        sr = rep_payload.get("structured_report") or {}
        obs["report_disclosure"] = sr.get("disclosure") or {}
        obs["report_rendered"] = rep_payload.get("rendered_report") or ""

    obs["hallucinated_products"] = sorted({p for p in obs["product_ids"]
                                            if p not in catalog_ids})

    # repair accounting from the task mirror
    for t in state.get("tasks", []):
        sid = t.get("stage_id")
        st = (state.get("stages", {}) or {}).get(sid, {})
        attempts = t.get("attempt") or 0
        if attempts > 1:
            obs["repairs_attempted"] += attempts - 1
            if st.get("status") == "COMPLETED":
                obs["repairs_succeeded"] += 1
            else:
                obs["repairs_failed"] += 1

    obs["trace_failed_events"] = sum(1 for r in (state.get("trace") or [])
                                     if r["event"] == "TASK_FAILED")
    obs["state"] = state
    obs["report"] = rep
    return obs


# --------------------------------------------------------------------------- #
# expectation checks
# --------------------------------------------------------------------------- #
def check_case(case, obs, catalog_ids):
    e = case.get("expect", {})
    checks = []

    def ck(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    ck("case_status == %s" % e.get("case_status"), obs["case_status"] == e.get("case_status"),
       obs["case_status"])
    if "waiting_reason" in e:
        w = obs["state"].get("waiting_for_user") or {}
        ck("waiting_reason == %s" % e["waiting_reason"], w.get("reason") == e["waiting_reason"],
           w.get("reason"))
        if e.get("next_questions_nonempty"):
            ck("next_questions non-empty", bool(w.get("next_questions")), w.get("next_questions"))
    if e.get("conflicts_preserved"):
        w = obs["state"].get("waiting_for_user") or {}
        blob = json.dumps(w.get("conflicts") or [], ensure_ascii=False)
        missing = [c for c in e["conflicts_preserved"] if c not in blob]
        ck("conflict candidates preserved", not missing, missing)
    if e.get("all_artifacts"):
        missing = [a for a in CANONICAL_ARTIFACTS if a not in obs["artifacts"]]
        ck("all 9 canonical artifacts present", not missing, missing)
    if e.get("require_report"):
        ck("report produced", obs["has_report"])
    if "recommendation_status" in e:
        ck("recommendation status == %s" % e["recommendation_status"],
           obs["rec_status"] == e["recommendation_status"], obs["rec_status"])
    if "primary_is_none" in e:
        ck("primary_is_none == %s" % e["primary_is_none"],
           obs["primary_is_none"] == e["primary_is_none"], obs["primary_is_none"])
    if "demo_disclosure" in e:
        disc = obs.get("report_disclosure") or {}
        ck("report marks demo products (is_demo == %s)" % e["demo_disclosure"],
           bool(disc.get("is_demo")) == e["demo_disclosure"], disc.get("is_demo"))
        if e["demo_disclosure"]:
            ck("demo disclosure text rendered in the report",
               "DEMO" in (obs.get("report_rendered") or ""), "no DEMO marker in rendered report")
            ck("disclosed product ids are in the catalog",
               all(p not in obs["hallucinated_products"] for p in (disc.get("demo_products") or [])),
               disc.get("demo_products"))
    if e.get("blocked"):
        ck("case blocked (NEEDS_REVIEW)", obs["case_status"] == "NEEDS_REVIEW",
           obs["case_status"])
        ck("trace shows a failed task", obs["trace_failed_events"] > 0,
           obs["trace_failed_events"])
    if "min_repairs_succeeded" in e:
        ck("repairs succeeded >= %s" % e["min_repairs_succeeded"],
           obs["repairs_succeeded"] >= e["min_repairs_succeeded"], obs["repairs_succeeded"])
    for a in e.get("forbidden_artifacts", []):
        ck("artifact %s absent" % a, a not in obs["artifacts"])

    # ---- universal safety checks (apply to every case) ----------------------
    ck("no product outside the Catalog", not obs["hallucinated_products"],
       obs["hallucinated_products"])
    if obs["rec_status"] == "COMPLETE":
        ck("COMPLETE recommendation keeps resolvable provenance",
           obs["evidence_refs"] and not obs["unresolved_evidence_refs"],
           obs["unresolved_evidence_refs"])

    return checks


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    write_baseline = "--write-baseline" in sys.argv
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    with open(os.path.join(REPO, manifest["seeds_file"]), encoding="utf-8") as f:
        base = json.load(f)
    with open(CATALOG, encoding="utf-8") as f:
        catalog_ids = {p["product_id"] for p in json.load(f)["products"]}

    kb_empty = os.path.join(REPO, manifest["empty_kb"])
    wf = orch.load_workflow()

    results = []
    for case in manifest["cases"]:
        state, rep = run_case(case, wf, base, manifest["seeds_file"], kb_empty)
        obs = observe(state, rep, catalog_ids)
        checks = check_case(case, obs, catalog_ids)
        results.append({
            "id": case["id"], "category": case["category"], "desc": case.get("desc"),
            "case_status": obs["case_status"], "rec_status": obs["rec_status"],
            "artifacts": obs["artifacts"], "checks": checks,
            "passed": all(c["ok"] for c in checks),
            "failed_checks": [c["name"] for c in checks if not c["ok"]],
            "hallucinated_products": obs["hallucinated_products"],
            "n_products_referenced": len(obs["product_ids"]),
            "repairs_attempted": obs["repairs_attempted"],
            "repairs_succeeded": obs["repairs_succeeded"],
            "repairs_failed": obs["repairs_failed"],
            "unresolved_evidence_refs": obs["unresolved_evidence_refs"],
            "demo_disclosed": bool((obs.get("report_disclosure") or {}).get("is_demo")),
        })

    # ---------------- metrics (spec §10) ---------------------------------- #
    total = len(results)
    succeeded = sum(1 for r in results if r["passed"])
    task_success_rate = succeeded / total if total else 0.0

    complete_recs = [r for r in results if r["rec_status"] == "COMPLETE"]
    prov_ok = sum(1 for r in complete_recs if not r["unresolved_evidence_refs"])
    provenance_completeness = (prov_ok / len(complete_recs)) if complete_recs else 1.0

    referenced = sum(r["n_products_referenced"] for r in results)
    hallucination_count = sum(len(r["hallucinated_products"]) for r in results)
    product_hallucination_rate = (hallucination_count / referenced) if referenced else 0.0

    # invalid continuation = a case that declared a blocking condition (or a COMPLETE
    # recommendation with unresolvable evidence) yet pushed a decision downstream.
    invalid_continuations = []
    for r in results:
        if not r["passed"] and any("absent" in c for c in r["failed_checks"]):
            invalid_continuations.append(r["id"])
        if r["rec_status"] == "COMPLETE" and r["unresolved_evidence_refs"]:
            invalid_continuations.append(r["id"])
    invalid_continuation_rate = len(invalid_continuations) / total if total else 0.0

    rep_att = sum(r["repairs_attempted"] for r in results)
    rep_ok = sum(r["repairs_succeeded"] for r in results)
    repair_success_rate = (rep_ok / rep_att) if rep_att else 1.0

    # Repair success is reported twice on purpose. The headline rate divides by EVERY
    # attempt, which is dragged down by the adversarial / no-evidence cases whose fault is
    # deliberately NOT repairable — they exist to prove the agent escalates instead of
    # thrashing. The repairable-only rate isolates the loop's real behaviour, and its
    # denominator is stated so a zero-attempt case can never masquerade as success.
    repairable_ids = {c["id"] for c in manifest["cases"] if c["category"] == "repairable"}
    rep_att_repairable = sum(r["repairs_attempted"] for r in results if r["id"] in repairable_ids)
    rep_ok_repairable = sum(r["repairs_succeeded"] for r in results if r["id"] in repairable_ids)
    repair_success_rate_repairable = ((rep_ok_repairable / rep_att_repairable)
                                      if rep_att_repairable else None)

    review_rate = sum(1 for r in results if r["case_status"] == "NEEDS_REVIEW") / total

    hard_gates = {
        "product_hallucination_zero": hallucination_count == 0,
        "critical_provenance_failure_zero": not any(
            r["rec_status"] == "COMPLETE" and r["unresolved_evidence_refs"] for r in results),
        "invalid_continuation_zero": not invalid_continuations,
    }
    gates_ok = all(hard_gates.values())

    metrics = {
        "version": "v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": total,
        "task_success_rate": round(task_success_rate, 4),
        "unsupported_claim_rate": round(1.0 - provenance_completeness, 4),
        "product_hallucination_rate": round(product_hallucination_rate, 4),
        "provenance_completeness": round(provenance_completeness, 4),
        "invalid_continuation_rate": round(invalid_continuation_rate, 4),
        "repair_success_rate": round(repair_success_rate, 4),
        "human_review_rate": round(review_rate, 4),
        "repairs_attempted": rep_att,
        "repairs_succeeded": rep_ok,
        "repair_success_rate_repairable_only": (
            round(repair_success_rate_repairable, 4)
            if repair_success_rate_repairable is not None else None),
        "repairable_repairs_attempted": rep_att_repairable,
        "repairable_repairs_succeeded": rep_ok_repairable,
        "complete_recommendations": len(complete_recs),
        "hard_gates": hard_gates,
        "invalid_continuation_cases": invalid_continuations,
    }

    by_category = {}
    for r in results:
        b = by_category.setdefault(r["category"], {"n": 0, "passed": 0})
        b["n"] += 1
        b["passed"] += 1 if r["passed"] else 0

    out = {"metrics": metrics, "by_category": by_category, "cases": results}
    with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # ---------------- report ---------------------------------------------- #
    lines = []
    lines.append("# Agent Benchmark Report (Step 4 · Phase 3)\n")
    lines.append("> 数字全部来自真实执行（`run_agent_benchmark.py`），无任何手工填写。\n")
    lines.append("## Agent-Level Metrics\n")
    lines.append("| Metric | Value | Meaning |")
    lines.append("|---|---|---|")
    lines.append("| Task Success Rate | %.1f%% (%d/%d) | 期望全部满足的 case 占比 |"
                 % (task_success_rate * 100, succeeded, total))
    lines.append("| Unsupported Claim Rate | %.1f%% | 无证据支撑的关键结论占比（COMPLETE 推荐中溯源不全） |"
                 % (metrics["unsupported_claim_rate"] * 100))
    lines.append("| Product Hallucination Rate | %.1f%% | 推荐产品不在 Catalog 中的比例（目标 0） |"
                 % (product_hallucination_rate * 100))
    lines.append("| Provenance Completeness | %.1f%% | COMPLETE 推荐可完整溯源（Recommendation→Evidence→Document→Chunk） |"
                 % (provenance_completeness * 100))
    lines.append("| Invalid Continuation Rate | %.1f%% | 已判定阻断却继续下推的比例（目标 0） |"
                 % (invalid_continuation_rate * 100))
    lines.append("| Repair Success Rate | %.1f%% (%d/%d) | 修复尝试中最终转正的占比（分母含**故意不可修复**的注入故障） |"
                 % (repair_success_rate * 100, rep_ok, rep_att))
    lines.append("| Repair Success (repairable only) | %s | 仅统计 category=repairable 的尝试，反映 Repair Loop 真实能力 |"
                 % ("%.1f%% (%d/%d)" % (repair_success_rate_repairable * 100,
                                        rep_ok_repairable, rep_att_repairable)
                    if repair_success_rate_repairable is not None else "n/a (0 attempts)"))
    lines.append("| Complete Recommendations | %d | 真正给出具体产品的 case 数（Provenance/Hallucination 指标的分母） |"
                 % len(complete_recs))
    lines.append("| Human Review Rate | %.1f%% | 最终 NEEDS_REVIEW 的 case 占比 |"
                 % (review_rate * 100))
    lines.append("")
    lines.append("## Safety Hard Gates (spec §11)\n")
    lines.append("| Gate | Result |")
    lines.append("|---|---|")
    for k, v in hard_gates.items():
        lines.append("| %s | %s |" % (k, "PASS" if v else "**FAIL**"))
    lines.append("")
    lines.append("## Coverage by Category\n")
    lines.append("| Category | Passed / Total |")
    lines.append("|---|---|")
    for cat, b in sorted(by_category.items()):
        lines.append("| %s | %d / %d |" % (cat, b["passed"], b["n"]))
    lines.append("")
    lines.append("## Cases\n")
    lines.append("| Case | Category | Status | Rec | DEMO? | Checks | Result |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in results:
        lines.append("| %s | %s | %s | %s | %s | %d/%d | %s |" % (
            r["id"], r["category"], r["case_status"], r["rec_status"],
            "yes" if r.get("demo_disclosed") else "-",
            sum(1 for c in r["checks"] if c["ok"]), len(r["checks"]),
            "PASS" if r["passed"] else "FAIL: " + "; ".join(r["failed_checks"])))
    text = "\n".join(lines) + "\n"
    with open(os.path.join(HERE, "report.md"), "w", encoding="utf-8") as f:
        f.write(text)

    if write_baseline:
        baseline = {
            "version": metrics["version"],
            "generated_at": metrics["generated_at"],
            "cases": total,
            "task_success_rate": metrics["task_success_rate"],
            "unsupported_claim_rate": metrics["unsupported_claim_rate"],
            "product_hallucination_rate": metrics["product_hallucination_rate"],
            "provenance_completeness": metrics["provenance_completeness"],
            "invalid_continuation_rate": metrics["invalid_continuation_rate"],
            "repair_success_rate": metrics["repair_success_rate"],
            "human_review_rate": metrics["human_review_rate"],
            "hard_gates": hard_gates,
            "by_category": by_category,
        }
        with open(os.path.join(HERE, "baseline.json"), "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2)

    # ---------------- console --------------------------------------------- #
    print("=" * 78)
    print("AGENT BENCHMARK — %d cases" % total)
    print("=" * 78)
    for r in results:
        print("%s %-26s %-16s %-16s %d/%d" % (
            "OK " if r["passed"] else "XX ", r["id"], r["case_status"],
            r["rec_status"] or "-", sum(1 for c in r["checks"] if c["ok"]), len(r["checks"])))
        if not r["passed"]:
            print("      failed: %s" % "; ".join(r["failed_checks"]))
    print("-" * 78)
    print("task_success_rate=%.4f  hallucination=%.4f  provenance=%.4f  invalid_continuation=%.4f  repair=%.4f  review=%.4f"
          % (task_success_rate, product_hallucination_rate, provenance_completeness,
             invalid_continuation_rate, repair_success_rate, review_rate))
    print("HARD GATES: %s" % ("ALL PASS" if gates_ok else json.dumps(hard_gates)))
    print("RESULT: %s" % ("ALL GREEN" if (gates_ok and succeeded == total) else "FAILURES PRESENT"))
    return 0 if (gates_ok and succeeded == total) else 1


if __name__ == "__main__":
    sys.exit(main())
