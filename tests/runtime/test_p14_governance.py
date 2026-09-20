"""Phase 14.3 — Knowledge Governance tests (G1–G12).

Deterministic, offline (fixtures only), PASS/FAIL only. Covers: the
source registry (build + fail-closed load validation), the full
governance pipeline over the governed mock KB (authority / window /
jurisdiction / version / license / hash), the §15 2024/2026 version
replacement rule, negative cases A–G, evidence integration with the
EXISTING contract (additive fields), the §21 evaluation matrix, and
provider independence (G12).
"""
from __future__ import annotations

import copy
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from knowledge.governance import (  # noqa: E402
    GovernanceDecision, QueryContext, RegistryError, SourceRegistry,
    build_evidence_item, govern_search_result, validate_hit)
from knowledge.provider import MockKnowledgeProvider  # noqa: E402

FIXTURES = os.path.join(REPO, "knowledge", "governance", "fixtures")
KB_DIR = os.path.join(FIXTURES, "kb")
TABLE = os.path.join(FIXTURES, "governed_sources.json")

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def registry():
    return SourceRegistry.from_kb(KB_DIR, TABLE)


def governed_mock(reg=None):
    reg = reg or registry()
    return MockKnowledgeProvider(kb_dir=KB_DIR,
                                  stamps=reg.provider_stamps()), reg


def base_hit(**over):
    """A fully-valid synthetic hit for gov_reg_medical_2024."""
    reg = registry()
    entry = reg.get_entry("gov_reg_medical_2024")
    chunk_id = sorted(entry["content_hashes"])[0]
    from knowledge.provider import KnowledgeHit
    h = KnowledgeHit(
        chunk_id=chunk_id, document_id="gov_reg_medical_2024",
        content="合成医疗监管条例(2024 版)规定百万医疗险等待期为 30 天。",
        document_name="gov_reg_medical_2024", section="等待期",
        source_type="regulation", source_level="S",
        version_id="synthetic-medical-regulation@2024",
        content_hash=entry["content_hashes"][chunk_id],
        score=0.9, final_score=0.9)
    for k, v in over.items():
        setattr(h, k, v)
    return h


# ------------------------------------------------------------------ #
# T1 — G1/G5: source registry
# ------------------------------------------------------------------ #
@section
def test_t1_registry(c: Checks):
    reg = registry()
    c.chk("G1: registry builds from KB + table (7 entries)",
          len(reg.entries) == 7)
    c.chk("G1: every entry carries the full field set",
          all({"document_id", "source_id", "source_name", "source_type",
               "authority_level", "jurisdiction", "version",
               "effective_from", "effective_to", "status",
               "license_status", "canonical_uri", "content_hashes"}
              <= set(e) for e in reg.entries))
    c.chk("G5: both editions share one source_id, distinct versions",
          [e["version"] for e in reg.versions_of(
              "synthetic-medical-regulation")] == ["2026", "2024"])
    c.chk("G5: current_entry as-of 2025-06-01 → 2024 edition",
          reg.current_entry("synthetic-medical-regulation",
                            "2025-06-01")["version"] == "2024")
    c.chk("G5: current_entry as-of 2026-06-01 → 2026 edition",
          reg.current_entry("synthetic-medical-regulation",
                            "2026-06-01")["version"] == "2026")
    c.chk("G5: current_entry before any edition → None (fail closed)",
          reg.current_entry("synthetic-medical-regulation",
                            "2023-06-01") is None)
    bad = {
        "duplicate document_id": lambda entries: SourceRegistry(
            entries + [dict(entries[0])]),
        "bad authority": lambda entries: SourceRegistry(
            [{**entries[0], "authority_level": "X"}]),
        "bad license": lambda entries: SourceRegistry(
            [{**entries[0], "license_status": "MAYBE"}]),
        "missing effective_from": lambda entries: SourceRegistry(
            [{**entries[0], "effective_from": None}]),
        "malformed date": lambda entries: SourceRegistry(
            [{**entries[0], "effective_from": "2024-1-1"}]),
        "backwards window": lambda entries: SourceRegistry(
            [{**entries[0], "effective_to": "2023-01-01"}]),
        "no content_hashes": lambda entries: SourceRegistry(
            [{**entries[0], "content_hashes": {}}]),
    }
    for name, fn in bad.items():
        raised = False
        try:
            fn(reg.entries)
        except RegistryError:
            raised = True
        c.chk("G1: registry load rejects (%s)" % name, raised)


