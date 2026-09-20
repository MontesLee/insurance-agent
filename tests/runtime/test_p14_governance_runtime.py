"""Phase 14.4 — Governance RUNTIME integration tests.

Proves the online invariants on the REAL runtime entry points (not
library-level):

  K001 all runtime retrieval enters through KnowledgeProvider (via the
       KnowledgeService composition — bypass scan)
  K002 no Evidence is constructed from a hit that failed Governance
       (online negatives A–E through the tool and the evidence loop)
  K003 provider failure never falls back (weknora-unconfigured → tool
       failure, no mock continuation)
  K004 tool and orchestrator paths use the SAME provider/governance
       (dual-path semantic consistency on the citation tuple)

Plus the §17 online positive (evidence carries the full citation tuple
through BOTH real paths) and determinism.
"""
from __future__ import annotations

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from knowledge.governance import QueryContext, SourceRegistry  # noqa: E402
from knowledge.provider import (MockKnowledgeProvider,  # noqa: E402
                                ProviderUnavailable,
                                WeKnoraKnowledgeProvider)
from knowledge.service import (KnowledgeService, default_registry,  # noqa: E402
                               default_service, reset_default_service,
                               set_default_service)

from runtime import orchestrator as orch  # noqa: E402
from runtime import tasks as tk  # noqa: E402
from runtime.agent.tools import ToolContext, _knowledge_search  # noqa: E402
from runtime.state import case_state as cs  # noqa: E402

GOV_KB = os.path.join(REPO, "knowledge", "governance", "fixtures", "kb")
GOV_TABLE = os.path.join(REPO, "knowledge", "governance", "fixtures",
                         "governed_sources.json")
WF = orch.load_workflow()

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def gov_service(registry=None, stamps_extra=None):
    reg = registry or SourceRegistry.from_kb(GOV_KB, GOV_TABLE)
    stamps = reg.provider_stamps()
    if stamps_extra:
        stamps.update(stamps_extra)
    return KnowledgeService(
        provider=MockKnowledgeProvider(kb_dir=GOV_KB, stamps=stamps),
        registry=reg), reg


def fresh_ctx():
    state = cs.new_case_state("p14-runtime", WF)
    tk.init_tasks(state, WF)
    return ToolContext(state, WF, "run_p14", persist=lambda: None)


def run_tool(query, ctx=None):
    return _knowledge_search({"query": query}, ctx or fresh_ctx())


CITATION = ("source_id", "version_id", "version", "effective_from",
            "effective_to", "authority_level", "jurisdiction",
            "license_status", "content_hash", "retrieved_at")


# ------------------------------------------------------------------ #
# R1 — online positive: the REAL tool path emits governed evidence
# ------------------------------------------------------------------ #
@section
def test_r1_tool_positive(c: Checks):
    svc, reg = gov_service()
    set_default_service(svc)
    try:
        out = run_tool("百万医疗险 等待期 免赔额")
        c.chk("R1: tool succeeds on governed valid sources",
              out.get("status") != "failed", out)
        art = (out.get("data", {}) or {}).get("artifact")
        state_ev = None
        if art is None:  # fetch from state (tool stores then reports id)
            ctx_state = None
        ev = None
        if art:
            ev = art.get("payload", {}).get("evidence", [])
        if not ev:
            # read back from the case state via a fresh tool run's ctx
            ctx = fresh_ctx()
            out2 = run_tool("百万医疗险 等待期 免赔额", ctx)
            ev = ((ctx.state.get("artifacts", {})
                   .get("knowledge-evidence", {})
                   .get("payload", {}) or {}).get("evidence", []))
        c.chk("R1: governed evidence items produced", len(ev) > 0)
        if ev:
            for f in CITATION:
                if f == "effective_to":     # None = open window (legal)
                    c.chk("R1: every item carries effective_to",
                          all(f in i for i in ev))
                    continue
                c.chk("R1: every item carries %s" % f,
                      all(f in i and i[f] not in (None, "") for i in ev),
                      f)
            c.chk("R1: every item carries the governance block",
                  all("governance" in i for i in ev))
            c.chk("R1: items resolve in the registry (4-hop)",
                  all(i["source_id"] and reg.get_entry(i["document_id"])
                      and i["chunk_id"] in reg.get_entry(
                          i["document_id"])["content_hashes"]
                      for i in ev))
            c.chk("R1: no expired edition sneaked in (as-of today)",
                  all(i["document_id"] != "gov_reg_medical_2024"
                      or i["effective_to"] is None for i in ev))
    finally:
        reset_default_service()


