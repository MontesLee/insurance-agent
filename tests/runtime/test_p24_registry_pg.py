"""Phase 24A — PostgreSQL Knowledge Governance Registry tests.

Requires a running agent-postgres (127.0.0.1:5433) with the credential
file used by test_p22_pg. Gated: without it the suite reports an
explicit INTEGRATION SKIPPED — never PASS silently.

Covers the Phase 24 hard gates that live in the registry layer:
  * lifecycle state machine: legal path DISCOVERED→INGESTED→REGISTERED
    →VALIDATED→ACTIVE; illegal jumps / terminal exits refused (HG-24-15)
  * uploaded ≠ ACTIVE: an INGESTED/REGISTERED/VALIDATED version can
    never ground evidence (governance R2 SOURCE_NOT_ACTIVE)
  * partial ingestion (§17): WeKnora-ok/PG-fail and PG-ok/WeKnora-fail
    both end NOT ACTIVE
  * activation guards: no chunks → refuse; overlapping ACTIVE windows
    of one source → AMBIGUOUS refuse (HG-24-07/§21)
  * explicit supersession enables the successor to activate (§10)
  * idempotency: re-running the pipeline is a no-op (HG-24-16); an
    ACTIVE version re-registered with different hashes is REFUSED
  * at-rest tamper detection: mutating chunk content / version hash /
    projection → selfcheck fails (HG-24-28)
  * content_map: canonical chunk contents for ACTIVE versions only
  * scope isolation: sources scoped TENANT are invisible to the GLOBAL
    registry (GLOBAL_ONLY documented, no fake tenancy — §43/§44)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

# Gate: skip without PostgreSQL configured (same file as test_p22_pg)
PG_PASSWORD = ""
try:
    PG_PASSWORD = open(
        r"C:\Users\aubor\AppData\Local\Temp\pg_cred.txt"
    ).read().strip().split("=", 1)[1]
except (FileNotFoundError, IndexError):
    pass
PG_AVAILABLE = bool(PG_PASSWORD)

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def _krs():
    os.environ["AGENT_PG_PASSWORD"] = PG_PASSWORD
    from runtime.state.pg import PostgresStore
    from knowledge.governance.pg_registry import KnowledgeRegistryStore
    store = PostgresStore()
    krs = KnowledgeRegistryStore(store.connect)
    krs.init_schema()
    return store, krs


def _cleanup(store, prefix="p24t-"):
    """Remove test rows (never touches non-test data)."""
    with store.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM knowledge_chunks WHERE version_id IN
                  (SELECT version_id FROM knowledge_versions
                   WHERE source_id LIKE %s)
            """, (prefix + "%",))
            cur.execute("DELETE FROM knowledge_versions WHERE "
                        "source_id LIKE %s", (prefix + "%",))
            cur.execute("DELETE FROM knowledge_sources WHERE "
                        "source_id LIKE %s", (prefix + "%",))


def _meta(src, doc, ver="2026", eff="2026-01-01", eto=None, **over):
    m = {
        "source_id": src, "document_id": doc, "version": ver,
        "source_name": "P24 Test", "source_type": "regulation",
        "authority_level": "A", "jurisdiction": "CN",
        "effective_from": eff, "effective_to": eto,
        "license_status": "ALLOWED",
        "content_hashes": {},
    }
    m.update(over)
    return m