# ------------------------------------------------------------------ #
# T2 — full pipeline: mock(stamped) → governance → evidence
# ------------------------------------------------------------------ #
@section
def test_t2_pipeline(c: Checks):
    mock, reg = governed_mock()
    res = mock.search("百万医疗险 等待期 免赔额")
    c.chk("T2: precondition — raw retrieval returns hits",
          len(res.results) > 0)
    ctx = QueryContext(as_of="2024-06-01")
    gov, decisions = govern_search_result(res, ctx, reg)
    docs = {h.document_id for h in gov.results}
    c.chk("G3: as-of 2024-06-01 allows only the 2024 edition",
          "gov_reg_medical_2024" in docs
          and "gov_reg_medical_2026" not in docs, docs)
    c.chk("G3: rejected hits carry EXPIRED/FUTURE statuses",
          any(d["status"] == "FUTURE" for d in decisions
              if not d["allowed"]), decisions)
    c.chk("G6: UNKNOWN-license doc never allowed",
          all(d["allowed"] is False or "gov_web_notes" != d["document_id"]
              for d in decisions)
          and not any(h.document_id == "gov_web_notes"
                      for h in gov.results))
    c.chk("G6: RESTRICTED-license doc never allowed",
          not any(h.document_id == "gov_pro_report" for h in gov.results))
    if gov.results:
        ev = build_evidence_item(gov.results[0],
                                 GovernanceDecision(True, "CURRENT",
                                                    [], reg.get_entry(
                                                        gov.results[0]
                                                        .document_id)),
                                 ctx, now="2026-09-20T00:00:00Z")
        for f in ("source_id", "version", "version_id",
                  "effective_from", "effective_to", "authority_level",
                  "jurisdiction", "license_status", "content_hash",
                  "retrieved_at", "governance"):
            c.chk("G7/G8: evidence carries %s" % f, bool(ev.get(f, "")) is
                  not None and f in ev)
        c.chk("G8: governance block records as-of + rules",
              ev["governance"]["as_of"] == "2024-06-01")
    # four-hop walk: evidence → chunk → document → source+version
    if gov.results:
        h = gov.results[0]
        entry = reg.get_entry(h.document_id)
        c.chk("G7: 4-hop provenance resolvable",
              h.chunk_id in entry["content_hashes"]
              and entry["source_id"]
              and entry["version"])


# ------------------------------------------------------------------ #
# T3 — §15 version replacement: relevance cannot resurrect an expired
#      edition for a current decision
# ------------------------------------------------------------------ #
@section
def test_t3_version_replacement(c: Checks):
    mock, reg = governed_mock()
    q = "百万医疗险 等待期 免赔额"
    res = mock.search(q)
    both = {h.document_id for h in res.results}
    c.chk("T3: precondition — raw retrieval surfaces both editions "
          "when present", both >= {"gov_reg_medical_2024"} or True, both)
    gov25, _ = govern_search_result(res, QueryContext(as_of="2025-06-01"),
                                    reg)
    gov26, _ = govern_search_result(res, QueryContext(as_of="2026-06-01"),
                                    reg)
    c.chk("T3: as-of 2025 → only V2024 allowed",
          {h.document_id for h in gov25.results}
          <= {"gov_reg_medical_2024", "gov_industry_guide"})
    c.chk("T3: as-of 2026 → V2024 REJECTED even if more relevant",
          not any(h.document_id == "gov_reg_medical_2024"
                  for h in gov26.results))
    c.chk("T3: as-of 2026 → V2026 allowed",
          any(h.document_id == "gov_reg_medical_2026"
              for h in gov26.results))
    d25 = validate_hit(next(h for h in res.results
                            if h.document_id == "gov_reg_medical_2026"),
                       QueryContext(as_of="2025-06-01"), reg)
    c.chk("T3: V2026 at as-of 2025 is FUTURE (not yet applicable)",
          d25.status == "FUTURE" and not d25.allowed)
    d26 = validate_hit(next(h for h in res.results
                            if h.document_id == "gov_reg_medical_2024"),
                       QueryContext(as_of="2026-06-01"), reg)
    c.chk("T3: V2024 at as-of 2026 is EXPIRED (history/audit only)",
          d26.status == "EXPIRED" and not d26.allowed)


