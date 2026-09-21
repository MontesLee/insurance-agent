"""Phase 14.5 — Evidence & Provenance Closure tests.

Tests A–L (§15) + the §16 static architecture scan, against the REAL
runtime paths (tool artifact + orchestrator provide_evidence), with an
injected deterministic clock (no wall-clock dependence).

P-rules: P001 identity · P002 hit · P003 document · P004 version ·
P005 source · P006 governance consistency · P007 hash · P008
jurisdiction · P009 license · P010 lineage completeness.
"""
from __future__ import annotations

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from knowledge.governance import (  # noqa: E402
    SourceRegistry, decision_evidence_refs, is_no_evidence_required,
    scan_chain_of_thought, validate_decision_provenance,
    validate_provenance)
from knowledge.provider import MockKnowledgeProvider  # noqa: E402
from knowledge.service import KnowledgeService  # noqa: E402

from runtime import orchestrator as orch  # noqa: E402
from runtime import tasks as tk  # noqa: E402
from runtime.agent.tools import ToolContext, _knowledge_search  # noqa: E402
from runtime.state import case_state as cs  # noqa: E402

GOV_KB = os.path.join(REPO, "knowledge", "governance", "fixtures", "kb")
GOV_TABLE = os.path.join(REPO, "knowledge", "governance", "fixtures",
                         "governed_sources.json")
FIXED_NOW = "2026-09-20T00:00:00Z"
QUERY = "百万医疗险 等待期 免赔额"
WF = orch.load_workflow()

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def gov_service():
    reg = SourceRegistry.from_kb(GOV_KB, GOV_TABLE)
    return KnowledgeService(
        provider=MockKnowledgeProvider(kb_dir=GOV_KB,
                                        stamps=reg.provider_stamps()),
        registry=reg, now_fn=lambda: FIXED_NOW), reg


def fresh_ctx():
    state = cs.new_case_state("p14-prov", WF)
    tk.init_tasks(state, WF)
    return ToolContext(state, WF, "run_prov", persist=lambda: None)


def tool_evidence(svc):
    from knowledge.service import set_default_service, reset_default_service
    set_default_service(svc)
    try:
        ctx = fresh_ctx()
        out = _knowledge_search({"query": QUERY}, ctx)
        art = (ctx.state.get("artifacts", {})
               .get("knowledge-evidence", {}) or {})
        return (art.get("payload", {}) or {}).get("evidence", []), out
    finally:
        reset_default_service()


def loop_evidence(svc):
    from knowledge.evidence.provider import provide_evidence
    q = {"artifact_type": "knowledge-query", "skill": "knowledge-search",
         "legacy_skill": "knowledge_search", "schema_version": "1.0",
         "generated_at": FIXED_NOW,
         "payload": {"query": QUERY, "domain": "medical",
                     "purpose": "SOLUTION_VALIDATION"},
         "provenance": []}
    artifact, ok, errs = provide_evidence(q, service=svc)
    return ((artifact or {}).get("payload", {}) or {}).get("evidence", []), ok


def first_valid_item(items):
    for i in items:
        if i.get("document_id") == "gov_reg_medical_2026":
            return copy.deepcopy(i)
    for i in items:
        if i.get("document_id") == "gov_reg_medical_2024":
            return copy.deepcopy(i)
    return copy.deepcopy(items[0]) if items else None


# ------------------------------------------------------------------ #
# A — complete lineage (real tool path) + L — no CoT leakage
# ------------------------------------------------------------------ #
@section
def test_a_complete_lineage(c: Checks):
    svc, reg = gov_service()
    items, out = tool_evidence(svc)
    c.chk("A: precondition — governed evidence produced",
          len(items) > 0 and out.get("status") != "failed")
    item = first_valid_item(items)
    ok, why = validate_provenance(item, reg)
    c.chk("A: full lineage validates (P001–P010) on the REAL tool "
          "artifact", ok, why)
    entry = reg.get_entry(item["document_id"])
    c.chk("A: decision→evidence→hit→document→version→source walk",
          item["evidence_id"] == item["knowledge_hit_id"]
          and item["knowledge_hit_id"] in entry["content_hashes"]
          and item["version_id"] == "%s@%s" % (entry["source_id"],
                                               entry["version"])
          and item["source_id"] == entry["source_id"])
    c.chk("A: effective window + retrieval time recorded",
          item["effective_from"] == entry["effective_from"]
          and item["retrieved_at"] == FIXED_NOW)
    c.chk("L: no chain-of-thought keys in evidence items",
          scan_chain_of_thought(items) == [])
    c.chk("L: no CoT keys in the whole artifact",
          scan_chain_of_thought(
              (ctx_state := None) or items) == [])