# ------------------------------------------------------------------ #
# R2 — online negatives A–E through the REAL tool entry point
# ------------------------------------------------------------------ #
@section
def test_r2_tool_negatives(c: Checks):
    base_svc, reg = gov_service()

    # A: expired — as-of TODAY the 2024 edition window has closed
    set_default_service(base_svc)
    try:
        out = run_tool("合成医疗监管条例 2024 版 免赔额上限")
        state = json.dumps(out, ensure_ascii=False, default=str)
        c.chk("A(expired): 2024-edition-only query fails or excludes "
              "the expired doc", out.get("status") == "failed"
              or "gov_reg_medical_2024" not in state, state[:120])
    finally:
        reset_default_service()

    # A': deterministic expired check at service level (fixed as-of)
    _, dec = None, None
    items, gov, dec, ctx = base_svc.build_evidence(
        "免赔额 等待期", as_of="2026-06-01")
    c.chk("A(expired): as-of 2026 → zero V2024 items (K002)",
          all(i.get("version") != "2024" for i in items))

    # B: jurisdiction — CN-BJ entry vs national query context
    svc_bj, _ = gov_service()
    out = svc_bj.build_evidence("合成北京理赔规则 理赔时限",
                                jurisdiction="CN")
    c.chk("B(jurisdiction): local rule vs national query → no evidence",
          len(out[0]) == 0)

    # C: unknown license — gov_web_notes never yields evidence
    items_c, gov_c, dec_c, _ = base_svc.build_evidence("合成网络资料 "
                                                       "赔付次数")
    c.chk("C(license UNKNOWN): no evidence from UNKNOWN-license source",
          all(i.get("license_status") != "UNKNOWN" for i in items_c))

    # D: registry conflict — provider claims S, registry says B
    stamps = copy.deepcopy(reg.provider_stamps())
    stamps["gov_industry_guide"]["authority_level"] = "S"   # forged claim
    svc_d, _ = gov_service(stamps_extra=stamps)
    items_d, gov_d, dec_d, _ = svc_d.build_evidence("健康告知 既往症")
    c.chk("D(registry conflict): forged authority claim yields no "
          "evidence for that doc",
          all(i.get("document_id") != "gov_industry_guide"
              for i in items_d))

    # E: hash mismatch — tamper EVERY recorded hash of that entry
    reg_t = SourceRegistry.from_kb(GOV_KB, GOV_TABLE)
    entry = reg_t.get_entry("gov_industry_guide")
    for cid in list(entry["content_hashes"]):
        entry["content_hashes"][cid] = "tampered"
    svc_e = KnowledgeService(
        provider=MockKnowledgeProvider(
            kb_dir=GOV_KB, stamps=reg_t.provider_stamps()),
        registry=reg_t)
    items_e, gov_e, dec_e, _ = svc_e.build_evidence("健康告知 既往症")
    c.chk("E(hash mismatch): tampered registry hash → no evidence from "
          "that doc", all(i.get("document_id") != "gov_industry_guide"
                          for i in items_e))
    # and through the real tool with the tampered service injected
    set_default_service(svc_e)
    try:
        out_e = run_tool("健康告知 既往症")
        blob = json.dumps(out_e, ensure_ascii=False, default=str)
        c.chk("E(hash mismatch): tool path stays consistent (fail or "
              "exclude)", out_e.get("status") == "failed"
              or "gov_industry_guide" not in blob)
    finally:
        reset_default_service()