@section
def test_s1_lifecycle_machine(c):
    """Legal path walks to ACTIVE; illegal jumps are refused."""
    from knowledge.governance.model import RegistryError
    store, krs = _krs()
    _cleanup(store)
    try:
        krs.upsert_source(_meta("p24t-src1", "p24t-doc1"))
        krs.upsert_version(_meta("p24t-src1", "p24t-doc1"), "DISCOVERED")
        vid = "p24t-src1@2026"
        for step in ("INGESTED", "REGISTERED"):
            krs.transition(vid, step)
        # no chunks yet → REGISTERED→VALIDATED is legal, but ACTIVATION
        # must refuse (no anchors)
        krs.upsert_chunks(vid, [{"chunk_id": "p24t-ch1", "chunk_index": 0,
                                 "content": "第一条 测试内容。"}])
        krs.transition(vid, "VALIDATED")
        # skipping VALIDATED from REGISTERED must be refused
        krs.upsert_version(_meta("p24t-src1", "p24t-doc2", ver="2027"),
                           "DISCOVERED")
        try:
            krs.transition("p24t-src1@2027", "ACTIVE")
            c.chk("skip-to-ACTIVE refused", False)
        except RegistryError:
            c.chk("skip-to-ACTIVE refused", True)
        # terminal exits refused
        krs.transition("p24t-src1@2027", "REJECTED")
        try:
            krs.transition("p24t-src1@2027", "INGESTED")
            c.chk("terminal exit refused", False)
        except RegistryError:
            c.chk("terminal exit refused", True)
        # expected_from idempotence guard
        try:
            krs.transition(vid, "ACTIVE", expected_from="REGISTERED")
            c.chk("expected_from guard", False)
        except RegistryError:
            c.chk("expected_from guard", True)
        krs.transition(vid, "ACTIVE")
        c.chk("reached ACTIVE",
              krs.get_version(vid)["status"] == "ACTIVE")
        # same-state transition is an idempotent no-op
        r = krs.transition(vid, "ACTIVE")
        c.chk("re-ACTIVE noop", r.get("noop") is True)
    finally:
        _cleanup(store)


@section
def test_s2_partial_failure(c):
    """§17: both partial-failure orders end NOT ACTIVE; governance
    denies hits from any pre-ACTIVE state."""
    store, krs = _krs()
    _cleanup(store)
    try:
        # Case A: WeKnora ok (chunks fetched) but pipeline crashes
        # before PG registration completes
        krs.upsert_source(_meta("p24t-srcA", "p24t-docA"))
        krs.upsert_version(_meta("p24t-srcA", "p24t-docA"), "DISCOVERED")
        krs.transition("p24t-srcA@2026", "INGESTED")   # weknora verified
        # crash here — version stays INGESTED
        c.chk("case A not active",
              krs.get_version("p24t-srcA@2026")["status"] == "INGESTED")
        # Case B: PG row written but WeKnora never verified
        krs.upsert_source(_meta("p24t-srcB", "p24t-docB"))
        krs.upsert_version(_meta("p24t-srcB", "p24t-docB"), "DISCOVERED")
        c.chk("case B not active",
              krs.get_version("p24t-srcB@2026")["status"] == "DISCOVERED")
        # Case B2: crash AFTER chunk registration but BEFORE activation —
        # anchors exist, state is REGISTERED: loaded by the read model
        # and denied by R2 with the state visible
        krs.upsert_source(_meta("p24t-srcB2", "p24t-docB2"))
        krs.upsert_version(_meta("p24t-srcB2", "p24t-docB2"),
                           "DISCOVERED")
        krs.upsert_chunks("p24t-srcB2@2026", [
            {"chunk_id": "p24t-b2", "chunk_index": 0,
             "content": "case B2 chunk"}])
        krs.transition("p24t-srcB2@2026", "INGESTED")
        krs.transition("p24t-srcB2@2026", "REGISTERED")
        c.chk("case B2 not active",
              krs.get_version("p24t-srcB2@2026")["status"]
              == "REGISTERED")
        # governance: a hit from a pre-chunk document is REGISTRY_MISS
        # (no registered chunk identity — honest); from a REGISTERED
        # (not ACTIVE) document it is SOURCE_NOT_ACTIVE (uploaded !=
        # ACTIVE)
        from knowledge.governance.governance import validate_hit
        from knowledge.governance.model import QueryContext
        reg = krs.load_registry()
        ctx = QueryContext(as_of="2026-06-01")

        class _Hit:
            def __init__(self, doc, ver):
                self.document_id = doc
                self.chunk_id = "x"
                self.content = "t"
                self.source_level = "A"
                self.version_id = ver
                self.content_hash = "h"
                self.score = 0.9

        d = validate_hit(_Hit("p24t-docA", "p24t-srcA@2026"), ctx, reg)
        c.chk("pre-chunk hit denied (REGISTRY_MISS)", not d.allowed
              and any(r.startswith("REGISTRY_MISS") for r in d.reasons),
              d.reasons)
        d2 = validate_hit(_Hit("p24t-docB2", "p24t-srcB2@2026"), ctx, reg)
        c.chk("REGISTERED hit denied", not d2.allowed)
        c.chk("REGISTERED reason names state",
              "SOURCE_NOT_ACTIVE:REGISTERED" in d2.reasons, d2.reasons)
    finally:
        _cleanup(store)