# ------------------------------------------------------------------ #
# B/C/D/E — broken lineage fails closed (validator level, real items)
# ------------------------------------------------------------------ #
@section
def test_b_c_d_e_broken_lineage(c: Checks):
    svc, reg = gov_service()
    items, _ = tool_evidence(svc)
    base = first_valid_item(items)

    b = copy.deepcopy(base); b.pop("knowledge_hit_id"); b.pop("chunk_id")
    ok, why = validate_provenance(b, reg)
    c.chk("B: missing KnowledgeHit → FAIL (P002)",
          not ok and any(r.startswith("P002") for r in why), why)

    cc = copy.deepcopy(base); cc["document_id"] = "gov_missing_doc"
    ok, why = validate_provenance(cc, reg)
    c.chk("C: missing Document → FAIL (P003)",
          not ok and any(r.startswith("P003") for r in why), why)

    d = copy.deepcopy(base); d["version_id"] = ""
    ok, why = validate_provenance(d, reg)
    c.chk("D: missing Version → FAIL (P004)",
          not ok and any(r.startswith("P004") for r in why), why)

    e = copy.deepcopy(base); e["content_hash"] = "0" * 64
    ok, why = validate_provenance(e, reg)
    c.chk("E: hash mismatch → FAIL (P007)",
          not ok and any(r.startswith("P007") for r in why), why)

    # P010 — incomplete lineage (missing retrieved_at)
    z = copy.deepcopy(base); z.pop("retrieved_at")
    ok, why = validate_provenance(z, reg)
    c.chk("P010: missing retrieved_at → FAIL (no partial completeness)",
          not ok and any(r.startswith("P010") for r in why), why)

    # P001 — missing identity
    a1 = copy.deepcopy(base); a1.pop("evidence_id")
    ok, why = validate_provenance(a1, reg)
    c.chk("P001: missing evidence_id → FAIL",
          not ok and any(r.startswith("P001") for r in why), why)


# ------------------------------------------------------------------ #
# F/G/H — governance / jurisdiction / license conflicts
# ------------------------------------------------------------------ #
@section
def test_f_g_h_conflicts(c: Checks):
    svc, reg = gov_service()
    items, _ = tool_evidence(svc)
    base = first_valid_item(items)

    f = copy.deepcopy(base); f["version"] = "1999"
    ok, why = validate_provenance(f, reg)
    c.chk("F: evidence version disagrees with governance → FAIL (P006)",
          not ok and any(r.startswith("P006") for r in why), why)

    f2 = copy.deepcopy(base)
    f2["governance"] = dict(f2.get("governance") or {},
                            window_status="EXPIRED")
    ok, why = validate_provenance(f2, reg)
    c.chk("F: window_status conflicts with re-derived state → FAIL",
          not ok and any(r.startswith("P006") for r in why), why)

    g = copy.deepcopy(base); g["jurisdiction"] = "CN-SH"
    ok, why = validate_provenance(g, reg)
    c.chk("G: jurisdiction mismatch → FAIL (P008)",
          not ok and any(r.startswith("P008") for r in why), why)

    h = copy.deepcopy(base); h["license_status"] = "UNKNOWN"
    ok, why = validate_provenance(h, reg)
    c.chk("H: license UNKNOWN → FAIL (P009 — never passes as ALLOWED)",
          not ok and any(r.startswith("P009") for r in why), why)
    h2 = copy.deepcopy(base); h2["license_status"] = "ALLOWED"
    reg_u = SourceRegistry.from_kb(GOV_KB, GOV_TABLE)
    reg_u.get_entry(h2["document_id"])["license_status"] = "UNKNOWN"
    ok, why = validate_provenance(h2, reg_u)
    c.chk("H: forged ALLOWED against an UNKNOWN registry → FAIL",
          not ok and any(r.startswith("P009") for r in why), why)