# ------------------------------------------------------------------ #
# R3 — orchestrator path: the evidence LOOP is governed (F-01 closed)
# ------------------------------------------------------------------ #
@section
def test_r3_orchestrator_path(c: Checks):
    from knowledge.evidence import loop as ev_loop
    solution = {"artifact_type": "solution-plan", "skill": "solution",
                "legacy_skill": "solution", "schema_version": "1.0",
                "generated_at": "2026-09-20T00:00:00Z",
                "payload": {"solutions": [{"solution_id": "S1",
                                           "solution_type": "MEDICAL",
                                           "direction": "医疗"}]},
                "provenance": []}
    # default path (no injection): templates were designed for the
    # fixtures KB — the DEFAULT governed service must serve it
    rnd2 = ev_loop.request_evidence(solution, source_kind="solution",
                                    purpose="SOLUTION_VALIDATION")
    ev2 = ((rnd2.get("evidence") or {}).get("payload", {})
           .get("evidence", []))
    c.chk("R3: DEFAULT service governs the default KB (loop round ok)",
          rnd2.get("ok") and len(ev2) > 0, rnd2.get("errors"))
    if ev2:
        for f in ("source_id", "version_id", "effective_from",
                  "authority_level", "jurisdiction", "license_status",
                  "content_hash"):
            c.chk("R3: loop evidence carries %s (citation passthrough)"
                  % f, all(f in i for i in ev2), f)
        c.chk("R3: every loop item resolves in the default registry",
              all(default_registry().get_entry(i.get("document_id", ""))
                  is not None for i in ev2))
    c.chk("R3: loop never mutated the requesting artifact",
          rnd2.get("source_unchanged") is True)
    # injected governed service (gov KB): the template query may
    # legitimately abstain there — the round must still be ok + honest
    svc, _ = gov_service()
    rnd = ev_loop.request_evidence(solution, source_kind="solution",
                                   purpose="SOLUTION_VALIDATION",
                                   service=svc)
    ev = ((rnd.get("evidence") or {}).get("payload", {})
          .get("evidence", []))
    c.chk("R3: injected-service round ok (evidence or honest "
          "abstention)", rnd.get("ok")
          and (len(ev) > 0
               or (rnd.get("evidence") or {}).get("payload", {})
               .get("status") == "insufficient_evidence"))


# ------------------------------------------------------------------ #
# R4 — dual-path semantic consistency (K004, §18)
# ------------------------------------------------------------------ #
@section
def test_r4_dual_path_consistency(c: Checks):
    # same query, same service: the TOOL path vs the ORCHESTRATOR path
    # (provide_evidence — the exact function the evidence loop calls)
    from knowledge.evidence.provider import provide_evidence
    svc, reg = gov_service()
    query = "百万医疗险 等待期"
    set_default_service(svc)
    try:
        ctx = fresh_ctx()
        run_tool(query, ctx)
        tool_ev = ((ctx.state.get("artifacts", {})
                    .get("knowledge-evidence", {})
                    .get("payload", {}) or {}).get("evidence", []))
    finally:
        reset_default_service()
    q_artifact = {"artifact_type": "knowledge-query",
                  "skill": "knowledge-search",
                  "legacy_skill": "knowledge_search",
                  "schema_version": "1.0",
                  "generated_at": "2026-09-20T00:00:00Z",
                  "payload": {"query": query, "domain": "medical",
                              "purpose": "SOLUTION_VALIDATION"},
                  "provenance": []}
    artifact, ok, errs = provide_evidence(q_artifact, service=svc)
    loop_ev = ((artifact or {}).get("payload", {}).get("evidence", []))
    c.chk("R4: orchestrator-path round ok", ok, errs[:2])
    c.chk("R4: both real paths produced evidence",
          len(tool_ev) > 0 and len(loop_ev) > 0)
    tool_by_chunk = {i["chunk_id"]: i for i in tool_ev}
    loop_by_chunk = {i["chunk_id"]: i for i in loop_ev}
    shared = set(tool_by_chunk) & set(loop_by_chunk)
    c.chk("R4: the two paths agree on at least one governed chunk",
          len(shared) > 0)
    for cid in sorted(shared)[:3]:
        t, l = tool_by_chunk[cid], loop_by_chunk[cid]
        for f in ("source_id", "version", "version_id",
                  "effective_from", "effective_to", "authority_level",
                  "jurisdiction", "license_status", "content_hash"):
            c.chk("R4: %s identical across paths (%s)" % (f, cid[:24]),
                  t.get(f) == l.get(f), (t.get(f), l.get(f)))
        c.chk("R4: eligibility identical (%s)" % cid[:24],
              reg.get_entry(t["document_id"]) is not None
              and reg.get_entry(l["document_id"]) is not None)