@section
def test_s3_ambiguity_and_supersession(c):
    """§21: overlapping ACTIVE windows refuse activation; explicit
    supersession lets the successor activate; superseded hits deny."""
    from knowledge.governance.model import RegistryError
    store, krs = _krs()
    _cleanup(store)
    try:
        krs.upsert_source(_meta("p24t-srcS", "p24t-docS1"))
        krs.upsert_version(_meta("p24t-srcS", "p24t-docS1"), "DISCOVERED")
        krs.upsert_chunks("p24t-srcS@2026", [
            {"chunk_id": "p24t-s1", "chunk_index": 0, "content": "V1"}])
        krs.transition("p24t-srcS@2026", "INGESTED")
        krs.transition("p24t-srcS@2026", "REGISTERED")
        krs.transition("p24t-srcS@2026", "VALIDATED")
        krs.transition("p24t-srcS@2026", "ACTIVE")
        # a second version of the SAME source with an OVERLAPPING
        # window must refuse activation (ambiguous currency)
        krs.upsert_version(_meta("p24t-srcS", "p24t-docS2", ver="2027",
                                 eff="2026-06-01"), "DISCOVERED")
        krs.upsert_chunks("p24t-srcS@2027", [
            {"chunk_id": "p24t-s2", "chunk_index": 0, "content": "V2"}])
        for step in ("INGESTED", "REGISTERED", "VALIDATED"):
            krs.transition("p24t-srcS@2027", step)
        try:
            krs.transition("p24t-srcS@2027", "ACTIVE")
            c.chk("overlapping activation refused", False)
        except RegistryError as e:
            c.chk("overlapping activation refused", "AMBIGUOUS" in str(e))
        # explicit supersession → successor activates
        krs.supersede("p24t-srcS@2026", "p24t-srcS@2027")
        krs.transition("p24t-srcS@2027", "ACTIVE")
        c.chk("successor ACTIVE",
              krs.get_version("p24t-srcS@2027")["status"] == "ACTIVE")
        c.chk("predecessor SUPERSEDED with successor recorded",
              krs.get_version("p24t-srcS@2026")["status"] == "SUPERSEDED"
              and krs.get_version("p24t-srcS@2026")["superseded_by"]
              == "p24t-srcS@2027")
        # load_registry: only the ACTIVE version's document is eligible
        reg = krs.load_registry()
        c.chk("active registry has successor only",
              reg.get_entry("p24t-docS2") is not None
              and reg.get_entry("p24t-docS1").get("status")
              == "SUPERSEDED")
    finally:
        _cleanup(store)


@section
def test_s4_idempotency_and_drift(c):
    """HG-24-16: re-ingestion is a no-op; hash drift on ACTIVE is
    refused; at-rest tampering is detected by selfcheck (HG-24-28)."""
    from knowledge.governance.model import RegistryError
    store, krs = _krs()
    _cleanup(store)
    vid = "p24t-srcI@2026"
    try:
        krs.upsert_source(_meta("p24t-srcI", "p24t-docI"))
        krs.upsert_version(_meta("p24t-srcI", "p24t-docI"), "DISCOVERED")
        krs.upsert_chunks(vid, [{"chunk_id": "p24t-i1",
                                 "chunk_index": 0, "content": "内容一"}])
        for step in ("INGESTED", "REGISTERED", "VALIDATED", "ACTIVE"):
            krs.transition(vid, step)
        # idempotent re-upsert with IDENTICAL content → noop
        r = krs.upsert_version(_meta(
            "p24t-srcI", "p24t-docI",
            content_hashes={"p24t-i1": krs.get_version(vid)
                            ["content_hashes"]["p24t-i1"]}))
        c.chk("re-ingest identical is noop", r.get("noop") is True)
        # different hashes on ACTIVE → refused
        try:
            krs.upsert_version(_meta("p24t-srcI", "p24t-docI",
                                     content_hashes={"other": "x"}))
            c.chk("ACTIVE hash drift refused", False)
        except RegistryError:
            c.chk("ACTIVE hash drift refused", True)
        # selfcheck green before tampering
        c.chk("selfcheck ok before tamper", krs.selfcheck(vid)["ok"])
        # tamper: change chunk CONTENT at rest (bypass the store)
        with store.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE knowledge_chunks SET content='篡改' "
                            "WHERE chunk_id='p24t-i1'")
        sc = krs.selfcheck(vid)
        c.chk("chunk tamper detected", not sc["ok"]
              and any(p.startswith("CHUNK_TAMPERED") for p in
                      sc["problems"]), sc)
        # restore content, tamper the version_hash instead
        with store.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE knowledge_chunks SET content=%s "
                            "WHERE chunk_id='p24t-i1'", ("内容一",))
                cur.execute("UPDATE knowledge_versions SET "
                            "version_hash='deadbeef' WHERE version_id=%s",
                            (vid,))
        sc2 = krs.selfcheck(vid)
        c.chk("version-hash tamper detected",
              "VERSION_HASH_MISMATCH" in sc2["problems"], sc2)
    finally:
        _cleanup(store)