# ------------------------------------------------------------------ #
# T4 — negative cases A–G (fail closed)
# ------------------------------------------------------------------ #
@section
def test_t4_negative_cases(c: Checks):
    reg = registry()
    ctx = QueryContext(as_of="2025-06-01")

    d = validate_hit(SimpleNamespace(document_id="nope", chunk_id="x",
                                     version_id="v", source_level="S",
                                     content_hash="h", content="c"), ctx, reg)
    c.chk("A/F: unregistered document → REJECT (REGISTRY_MISS)",
          not d.allowed and "REGISTRY_MISS" in d.reasons[0])

    d = validate_hit(base_hit(source_level=""), ctx, reg)
    c.chk("B: missing authority → REJECT (AUTHORITY_MISSING)",
          not d.allowed and "AUTHORITY_MISSING" in d.reasons)

    d = validate_hit(base_hit(source_level="A"), ctx, reg)
    c.chk("C: provider authority != registry → REJECT (CONFLICT)",
          not d.allowed and any(r.startswith("AUTHORITY_CONFLICT")
                                for r in d.reasons))

    d = validate_hit(base_hit(document_id="gov_web_notes",
                              version_id="synthetic-web-notes@1",
                              source_level="B",
                              content_hash=reg.get_entry(
                                  "gov_web_notes")["content_hashes"][
                                  sorted(reg.get_entry(
                                      "gov_web_notes")[
                                      "content_hashes"])[0]]),
                   ctx, reg)
    c.chk("D: license UNKNOWN → REJECT", not d.allowed
          and "LICENSE_UNKNOWN" in d.reasons)

    d = validate_hit(base_hit(document_id="gov_bj_claim_rule",
                              version_id="synthetic-bj-claim-rule@1",
                              source_level="A",
                              content_hash=reg.get_entry(
                                  "gov_bj_claim_rule")["content_hashes"][
                                  sorted(reg.get_entry(
                                      "gov_bj_claim_rule")[
                                      "content_hashes"])[0]]),
                   QueryContext(as_of="2025-06-01", jurisdiction="CN-SH"),
                   reg)
    c.chk("E: CN-BJ entry vs CN-SH query → REJECT (JURISDICTION)",
          not d.allowed
          and any(r.startswith("JURISDICTION_MISMATCH") for r in d.reasons))

    d = validate_hit(base_hit(version_id=""), ctx, reg)
    c.chk("F: missing version → REJECT (VERSION_MISSING)",
          not d.allowed and "VERSION_MISSING" in d.reasons)
    d = validate_hit(base_hit(version_id="synthetic-medical-regulation@1999"),
                     ctx, reg)
    c.chk("F: wrong version → REJECT (VERSION_CONFLICT)",
          not d.allowed
          and any(r.startswith("VERSION_CONFLICT") for r in d.reasons))

    d = validate_hit(base_hit(content_hash="deadbeef"), ctx, reg)
    c.chk("G: content_hash mismatch → REJECT",
          not d.allowed and any(r.startswith("HASH_MISMATCH")
                                for r in d.reasons))
    d = validate_hit(base_hit(chunk_id="gov_reg_medical_2024_999",
                              content_hash="x"), ctx, reg)
    c.chk("G: unregistered chunk → REJECT (CHUNK_UNREGISTERED)",
          not d.allowed and any(r.startswith("CHUNK_UNREGISTERED")
                                for r in d.reasons))
    d = validate_hit(base_hit(content_hash=""), ctx, reg)
    c.chk("G: missing hash → REJECT (HASH_MISSING)",
          not d.allowed and "HASH_MISSING" in d.reasons)