# ------------------------------------------------------------------ #
# R5 — K003: provider failure never falls back (online, real tool)
# ------------------------------------------------------------------ #
@section
def test_r5_no_fallback_online(c: Checks):
    from knowledge.provider import (reset_default_provider,
                                    set_default_provider)
    set_default_provider(WeKnoraKnowledgeProvider())   # no transport
    try:
        out = run_tool("百万医疗险 等待期")
        c.chk("K003: unconfigured weknora → tool FAILS (no mock "
              "continuation)", out.get("status") == "failed")
        c.chk("K003: failure names the fail-closed policy",
              "fail-closed" in out.get("summary", ""))
        c.chk("K003: no evidence stored on provider failure",
              "knowledge-evidence" not in json.dumps(
                  out, default=str)[:400])
    finally:
        reset_default_provider()
        reset_default_service()


# ------------------------------------------------------------------ #
# R6 — K001 bypass scan + determinism
# ------------------------------------------------------------------ #
@section
def test_r6_bypass_scan_and_determinism(c: Checks):
    offenders = []
    for rel in (os.path.join("runtime", "orchestrator.py"),
                os.path.join("runtime", "agent", "tools.py"),
                os.path.join("knowledge", "evidence", "loop.py"),
                os.path.join("knowledge", "evidence", "provider.py")):
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            lines = f.read().splitlines()
        in_legacy_fn = False
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if s.startswith("def "):
                in_legacy_fn = s.startswith("def build_engine")
                continue
            if in_legacy_fn:
                continue        # the sanctioned legacy/test helper body
            if s.startswith("#") or '"""' in ln:
                continue
            if "build_engine(" in s or "KnowledgeSearchEngine(" in s \
                    or "from knowledge.rag" in s:
                offenders.append("%s:%d: %s" % (rel, i, s[:70]))
    c.chk("K001: no runtime path constructs a retrieval engine "
          "(bypass scan; legacy helper body excluded)", offenders == [],
          offenders[:4])
    svc, _ = gov_service()
    a = svc.build_evidence("百万医疗险 等待期 免赔额", as_of="2026-06-01")
    b = svc.build_evidence("百万医疗险 等待期 免赔额", as_of="2026-06-01")
    c.chk("R6: deterministic service output (fixed as-of)",
          json.dumps(a[1].to_dict(), default=str, sort_keys=True)
          == json.dumps(b[1].to_dict(), default=str, sort_keys=True))
    src = open(os.path.join(REPO, "knowledge", "service.py"),
               encoding="utf-8").read()
    c.chk("R6: service delegates to the single governance package "
          "(no rule copies)",
          "from knowledge.governance import" in src
          and "LICENSE_UNKNOWN" not in src
          and "JURISDICTION_MISMATCH" not in src)


def main():
    return run_sections(SECTIONS, "p14_governance_runtime_log.txt",
                        "PHASE 14.4 GOVERNANCE RUNTIME INTEGRATION")


if __name__ == "__main__":
    sys.exit(main())