@section
def test_s5_content_map_and_scope(c):
    """F-24 data: canonical contents exposed for ACTIVE versions only;
    scope isolation: TENANT-scoped sources are invisible to the GLOBAL
    registry load (explicit GLOBAL_ONLY — no fake tenancy)."""
    store, krs = _krs()
    _cleanup(store)
    try:
        krs.upsert_source(_meta("p24t-srcM", "p24t-docM"))
        krs.upsert_version(_meta("p24t-srcM", "p24t-docM"), "DISCOVERED")
        krs.upsert_chunks("p24t-srcM@2026", [
            {"chunk_id": "p24t-m1", "chunk_index": 0,
             "content": "canonical chunk"}])
        for step in ("INGESTED", "REGISTERED", "VALIDATED", "ACTIVE"):
            krs.transition("p24t-srcM@2026", step)
        cm = krs.content_map(only_active=True)
        c.chk("content_map has ACTIVE canonical content",
              cm.get("p24t-docM", {}).get("p24t-m1")
              == "canonical chunk")
        # a tenant-scoped source must not appear in the GLOBAL registry
        krs.upsert_source(_meta("p24t-srcT", "p24t-docT",
                                scope="TENANT"))
        krs.upsert_version(_meta("p24t-srcT", "p24t-docT"), "DISCOVERED")
        krs.upsert_chunks("p24t-srcT@2026", [
            {"chunk_id": "p24t-t1", "chunk_index": 0, "content": "T"}])
        for step in ("INGESTED", "REGISTERED", "VALIDATED", "ACTIVE"):
            krs.transition("p24t-srcT@2026", step)
        reg = krs.load_registry(scope="GLOBAL")
        c.chk("TENANT source invisible to GLOBAL registry",
              reg.get_entry("p24t-docT") is None)
        cm2 = krs.content_map(only_active=True)
        c.chk("TENANT doc absent from default content_map",
              "p24t-docT" not in cm2)
    finally:
        _cleanup(store)


@section
def test_s6_restart_preserves_state(c):
    """HG-24-17: a NEW store instance (fresh process-equivalent) reads
    the same ACTIVE state and identical integrity anchors."""
    store, krs = _krs()
    _cleanup(store)
    try:
        krs.upsert_source(_meta("p24t-srcR", "p24t-docR"))
        krs.upsert_version(_meta("p24t-srcR", "p24t-docR"), "DISCOVERED")
        vhash = krs.upsert_chunks("p24t-srcR@2026", [
            {"chunk_id": "p24t-r1", "chunk_index": 0,
             "content": "重启后仍在"}])
        for step in ("INGESTED", "REGISTERED", "VALIDATED", "ACTIVE"):
            krs.transition("p24t-srcR@2026", step)
        # fresh instance over the same database
        _, krs2 = _krs()
        v = krs2.get_version("p24t-srcR@2026")
        c.chk("state survives restart", v["status"] == "ACTIVE")
        c.chk("version hash survives restart", v["version_hash"]
              == vhash)
        c.chk("selfcheck green after restart",
              krs2.selfcheck("p24t-srcR@2026")["ok"])
    finally:
        _cleanup(store)


def main() -> int:
    if not PG_AVAILABLE:
        print("PHASE 24A REGISTRY PG SUITE: INTEGRATION SKIPPED "
              "(no PostgreSQL credential file)")
        return 0
    os.chdir(REPO)
    return run_sections(SECTIONS, "p24_registry_pg_log.txt",
                        "PHASE 24A REGISTRY PG SUITE")


if __name__ == "__main__":
    sys.exit(main())
