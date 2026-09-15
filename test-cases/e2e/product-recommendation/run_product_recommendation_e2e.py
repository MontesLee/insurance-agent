#!/usr/bin/env python3
"""Step 2 E2E: Solution -> Evidence -> Candidate -> Recommendation.

Per spec section 21 the NEW links (Evidence, Candidate, Recommendation) are REALLY
executed against the real engines -- they are not replayed from fixtures. The upstream
Requirement / Risk / Gap / Solution artifacts may come from fixtures.

Chain executed per case:
    SolutionPlan
      -> evidence.request.from_solution()          (real query construction)
      -> evidence.provider.provide_evidence()      (real retrieval over the domain corpus)
      -> product_candidate_engine.run()            (real catalog filtering)
      -> invoke-product-recommendation.run()       (real recommendation over real candidates)

Exit 0 only if every check passes.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# product-recommendation -> e2e -> test-cases -> insurance-agent
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

CAND_SCRIPTS = os.path.join(REPO_ROOT, ".trae", "skills", "product-candidate-provider", "scripts")
REC_SCRIPTS = os.path.join(REPO_ROOT, ".trae", "skills", "recommendation", "scripts")
DEFAULT_KB = os.path.join(REPO_ROOT, "domain", "insurance", "references")

for p in (REPO_ROOT, CAND_SCRIPTS, REC_SCRIPTS):
    if p not in sys.path:
        sys.path.insert(0, p)

from knowledge.evidence import request as ev_request  # noqa: E402
from knowledge.evidence import provider as ev_provider  # noqa: E402
import product_candidate_engine as cand_engine  # noqa: E402
from product_candidate_engine import load_catalog, load_rules as load_cand_rules  # noqa: E402


def _load_rec_module():
    path = os.path.join(REC_SCRIPTS, "invoke-product-recommendation.py")
    spec = importlib.util.spec_from_file_location("invoke_product_recommendation", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Every expect key a case may declare. Anything outside this set is a manifest bug.
RECOGNIZED_EXPECT_KEYS = {
    "id", "provider_status", "recommendation_status", "min_evidence", "max_evidence",
    "require_evidence_trace", "candidate_count", "candidate_count_gt", "admissible_count",
    "all_candidates_evidence_missing", "all_ineligible", "expect_rejected",
    "next_information_needed_nonempty", "primary_product_id",
    "forbidden_primary_product_ids", "primary_evidence_refs_nonempty",
    "not_recommended_contains",
}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Results:
    def __init__(self):
        self.checks = []

    def chk(self, name, cond, detail=""):
        self.checks.append((name, bool(cond), detail))

    @property
    def failed(self):
        return [c for c in self.checks if not c[1]]


def run_case(case_file, expect, res, kb_dir=DEFAULT_KB, catalog=None, cand_rules=None):
    case = _load(case_file)
    cid = expect["id"]

    solution_plan = case["solution_plan"]
    coverage_gap_analysis = case.get("coverage_gap_analysis")
    client_profile = case.get("client_profile")
    sols = solution_plan.get("payload", {}).get("solutions") or []
    sol = sols[0] if sols else {}

    # ---- 1. Evidence Request (real) -------------------------------------- #
    q = ev_request.from_solution(sol, purpose="PRODUCT_VALIDATION", requester="step2-e2e")
    res.chk(f"[{cid}] Evidence Request 由 Solution 真实生成",
            bool(q.get("payload", {}).get("query")),
            q.get("payload", {}).get("query", ""))
    related = q.get("payload", {}).get("related_artifact_ids") or []
    res.chk(f"[{cid}] Evidence Request 携带 Solution/Gap 溯源",
            any(str(x).startswith("SOL") for x in related)
            and any(str(x).startswith("GAP") for x in related),
            str(related))

    # ---- 2. Knowledge Search -> Knowledge Evidence (real) ---------------- #
    eng = ev_provider.build_engine(kb_dir)
    ev, ev_ok, ev_errs = ev_provider.provide_evidence(q, engine=eng)
    res.chk(f"[{cid}] KnowledgeEvidence 契约校验通过", ev_ok, "; ".join(ev_errs))
    payload = (ev or {}).get("payload", {})
    items = payload.get("evidence", []) or []
    if "min_evidence" in expect:
        res.chk(f"[{cid}] 检索到 >= {expect['min_evidence']} 条证据",
                len(items) >= expect["min_evidence"], f"actual={len(items)}")
    if "max_evidence" in expect:
        res.chk(f"[{cid}] 证据条数 <= {expect['max_evidence']}",
                len(items) <= expect["max_evidence"], f"actual={len(items)}")
    if expect.get("require_evidence_trace") and items:
        ok_doc = all(i.get("document_id") for i in items)
        ok_chunk = all(i.get("chunk_id") for i in items)
        prov_ok = all(
            any(p.get("source_type") == "DOCUMENT" for p in (i.get("provenance") or []))
            and any(p.get("source_type") == "CHUNK" for p in (i.get("provenance") or []))
            for i in items)
        res.chk(f"[{cid}] 每条证据都有 document_id（Recommendation→Document 可解析）", ok_doc, "")
        res.chk(f"[{cid}] 每条证据都有 chunk_id（Recommendation→Chunk 可解析）", ok_chunk, "")
        res.chk(f"[{cid}] 每条证据 provenance 含 DOCUMENT+CHUNK", prov_ok, "")

    # ---- 3. Product Candidate Provider (real) ---------------------------- #
    cand_in = {
        "client_profile": client_profile,
        "coverage_gap_analysis": coverage_gap_analysis,
        "solution_plan": solution_plan,
        "knowledge_evidence": ev,
    }
    if case.get("requested_product_ids"):
        cand_in["requested_product_ids"] = case["requested_product_ids"]
    cand_out, c_ok, c_errs = cand_engine.run(cand_in, cand_rules, catalog)
    res.chk(f"[{cid}] Candidate Provider 执行成功", c_ok, "; ".join(c_errs))
    res.chk(f"[{cid}] provider.status 符合预期",
            cand_out.get("status") == expect.get("provider_status"),
            f"expected={expect.get('provider_status')} actual={cand_out.get('status')}")

    candidates = cand_out.get("candidates") or []
    if "candidate_count" in expect:
        res.chk(f"[{cid}] 候选数量 == {expect['candidate_count']}",
                len(candidates) == expect["candidate_count"], f"actual={len(candidates)}")
    if "candidate_count_gt" in expect:
        res.chk(f"[{cid}] 候选数量 > {expect['candidate_count_gt']}",
                len(candidates) > expect["candidate_count_gt"], f"actual={len(candidates)}")
    if "admissible_count" in expect:
        res.chk(f"[{cid}] 准入候选数 == {expect['admissible_count']}",
                len(cand_out.get("admissible_candidate_ids") or []) == expect["admissible_count"],
                f"actual={len(cand_out.get('admissible_candidate_ids') or [])}")

    # Candidate validity: every candidate must come from the catalog (no invented product).
    catalog_ids = {p["product_id"] for p in (catalog or load_catalog()).get("products", [])}
    res.chk(f"[{cid}] 所有候选都来自 Product Catalog（无虚构产品）",
            all(c.get("product_id") in catalog_ids for c in candidates),
            str([c.get("product_id") for c in candidates if c.get("product_id") not in catalog_ids]))
    res.chk(f"[{cid}] 所有候选 is_demo=true",
            all(c.get("is_demo") for c in candidates), "")

    if expect.get("all_candidates_evidence_missing"):
        res.chk(f"[{cid}] 全部候选 evidence=MISSING",
                bool(candidates) and all(not (c.get("evidence") or {}).get("available")
                                         for c in candidates),
                str([(c.get("product_id"), (c.get("evidence") or {}).get("status"))
                     for c in candidates]))
    if expect.get("all_ineligible"):
        res.chk(f"[{cid}] 全部候选 eligibility=INELIGIBLE",
                bool(candidates) and all((c.get("eligibility") or {}).get("status") == "INELIGIBLE"
                                         for c in candidates),
                str([(c.get("product_id"), (c.get("eligibility") or {}).get("status"))
                     for c in candidates]))

    for pid, codes in (expect.get("expect_rejected") or {}).items():
        hit = [r for r in (cand_out.get("rejected") or []) if r.get("product_id") == pid]
        res.chk(f"[{cid}] {pid} 被拒绝且原因含 {codes}",
                bool(hit) and all(c in (hit[0].get("reason_codes") or []) for c in codes),
                str(hit[0].get("reason_codes")) if hit else "not rejected")

    if expect.get("next_information_needed_nonempty"):
        res.chk(f"[{cid}] NO_CANDIDATES 时给出 next_information_needed",
                bool(cand_out.get("next_information_needed")),
                str(cand_out.get("next_information_needed")))

    # ---- 4. Recommendation (real) ---------------------------------------- #
    rec_mod = _load_rec_module()
    v2_input = {
        "requirement_analysis": case.get("requirement_analysis") or {},
        "risk_assessment": case.get("risk_assessment") or {},
        "coverage_gap_analysis": coverage_gap_analysis or {},
        "solution_plan": solution_plan,
        "knowledge_evidence": ev,
        "product_candidates": cand_out,
        "constraints": case.get("constraints"),
    }
    rec, warns = rec_mod.run(v2_input)
    rpayload = rec.get("payload", {})
    res.chk(f"[{cid}] Recommendation 产物无契约校验错误",
            not rec.get("_validation_errors"), str(rec.get("_validation_errors") or ""))
    res.chk(f"[{cid}] recommendation.status 符合预期",
            rpayload.get("status") == expect.get("recommendation_status"),
            f"expected={expect.get('recommendation_status')} actual={rpayload.get('status')}")

    primary = rpayload.get("primary_recommendation") or {}
    got_pid = (primary.get("product") or {}).get("product_id")
    if "primary_product_id" in expect:
        res.chk(f"[{cid}] 主推荐产品 == {expect['primary_product_id']}",
                got_pid == expect["primary_product_id"], f"actual={got_pid}")
    for bad in (expect.get("forbidden_primary_product_ids") or []):
        res.chk(f"[{cid}] 主推荐不得为 {bad}", got_pid != bad, f"actual={got_pid}")
    if expect.get("primary_evidence_refs_nonempty"):
        res.chk(f"[{cid}] 主推荐带 evidence_refs",
                bool(rpayload.get("evidence_refs")), str(rpayload.get("evidence_refs")))
    if "not_recommended_contains" in expect:
        blob = json.dumps(rpayload.get("not_recommended") or [], ensure_ascii=False)
        res.chk(f"[{cid}] not_recommended 含 {expect['not_recommended_contains']}",
                expect["not_recommended_contains"] in blob, blob[:200])

    # ---- 5. Provenance trace (spec section 22) --------------------------- #
    if got_pid:
        cand_hit = [c for c in candidates if c.get("product_id") == got_pid]
        if cand_hit:
            c0 = cand_hit[0]
            res.chk(f"[{cid}] 追溯链 Recommendation→Product→Candidate 成立",
                    c0.get("candidate_id") is not None
                    and any(str(x).startswith("SOL") for x in [c0.get("solution_id")])
                    and bool(c0.get("related_gap_ids")),
                    f"candidate={c0.get('candidate_id')} solution={c0.get('solution_id')} "
                    f"gaps={c0.get('related_gap_ids')}")
            ev_ids = (c0.get("evidence") or {}).get("evidence_ids") or []
            resolvable = all(
                any(i.get("evidence_id") == e for i in items) for e in ev_ids) if ev_ids else False
            res.chk(f"[{cid}] 追溯链 Candidate→Evidence→Document/Chunk 可解析",
                    bool(ev_ids) and resolvable,
                    f"evidence_ids={ev_ids} corpus={len(items)}")

    return {"case": cid, "evidence_status": payload.get("status"),
            "evidence_count": len(items),
            "provider_status": cand_out.get("status"),
            "candidates": len(candidates),
            "admissible": cand_out.get("admissible_candidate_ids") or [],
            "recommendation_status": rpayload.get("status"),
            "primary_product_id": got_pid,
            "not_recommended": [n.get("reason") for n in (rpayload.get("not_recommended") or [])]}


def main():
    manifest = _load(os.path.join(HERE, "manifest.json"))
    res = Results()
    catalog = load_catalog()
    cand_rules = load_cand_rules()
    kb = os.environ.get("STEP2_KB_DIR", DEFAULT_KB)

    summaries = []
    for entry in manifest["cases"]:
        exp = dict(entry.get("expect") or {})
        exp["id"] = entry["id"]
        # Anti-fake-pass guard: a manifest key the runner does not implement would be
        # silently ignored, so an unrecognised key is a FAILURE, not a no-op.
        unknown = set(exp) - RECOGNIZED_EXPECT_KEYS - {"id"}
        res.chk(f"[{exp['id']}] manifest 期望键全部被实现（无静默忽略）", not unknown,
                "unrecognised: " + ", ".join(sorted(unknown)))
        if "expect" not in entry:
            res.chk(f"[{exp['id']}] manifest 含 expect 块", False, "missing 'expect'")
            continue
        try:
            summaries.append(run_case(os.path.join(HERE, entry["file"]), exp, res,
                                      kb_dir=kb, catalog=catalog, cand_rules=cand_rules))
        except Exception as e:  # noqa: BLE001
            import traceback
            res.chk(f"[{exp['id']}] 执行无异常", False, repr(e))
            traceback.print_exc()

    for name, ok, detail in res.checks:
        print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else ""))
    print()
    print("--- CASE SUMMARY ---")
    for s in summaries:
        print(json.dumps(s, ensure_ascii=False))

    passed = sum(1 for _, ok, _ in res.checks if ok)
    total = len(res.checks)
    print()
    print(f"STEP2 E2E: {passed}/{total} passed")
    if res.failed:
        print("RESULT: FAILURES PRESENT")
        sys.exit(1)
    print("RESULT: ALL GREEN")
    sys.exit(0)


if __name__ == "__main__":
    main()