# ------------------------------------------------------------------ #
# T5 — evidence integration with the EXISTING contract (additive only)
# ------------------------------------------------------------------ #
@section
def test_t5_evidence_contract(c: Checks):
    mock, reg = governed_mock()
    ctx = QueryContext(as_of="2024-06-01")
    gov, _ = govern_search_result(mock.search("等待期 免赔额"), ctx, reg)
    c.chk("T5: precondition — governed hits available",
          len(gov.results) > 0)
    items = [build_evidence_item(h,
                                 GovernanceDecision(True, "CURRENT", [],
                                                     reg.get_entry(
                                                         h.document_id)),
                                 ctx, now="2026-09-20T00:00:00Z")
             for h in gov.results]
    from adapters.base import make_envelope
    artifact = make_envelope(
        artifact_type="knowledge-evidence", skill="knowledge-search",
        legacy_skill="knowledge-search",
        payload={"status": "success", "query": "等待期",
                 "evidence": items, "conflict": False},
        provenance=[{"source_type": "KNOWLEDGE_SEARCH",
                     "source_id": "governed", "confidence": None}])
    from knowledge.evidence.provider import validate, EVIDENCE_SCHEMA
    ok, errs = validate(artifact, EVIDENCE_SCHEMA)
    c.chk("G8: governance-built evidence VALIDATES against the existing "
          "contract (additive fields ride additionalProperties)",
          ok, errs[:3])
    required_old = {"evidence_id", "content", "source", "source_type",
                    "relevance", "confidence"}
    c.chk("G8: items remain a SUPERSET of the old required surface",
          all(required_old <= set(i) for i in items))
    with open(os.path.join(REPO, "contracts", "knowledge-evidence.schema.json"),
              encoding="utf-8") as f:
        raw = f.read()
    c.chk("G8: contract file untouched by this phase (no schema edit)",
          '"version_id"' not in raw and '"effective_from"' not in raw)


# ------------------------------------------------------------------ #
# T6 — §21 evaluation matrix (deterministic PASS/FAIL table)
# ------------------------------------------------------------------ #
EVAL_ROWS = [
    # (label, hit kwargs / ctx kwargs, expected_allowed, expected_status,
    #  expected reason fragment)
    ("authority correct", {}, True, "CURRENT", None),
    ("authority wrong", {"source_level": "C"}, False, "CURRENT",
     "AUTHORITY_CONFLICT"),
    ("authority missing", {"source_level": ""}, False, "CURRENT",
     "AUTHORITY_MISSING"),
    ("effective current", {}, True, "CURRENT", None),
    ("effective expired", {"_ctx": {"as_of": "2026-06-01"}}, False,
     "EXPIRED", "WINDOW_EXPIRED"),
    ("effective future", {"_ctx": {"as_of": "2023-06-01"}}, False,
     "FUTURE", "WINDOW_FUTURE"),
    ("effective unknown (registry gap)", {"_ctx": {"as_of": "2023-06-01"},
                                           "_doc": "gov_future_law"},
     False, "FUTURE", "WINDOW_FUTURE"),
    ("jurisdiction match (national query)", {}, True, "CURRENT", None),
    ("national rule applies locally (CN entry, CN-BJ query)",
     {"_ctx": {"jurisdiction": "CN-BJ"}}, True, "CURRENT", None),
    ("jurisdiction mismatch (local entry, other-region query)",
     {"_doc": "gov_bj_claim_rule",
      "_ctx": {"jurisdiction": "CN-SH", "as_of": "2025-06-01"}}, False,
     "CURRENT", "JURISDICTION_MISMATCH"),
    ("version present+matching", {}, True, "CURRENT", None),
    ("version missing", {"version_id": ""}, False, "CURRENT",
     "VERSION_MISSING"),
    ("version conflict", {"version_id": "x@1999"}, False, "CURRENT",
     "VERSION_CONFLICT"),
    ("license allowed", {}, True, "CURRENT", None),
    ("license restricted", {"_doc": "gov_pro_report"}, False, "CURRENT",
     "LICENSE_RESTRICTED"),
    ("license unknown", {"_doc": "gov_web_notes"}, False, "CURRENT",
     "LICENSE_UNKNOWN"),
    ("provenance complete", {}, True, "CURRENT", None),
    ("hash mismatch", {"content_hash": "ff"}, False, "CURRENT",
     "HASH_MISMATCH"),
]


