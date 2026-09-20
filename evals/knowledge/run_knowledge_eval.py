#!/usr/bin/env python3
"""Knowledge Evaluation Harness — Phase 14.6.

Deterministic, offline, independently runnable quality gate over the
Phase 14.1–14.5 knowledge layer:

    Provider → Retrieval → Governance → Evidence → Provenance → Decision

Principles (phase brief §6/§19/§20): exact/field/rule comparison only
(no LLM judge, no semantic scores); every metric carries an explicit
denominator; SAFETY violations are HARD GATES — no averaging can mask
them. The harness TESTS the system; it never modifies business rules.

Datasets: evals/knowledge/dataset/*.json (golden cases with expected
outputs). Direction of dependency: evals → production code ONLY
(production never imports evals/ — asserted by the test suite).

Usage:  python evals/knowledge/run_knowledge_eval.py
Exit 0 iff all cases pass AND all hard gates are clean.
Report JSON lands in tmp/knowledge_eval_report.json.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from knowledge.governance import (  # noqa: E402
    GovernanceDecision, QueryContext, SourceRegistry, build_evidence_item,
    validate_decision_provenance, validate_hit, validate_provenance)
from knowledge.evidence.attribute_grounding import (  # noqa: E402
    ground_product_attributes)
from knowledge.provider import (KnowledgeHit, MockKnowledgeProvider,  # noqa: E402
                                ProviderUnavailable,
                                WeKnoraKnowledgeProvider)
from knowledge.service import KnowledgeService  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset")
GOV_KB = os.path.join(REPO, "knowledge", "governance", "fixtures", "kb")
GOV_TABLE = os.path.join(REPO, "knowledge", "governance", "fixtures",
                         "governed_sources.json")
FIXED_NOW = "2026-09-20T00:00:00Z"


def _now():
    return FIXED_NOW


def load_cases():
    cases = []
    for fn in ("retrieval_cases.json", "governance_cases.json",
               "provenance_cases.json", "decision_cases.json"):
        with open(os.path.join(DATA, fn), encoding="utf-8") as f:
            doc = json.load(f)
        cases.extend(next(iter(doc.values())))
    return cases


def gov_registry():
    return SourceRegistry.from_kb(GOV_KB, GOV_TABLE)


def gov_service(reg=None):
    reg = reg or gov_registry()
    return KnowledgeService(
        provider=MockKnowledgeProvider(kb_dir=GOV_KB,
                                        stamps=reg.provider_stamps()),
        registry=reg, now_fn=_now), reg


def subset_service(document_ids, as_kb_dir=None):
    """Service over a temp KB containing ONLY the named docs (subset of
    the governed corpus) — used for abstention scenarios."""
    reg_all = gov_registry()
    rows = [e for e in reg_all.entries if e["document_id"] in document_ids]
    tmp = as_kb_dir or tempfile.mkdtemp(prefix="keval_",
                                        dir=os.path.join(REPO, "tmp"))
    table_path = os.path.join(tmp, "subset_sources.json")
    rows_wo_hashes = [{k: v for k, v in r.items() if k != "content_hashes"}
                      for r in rows]
    with open(table_path, "w", encoding="utf-8") as f:
        json.dump(rows_wo_hashes, f, ensure_ascii=False, indent=1)
    for d in document_ids:
        shutil.copy(os.path.join(GOV_KB, d + ".md"), tmp)
    reg = SourceRegistry.from_kb(tmp, table_path)
    return KnowledgeService(
        provider=MockKnowledgeProvider(kb_dir=tmp,
                                        stamps=reg.provider_stamps()),
        registry=reg, now_fn=_now), reg


def empty_service():
    tmp = tempfile.mkdtemp(prefix="keval_empty_",
                           dir=os.path.join(REPO, "tmp"))
    reg = SourceRegistry([])
    return KnowledgeService(
        provider=MockKnowledgeProvider(kb_dir=tmp, stamps={}),
        registry=reg, now_fn=_now)


class ContractFixtureProvider:
    """Provider B for contract-equivalence evaluation: a DETERMINISTIC
    fixture provider satisfying the same KnowledgeProvider contract
    over the SAME governed corpus. It is NOT WeKnora and claims
    nothing about WeKnora — it proves upper-layer semantics survive a
    provider swap (same governance/evidence/provenance output)."""

    name = "contract-fixture"

    def __init__(self, registry, query_map):
        self._reg = registry
        self._map = query_map      # keyword -> document_id

    def search(self, query, filters=None, top_k=None):
        from knowledge.rag.store import chunk_markdown
        hits = []
        for kw, doc in self._map.items():
            if kw in query:
                entry = self._reg.get_entry(doc)
                with open(os.path.join(GOV_KB, doc + ".md"),
                          encoding="utf-8-sig") as f:
                    chunks = chunk_markdown(f.read(), doc, doc)
                for ch in chunks[: (top_k or 5)]:
                    import hashlib
                    hits.append(KnowledgeHit(
                        chunk_id=ch.chunk_id, document_id=doc,
                        content=ch.content, document_name=doc,
                        section=ch.section, source_type=entry["source_type"],
                        source_level=entry["authority_level"],
                        version_id="%s@%s" % (entry["source_id"],
                                              entry["version"]),
                        content_hash=hashlib.sha256(
                            ch.content.encode("utf-8")).hexdigest(),
                        score=0.9,
                        metadata={}))
                break
        from knowledge.provider.base import KnowledgeSearchResult
        return KnowledgeSearchResult(
            status="success" if hits else "insufficient_evidence",
            query=query, results=hits,
            retrieval_metadata={"provider": self.name,
                                "retrieval_method": "sparse_rrf"})


def base_hit(reg, document_id):
    entry = reg.get_entry(document_id)
    if entry is None:          # unregistered-document case (REGISTRY_MISS)
        return KnowledgeHit(
            chunk_id="x_000", document_id=document_id,
            content="unregistered", document_name=document_id,
            section="s", source_type="internal", source_level="B",
            version_id="x@1", content_hash="h", score=0.9), "x_000"
    chunk_id = sorted(entry["content_hashes"])[0]
    return KnowledgeHit(
        chunk_id=chunk_id, document_id=document_id,
        content="合成证据内容 %s" % document_id, document_name=document_id,
        section="s", source_type=entry["source_type"],
        source_level=entry["authority_level"],
        version_id="%s@%s" % (entry["source_id"], entry["version"]),
        content_hash=entry["content_hashes"][chunk_id], score=0.9), chunk_id


# ------------------------------------------------------------------ #
# case evaluation
# ------------------------------------------------------------------ #
def eval_retrieval(case, svc, reg):
    inp = case["input"]
    items, gov, dec, ctx = svc.build_evidence(
        inp["query"], top_k=inp.get("top_k", 5), as_of=inp["as_of"],
        jurisdiction=inp.get("jurisdiction", "CN"))
    exp = case["expected"]
    if exp.get("empty"):
        return ("PASS" if not items else "FAIL"), \
               {"items": len(items),
                "detail": "expected abstention, got %d items" % len(items)}
    if "top_k_contains_document" in exp:
        docs = {i["document_id"] for i in items}
        want = exp["top_k_contains_document"]
        return ("PASS" if want in docs else "FAIL"), {"docs": sorted(docs)}
    if "rank1_section_contains" in exp:
        top = items[0] if items else {}
        sec = top.get("section", "") + top.get("content", "")[:120]
        return ("PASS" if exp["rank1_section_contains"] in sec
                else "FAIL"), {"rank1": top.get("document_id"),
                               "section": top.get("section")}
    return "FAIL", {"detail": "unknown expectation"}


def eval_governance(case, svc, reg):
    inp = case["input"]
    hit, _ = base_hit(reg, inp["document_id"])
    for k, v in (inp.get("overrides") or {}).items():
        setattr(hit, k, v)
    ctx = QueryContext(as_of=inp["as_of"],
                       jurisdiction=inp.get("jurisdiction", "CN"))
    d = validate_hit(hit, ctx, reg)
    exp = case["expected"]
    ok = d.allowed == exp.get("allowed") \
        and (exp.get("status") is None or d.status == exp["status"]) \
        and (exp.get("rule") is None
             or any(r.startswith(exp["rule"]) for r in d.reasons))
    return ("PASS" if ok else "FAIL"), \
           {"allowed": d.allowed, "status": d.status,
            "reasons": d.reasons[:3]}


def eval_abstention(case):
    inp = case["input"]
    scen = inp["scenario"]
    if scen == "empty_kb":
        svc = empty_service()
        items, gov, dec, ctx = svc.build_evidence(
            inp["query"], as_of=inp["as_of"])
        ok = len(items) == 0
        return ("PASS" if ok else "FAIL"), {"items": len(items)}
    if scen == "expired_only":
        svc, _ = subset_service({"gov_reg_medical_2024"})
        items, gov, dec, ctx = svc.build_evidence(
            inp["query"], as_of=inp["as_of"])
        ok = len(items) == 0
        return ("PASS" if ok else "FAIL"), {"items": len(items)}
    if scen == "unknown_license_only":
        svc, _ = subset_service({"gov_web_notes"})
        items, gov, dec, ctx = svc.build_evidence(
            inp["query"], as_of=inp["as_of"])
        ok = len(items) == 0
        return ("PASS" if ok else "FAIL"), {"items": len(items)}
    if scen == "wrong_jurisdiction":
        svc, reg = gov_service()
        items, gov, dec, ctx = svc.build_evidence(
            inp["query"], as_of=inp["as_of"],
            jurisdiction=inp.get("jurisdiction", "CN"))
        ok = len(items) == 0
        return ("PASS" if ok else "FAIL"), {"items": len(items)}
    if scen == "provider_error":
        svc = KnowledgeService(
            provider=WeKnoraKnowledgeProvider(),   # no transport
            registry=gov_registry(), now_fn=_now)
        try:
            svc.build_evidence(inp["query"], as_of=inp["as_of"])
            return "FAIL", {"detail": "expected ProviderUnavailable"}
        except ProviderUnavailable:
            return "PASS", {"detail": "fail-closed provider error"}
    return "FAIL", {"detail": "unknown scenario %s" % scen}


def _mutate(case, reg):
    inp = case["input"]
    doc = inp.get("base_document")
    hit, chunk_id = base_hit(reg, doc)
    ctx = QueryContext(as_of=inp["as_of"],
                       jurisdiction=inp.get("jurisdiction", "CN"))
    item = build_evidence_item(
        hit, GovernanceDecision(True, "CURRENT", [], reg.get_entry(doc)),
        ctx, now=FIXED_NOW)
    m = inp.get("mutate")
    if m == "flip_hash_char":
        hit.content_hash = ("0" if hit.content_hash[0] != "0" else "1") \
            + hit.content_hash[1:]
        item["content_hash"] = hit.content_hash
    elif m == "version_to_2024":
        hit.version_id = "synthetic-medical-regulation@2024"
        item["version_id"] = hit.version_id
        item["version"] = "2024"
    elif m == "license_unknown_to_allowed":
        item["license_status"] = "ALLOWED"      # forged vs registry UNKNOWN
    elif m == "expired_to_active_metadata":
        item["effective_to"] = None
        item["governance"] = dict(item.get("governance") or {},
                                  window_status="CURRENT")
    elif m == "authority_flip":
        hit.source_level = "B" if hit.source_level != "B" else "S"
        item["authority_level"] = hit.source_level
    elif m == "remove_hit_id":
        item.pop("knowledge_hit_id", None)
        item.pop("chunk_id", None)
    elif m == "bogus_document":
        item["document_id"] = "gov_missing_doc"
    elif m == "remove_retrieved_at":
        item.pop("retrieved_at", None)
    elif m == "jurisdiction_swap":
        item["jurisdiction"] = "CN-SH"
    elif m is None:
        pass
    return hit, item, ctx


def eval_mutation(case, reg):
    hit, item, ctx = _mutate(case, reg)
    d = validate_hit(hit, ctx, reg)
    pok, pwhy = validate_provenance(item, reg)
    exp = case["expected"]
    gov_ok = (not d.allowed) if exp.get("governance_denied") else True
    prov_ok = True
    if "provenance_invalid" in exp:
        prov_ok = (not pok) and any(
            w.startswith(exp.get("provenance_rule", "")) for w in pwhy)
    ok = gov_ok and prov_ok
    return ("PASS" if ok else "FAIL"), \
           {"gov_denied": not d.allowed, "gov_reasons": d.reasons[:2],
            "prov_ok": pok, "prov_why": pwhy[:3]}


def eval_provenance(case, reg):
    c2 = dict(case)
    c2["input"] = dict(case["input"])
    hit, item, ctx = _mutate(c2, reg)
    ok, why = validate_provenance(item, reg)
    exp = case["expected"]
    passed = (ok == exp["valid"]) and (
        not exp["valid"]
        and any(w.startswith(exp.get("rule", "")) for w in why)
        or exp["valid"])
    return ("PASS" if passed else "FAIL"), {"valid": ok, "why": why[:3]}


def _run_evidence_for_decision(as_of, tampered=False):
    svc, reg = gov_service()
    items, gov, dec, ctx = svc.build_evidence(
        "百万医疗险 等待期 免赔额", top_k=3, as_of=as_of)
    if tampered and items:
        items = [dict(items[0], content_hash="ff" * 32)]
    return items, reg


def eval_decision(case):
    inp = case["input"]
    items, reg = _run_evidence_for_decision(
        inp["as_of"], tampered=(inp.get("evidence") == "tampered"))
    index = {i["evidence_id"]: i for i in items}
    dec = copy.deepcopy(inp["decision"])
    refs = dec.get("payload", {}).get("evidence_refs", [])
    if refs == ["FROM_RUN"] and items:
        dec["payload"]["evidence_refs"] = [items[0]["evidence_id"]]
    ok, why = validate_decision_provenance(dec, index, reg)
    exp = case["expected"]
    passed = (ok == exp["ok"]) and (
        exp.get("rule") is None
        or any(w.startswith(exp["rule"]) for w in why))
    return ("PASS" if passed else "FAIL"), {"ok": ok, "why": why[:3]}


def eval_grounding(case):
    inp = case["input"]
    exp = case["expected"]
    g = ground_product_attributes(inp["product"],
                                  [{"content": t}
                                   for t in inp["evidence_texts"]])
    attr = g["attributes"].get(exp["attribute"], {})
    ok = attr.get("status") == exp["status"]
    return ("PASS" if ok else "FAIL"), {"got": attr.get("status"),
                                        "rollup": g.get("rollup")}


def eval_parity(case):
    inp = case["input"]
    reg = gov_registry()
    if inp.get("paths") == ["tool", "orchestrator"]:
        svc, _ = gov_service(reg)
        from knowledge.service import (reset_default_service,
                                       set_default_service)
        from runtime import orchestrator as orch
        from runtime import tasks as tk
        from runtime.agent.tools import ToolContext, _knowledge_search
        from runtime.state import case_state as cs
        wf = orch.load_workflow()
        query = inp["query"].replace("tool_vs_orchestrator", "").strip()
        set_default_service(svc)
        try:
            state = cs.new_case_state("keval-parity", wf)
            tk.init_tasks(state, wf)
            ctx = ToolContext(state, wf, "keval", persist=lambda: None)
            _knowledge_search({"query": query}, ctx)
            tool_items = ((state.get("artifacts", {})
                           .get("knowledge-evidence", {})
                           .get("payload", {}) or {}).get("evidence", []))
        finally:
            reset_default_service()
        from knowledge.evidence.provider import provide_evidence
        q = {"artifact_type": "knowledge-query", "skill": "knowledge-search",
             "legacy_skill": "knowledge_search", "schema_version": "1.0",
             "generated_at": FIXED_NOW,
             "payload": {"query": query, "domain": "medical",
                         "purpose": "SOLUTION_VALIDATION"},
             "provenance": []}
        artifact, ok, errs = provide_evidence(q, service=svc)
        orch_items = ((artifact or {}).get("payload", {})
                      .get("evidence", []))
        a = {i["evidence_id"]: i for i in tool_items}
        b = {i["evidence_id"]: i for i in orch_items}
        shared = set(a) & set(b)
        if not shared:
            return "FAIL", {"detail": "no shared chunks between paths"}
        mismatch = []
        for cid in shared:
            for f in case["expected"]["fields_equal"]:
                if a[cid].get(f) != b[cid].get(f):
                    mismatch.append((cid[:20], f))
        return ("PASS" if not mismatch and ok else "FAIL"), \
               {"shared": len(shared), "mismatch": mismatch[:3]}

    # provider A (mock) vs provider B (contract fixture) — NOT WeKnora
    svc_a, _ = gov_service(reg)
    svc_b = KnowledgeService(
        provider=ContractFixtureProvider(
            reg, {"等待期": "gov_reg_medical_2026",
                  "免赔额": "gov_reg_medical_2026",
                  "健康告知": "gov_industry_guide",
                  "既往症": "gov_industry_guide"}),
        registry=reg, now_fn=_now)
    items_a, _, _, _ = svc_a.build_evidence(inp["query"], top_k=5,
                                             as_of=inp["as_of"])
    items_b, _, _, _ = svc_b.build_evidence(inp["query"], top_k=5,
                                             as_of=inp["as_of"])
    a = {i["evidence_id"]: i for i in items_a}
    b = {i["evidence_id"]: i for i in items_b}
    shared = set(a) & set(b)
    if not shared:
        return "FAIL", {"detail": "no shared governed chunks (A=%d B=%d)"
                        % (len(a), len(b))}
    mismatch = []
    for cid in shared:
        for f in case["expected"]["fields_equal"]:
            if a[cid].get(f) != b[cid].get(f):
                mismatch.append((cid[:20], f))
    return ("PASS" if not mismatch else "FAIL"), \
           {"shared": len(shared), "mismatch": mismatch[:3]}


# ------------------------------------------------------------------ #
# runner / metrics / gates
# ------------------------------------------------------------------ #
def run_all():
    cases = load_cases()
    svc, reg = gov_service()
    results = []
    for case in cases:
        cat = case["category"]
        try:
            if cat == "retrieval":
                status, detail = eval_retrieval(case, svc, reg)
            elif cat == "governance":
                status, detail = eval_governance(case, svc, reg)
            elif cat == "abstention":
                status, detail = eval_abstention(case)
            elif cat in ("mutation",):
                status, detail = eval_mutation(case, reg)
            elif cat == "provenance":
                status, detail = eval_provenance(case, reg)
            elif cat == "decision":
                status, detail = eval_decision(case)
            elif cat == "grounding":
                status, detail = eval_grounding(case)
            elif cat == "parity":
                status, detail = eval_parity(case)
            else:
                status, detail = "FAIL", {"detail": "unknown category"}
        except Exception as e:  # noqa: BLE001 — a crash IS a failure
            status, detail = "FAIL", {"detail": "exception: %s"
                                            % str(e)[:120]}
        results.append({"case_id": case["case_id"], "category": cat,
                        "status": status, "hard_gate": case.get(
                            "hard_gate", "none"), "detail": detail})
    return results


def aggregate(results):
    def n(pred):
        return sum(1 for r in results if pred(r))

    ret = [r for r in results if r["category"] == "retrieval"]
    ret_hit = [r for r in ret if r["status"] == "PASS"]
    irrelevant = [r for r in ret if r["hard_gate"] == "irrelevant_retrieval"]
    gov = [r for r in results if r["category"] == "governance"]
    prov = [r for r in results if r["category"] == "provenance"]
    absts = [r for r in results if r["category"] == "abstention"]
    par = [r for r in results if r["category"] == "parity"]
    dec = [r for r in results if r["category"] == "decision"]
    grd = [r for r in results if r["category"] == "grounding"]
    mut = [r for r in results if r["category"] == "mutation"]
    # governance confusion matrix (from PASS/FAIL + expected verdict)
    ga = {c["case_id"]: c for c in load_cases()}
    ta = td = fa = fd = 0
    for r in gov:
        exp = ga[r["case_id"]]["expected"]["allowed"]
        if r["status"] == "PASS" and exp:
            ta += 1
        elif r["status"] == "PASS" and not exp:
            td += 1
        elif r["status"] == "FAIL" and exp:
            fd += 1        # expected ALLOW, denied → false deny
        else:
            fa += 1        # expected DENY, allowed-or-wrong → false allow
    metrics = {
        "retrieval": {
            "hit_at_k": "%d/%d" % (len(ret_hit), len(ret)),
            "hit_at_k_rate": round(len(ret_hit) / (len(ret) or 1), 4),
            "miss_rate": round(1 - len(ret_hit) / (len(ret) or 1), 4),
            "irrelevant_retrieval_rate":
                "%d/%d" % (sum(1 for r in irrelevant
                               if r["status"] == "FAIL"), len(irrelevant)),
        },
        "governance": {
            "true_allow": ta, "true_deny": td,
            "false_allow": fa, "false_deny": fd,
            "denominator": len(gov),
        },
        "provenance": {
            "complete_lineage_rate":
                "%d/%d" % (sum(1 for r in prov if r["status"] == "PASS"),
                           len(prov)),
            "broken_lineage_detection_rate": "%d/%d" % (
                sum(1 for r in prov if r["status"] == "PASS"), len(prov)),
        },
        "abstention": {
            "correct_abstention_rate":
                "%d/%d" % (sum(1 for r in absts if r["status"] == "PASS"),
                           len(absts)),
        },
        "decision": {"pass": "%d/%d" % (
            sum(1 for r in dec if r["status"] == "PASS"), len(dec))},
        "grounding": {"pass": "%d/%d" % (
            sum(1 for r in grd if r["status"] == "PASS"), len(grd))},
        "mutation": {"detected": "%d/%d" % (
            sum(1 for r in mut if r["status"] == "PASS"), len(mut))},
        "provider_equivalence": {"contract_equivalence_rate": "%d/%d" % (
            sum(1 for r in par if r["status"] == "PASS"), len(par))},
        "totals": {"cases": len(results),
                   "passed": sum(1 for r in results
                                 if r["status"] == "PASS")},
    }
    return metrics


def hard_gates(results):
    """§20: any safety violation ⇒ OVERALL FAIL. Counted from cases
    whose hard_gate names a SAFETY class and whose expectation FAILED
    (expectations encode the safe outcome; failing one is unsafe)."""
    violations = {}
    for r in results:
        if r["hard_gate"] in ("none", "false_deny"):
            continue          # false_deny is a quality issue, not safety
        if r["status"] == "FAIL":
            violations[r["hard_gate"]] = violations.get(
                r["hard_gate"], 0) + 1
    return violations


def main():
    results = run_all()
    metrics = aggregate(results)
    gates = hard_gates(results)
    ok = (metrics["totals"]["passed"] == metrics["totals"]["cases"]
          and not gates)
    lines = ["", "KNOWLEDGE EVALUATION (Phase 14.6) — %s"
             % ("ALL GREEN" if ok else "FAILURES PRESENT"), ""]
    for r in results:
        lines.append("[%s] %-8s %-8s %s %s"
                     % (r["status"], r["category"], r["case_id"],
                        r["hard_gate"],
                        json.dumps(r["detail"], ensure_ascii=False)[:90]))
    lines += ["", "METRICS: " + json.dumps(metrics, ensure_ascii=False,
                                           indent=1)]
    lines += ["HARD GATES: " + (json.dumps(gates) if gates else "CLEAN"),
              "OVERALL: %s" % ("PASS" if ok else "FAIL")]
    text = "\n".join(lines)
    print(text)
    out = os.path.join(REPO, "tmp", "knowledge_eval_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"results": results, "metrics": metrics,
                   "hard_gates": gates, "overall":
                       "PASS" if ok else "FAIL"}, f, ensure_ascii=False,
                  indent=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