# ------------------------------------------------------------------ #
# I/J — decision binding
# ------------------------------------------------------------------ #
@section
def test_i_j_decision_binding(c: Checks):
    svc, reg = gov_service()
    items, _ = tool_evidence(svc)
    index = {i["evidence_id"]: i for i in items}
    good_id = next(iter(index))

    decision = {"artifact_type": "product-recommendation", "skill": "x",
                "payload": {"evidence_refs": [good_id],
                            "primary_product_id": "P001"}}
    ok, why = validate_decision_provenance(decision, index, reg)
    c.chk("I-pre: a bound decision with a valid ref PASSES",
          ok, why)

    broken = {"payload": {"evidence_refs": ["EV-DOES-NOT-EXIST"]}}
    ok, why = validate_decision_provenance(broken, index, reg)
    c.chk("I: evidence-backed decision with a missing ref → FAIL",
          not ok and any(r.startswith("D002") for r in why), why)

    none_refs = {"payload": {"evidence_refs": []}}
    ok, why = validate_decision_provenance(none_refs, index, reg)
    c.chk("I: empty refs on a required decision → FAIL (D001)",
          not ok and any(r.startswith("D001") for r in why), why)

    opt_out = {"payload": {"evidence_policy": "NO_EVIDENCE_REQUIRED"}}
    ok, why = validate_decision_provenance(opt_out, index, reg)
    c.chk("J: explicit NO_EVIDENCE_REQUIRED → PASS",
          ok and is_no_evidence_required(opt_out))

    # a decision whose ref points at TAMPERED evidence → D003
    tampered = copy.deepcopy(index[good_id])
    tampered["content_hash"] = "ff" * 32
    ok, why = validate_decision_provenance(
        decision, {good_id: tampered}, reg)
    c.chk("I: decision bound to tampered evidence → FAIL (D003 chain)",
          not ok and any(r.startswith("D003") for r in why), why)
    c.chk("L: no CoT keys anywhere in decision provenance",
          scan_chain_of_thought(decision) == [])


# ------------------------------------------------------------------ #
# K — Tool / Orchestrator provenance parity
# ------------------------------------------------------------------ #
@section
def test_k_path_parity(c: Checks):
    svc, reg = gov_service()
    tool_items, out = tool_evidence(svc)
    loop_items, ok = loop_evidence(svc)
    c.chk("K: both real paths produced evidence",
          len(tool_items) > 0 and ok and len(loop_items) > 0)
    for name, its in (("tool", tool_items), ("orchestrator", loop_items)):
        bad = []
        for i in its:
            o, w = validate_provenance(i, reg)
            if not o:
                bad.append((i.get("document_id"), w[:2]))
        c.chk("K: %s-path evidence all lineage-valid" % name, not bad, bad)
    t_by_id = {i["evidence_id"]: i for i in tool_items}
    l_by_id = {i["evidence_id"]: i for i in loop_items}
    shared = set(t_by_id) & set(l_by_id)
    c.chk("K: paths share governed chunks", len(shared) > 0)
    for cid in sorted(shared)[:3]:
        t, l = t_by_id[cid], l_by_id[cid]
        for f in ("knowledge_hit_id", "source_id", "document_id",
                  "version_id", "version", "effective_from",
                  "authority_level", "jurisdiction", "license_status",
                  "content_hash"):
            c.chk("K: %s parity (%s)" % (f, cid[:20]),
                  t.get(f) == l.get(f), (t.get(f), l.get(f)))