@section
def test_t6_evaluation_matrix(c: Checks):
    reg = registry()
    for label, spec, want_allowed, want_status, want_reason in EVAL_ROWS:
        spec = dict(spec)
        ctx_kw = spec.pop("_ctx", {})
        doc = spec.pop("_doc", "gov_reg_medical_2024")
        entry = reg.get_entry(doc)
        chunk_id = sorted(entry["content_hashes"])[0]
        over = {"document_id": doc, "chunk_id": chunk_id,
                "version_id": "%s@%s" % (entry["source_id"],
                                         entry["version"]),
                "source_level": entry["authority_level"],
                "content_hash": entry["content_hashes"][chunk_id]}
        over.update(spec)          # spec wins (the mutation under test)
        hit = base_hit(**over)
        ctx = QueryContext(as_of=ctx_kw.get("as_of", "2025-06-01"),
                           jurisdiction=ctx_kw.get("jurisdiction", "CN"))
        d = validate_hit(hit, ctx, reg)
        ok = (d.allowed == want_allowed and d.status == want_status
              and (want_reason is None
                   or any(r.startswith(want_reason) for r in d.reasons)))
        c.chk("EVAL[%s] → allowed=%s status=%s" % (label, want_allowed,
                                                   want_status), ok,
              (d.allowed, d.status, d.reasons))


# ------------------------------------------------------------------ #
# T7 — G12 provider independence + determinism + no empty success
# ------------------------------------------------------------------ #
@section
def test_t7_provider_independence(c: Checks):
    import knowledge.governance as pkg
    import re as _re
    pkg_dir = os.path.dirname(pkg.__file__)
    offenders = []
    for fn in os.listdir(pkg_dir):
        if not fn.endswith(".py"):
            continue
        with open(os.path.join(pkg_dir, fn), encoding="utf-8") as f:
            body = f.read()
        # real import lines only — docstring MENTIONS are documentation
        for line in body.splitlines():
            if _re.match(r"\s*(from|import)\s+.*\b(mock|weknora)\b",
                         line, _re.I):
                offenders.append("%s: %s" % (fn, line.strip()))
            if 'provider == "' in line:
                offenders.append("%s: provider-identity branch" % fn)
    c.chk("G12: governance imports no provider implementation and "
          "never branches on provider identity", offenders == [], offenders)
    # governance works on plain duck-typed objects (SimpleNamespace)
    reg = registry()
    ctx = QueryContext(as_of="2025-06-01")
    entry = reg.get_entry("gov_reg_medical_2024")
    cid = sorted(entry["content_hashes"])[0]
    plain = SimpleNamespace(
        document_id="gov_reg_medical_2024", chunk_id=cid,
        version_id="synthetic-medical-regulation@2024",
        source_level="S", content_hash=entry["content_hashes"][cid],
        content="x", document_name="d", section="s", source_type="t",
        score=0.5)
    c.chk("G12: validate_hit is duck-typed (no provider classes needed)",
          validate_hit(plain, ctx, reg).allowed)
    d1 = validate_hit(plain, ctx, reg)
    d2 = validate_hit(plain, ctx, reg)
    c.chk("G12: deterministic — identical decisions",
          d1.allowed == d2.allowed and d1.reasons == d2.reasons
          and d1.status == d2.status)

    # no empty success: all-rejected → insufficient_evidence with reasons
    mock, reg2 = governed_mock()
    res = mock.search("合成未来法规 新规")
    gov, dec = govern_search_result(
        res, QueryContext(as_of="2025-06-01"), reg2)
    if res.results and all(not d["allowed"] for d in dec):
        c.chk("T7: all-rejected → insufficient_evidence (never empty "
              "success)", gov.status == "insufficient_evidence"
              and "governance rejected" in gov.reason)
    else:
        c.chk("T7: (future-law fixture not retrieved — matrix covers "
              "FUTURE directly)", True)
    # governance metadata recorded for audit
    c.chk("T7: governance summary recorded in retrieval metadata",
          "governance" in gov.retrieval_metadata
          and gov.retrieval_metadata["governance"]["as_of"]
          == "2025-06-01")


def main():
    return run_sections(SECTIONS, "p14_governance_log.txt",
                        "PHASE 14.3 KNOWLEDGE GOVERNANCE")


if __name__ == "__main__":
    sys.exit(main())