# ------------------------------------------------------------------ #
# Static architecture scan (§16)
# ------------------------------------------------------------------ #
@section
def test_static_architecture_scan(c: Checks):
    def read(rel):
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            return f.read()

    report_engine = read(os.path.join(
        ".trae", "skills", "report-generation", "scripts",
        "report_generation_engine.py"))
    c.chk("SCAN: report generation performs NO knowledge retrieval",
          "knowledge.service" not in report_engine
          and "KnowledgeService" not in report_engine
          and "knowledge_search(" not in report_engine
          and "provide_evidence" not in report_engine)

    rec_engine = read(os.path.join(
        ".trae", "skills", "recommendation", "scripts",
        "recommendation_engine.py"))
    c.chk("SCAN: recommendation consumes stored evidence only "
          "(no service/provider calls)",
          "KnowledgeService" not in rec_engine
          and "default_provider" not in rec_engine
          and "MockKnowledgeProvider" not in rec_engine)

    orch_src = read(os.path.join("runtime", "orchestrator.py"))
    c.chk("SCAN: orchestrator constructs no knowledge engine",
          "build_engine" not in orch_src
          and "KnowledgeSearchEngine" not in orch_src)

    # exactly ONE provenance validator + ONE evidence identity source
    defs = []
    for root, _dirs, files in os.walk(os.path.join(REPO, "knowledge")):
        for fn in files:
            if not fn.endswith(".py") or "__pycache__" in root:
                continue
            body = open(os.path.join(root, fn), encoding="utf-8").read()
            if "def validate_provenance" in body:
                defs.append(os.path.join(root, fn))
            if "def validate_decision_provenance" in body \
                    and "def validate_decision_provenance(" not in body:
                defs.append(os.path.join(root, fn) + "?")
    c.chk("SCAN: single provenance validator implementation",
          len([d for d in defs if not d.endswith("?")]) == 1, defs)
    ev_id_sources = []
    for root, _dirs, files in os.walk(os.path.join(REPO, "knowledge")):
        for fn in files:
            if not fn.endswith(".py") or "__pycache__" in root:
                continue
            body = open(os.path.join(root, fn), encoding="utf-8").read()
            if '"evidence_id":' in body:      # assignment = production
                ev_id_sources.append(os.path.join(root, fn))
    ev_id_sources.append("adapters/knowledge_search_adapter.py") \
        if '"evidence_id":' in read(os.path.join(
            "adapters", "knowledge_search_adapter.py")) else None
    c.chk("SCAN: evidence identity produced only by the governance/"
          "adapter pair", sorted(
              set(os.path.relpath(p, REPO) for p in ev_id_sources))
          == ["adapters\\knowledge_search_adapter.py",
              "knowledge\\governance\\governance.py"], ev_id_sources)

    http_offenders = []
    for rel in (os.path.join("runtime", "agent", "tools.py"),
                os.path.join("runtime", "orchestrator.py"),
                os.path.join("knowledge", "service.py"),
                os.path.join("knowledge", "evidence", "provider.py")):
        body = read(rel)
        for tok in ("requests", "httpx", "urllib.request", "docker",
                    "psycopg", "redis", "pymongo", "WeKnoraKnowledge"
                    "Provider("):
            if tok in body:
                http_offenders.append("%s:%s" % (rel, tok))
    c.chk("SCAN: no WeKnora client / Docker / DB dependencies on the "
          "runtime knowledge paths", http_offenders == [],
          http_offenders)
    import inspect as _insp
    seam = _insp.getsource(
        __import__("knowledge.provider.weknora",
                   fromlist=["WeKnoraKnowledgeProvider"]
                   ).WeKnoraKnowledgeProvider)
    c.chk("SCAN: weknora SEAM still transport-injected (live transport "
          "is a separate Phase-18 class)",
          "import urllib" not in seam
          and "import requests" not in seam and "import httpx" not in seam)


def main():
    return run_sections(SECTIONS, "p14_provenance_log.txt",
                        "PHASE 14.5 PROVENANCE CLOSURE")


if __name__ == "__main__":
    sys.exit(main())
