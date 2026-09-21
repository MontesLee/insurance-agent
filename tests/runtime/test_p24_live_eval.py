"""Phase 24E — LIVE knowledge evaluation (env-gated integration).

Runs ONLY when BOTH live systems are configured:
  * PostgreSQL registry (credential file, as test_p22_pg)
  * WeKnora  INSURANCE_AGENT_WEKNORA_URL / _API_KEY /
    _KNOWLEDGE_BASE_ID (the fixtures KB)
    (+ optional _JWT for the crafted DENY-case corpus uploads;
      INSURANCE_AGENT_WEKNORA_PILOT_KB for the pilot KB sections)
Otherwise: explicit INTEGRATION SKIPPED — never PASS silently.

Proves, against the REAL systems (Phase 24 spec §36–§51):
  * the full production knowledge chain Question → WeKnora search →
    KnowledgeHit → PostgreSQL registry → governance → evidence →
    provenance (§39), including the F-24 canonical re-anchoring on the
    78-chunk pilot regulation (raw search window → canonical chunk →
    registry hash → ALLOW; the same hit DENIES without re-anchoring)
  * dual-mode agreement: mock vs live on the same queries (§36)
  * governance DENY on real retrieval over crafted registrations:
    expired / future / license-unknown / authority-conflict /
    jurisdiction-conflict / unregistered / hash-mutation /
    chunk-mutation / registry-mutation (§37/§40)
  * provider fail-closed at the HTTP boundary (§25) and health-as-
    reachability-only (§27)
  * metrics (§38) + latency N>=20 with percentiles (§51) — written to
    tmp/p24_live_eval_report.json
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

PG_PASSWORD = ""
try:
    PG_PASSWORD = open(
        r"C:\Users\aubor\AppData\Local\Temp\pg_cred.txt"
    ).read().strip().split("=", 1)[1]
except (FileNotFoundError, IndexError):
    pass

URL = os.environ.get("INSURANCE_AGENT_WEKNORA_URL", "").strip()
KEY = os.environ.get("INSURANCE_AGENT_WEKNORA_API_KEY", "").strip()
KB = os.environ.get("INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID",
                    "").strip()
PILOT_KB = os.environ.get("INSURANCE_AGENT_WEKNORA_PILOT_KB", "").strip()
JWT = os.environ.get("INSURANCE_AGENT_WEKNORA_JWT", "").strip()
LIVE = bool(PG_PASSWORD and URL and KEY and KB)

SECTIONS = []
METRICS = {"cases": [], "latency_ms": [], "governance": {"allow": 0,
                                                         "deny": 0}}


def section(fn):
    SECTIONS.append(fn)
    return fn


def _krs():
    from runtime.state.pg import PostgresStore
    from knowledge.governance.pg_registry import KnowledgeRegistryStore
    store = PostgresStore()
    krs = KnowledgeRegistryStore(store.connect)
    krs.init_schema()
    return store, krs


def _live_service(kb_id=None, with_content_map=True, registry=None,
                  krs=None):
    """KnowledgeService over the PG registry + real WeKnora (the
    production composition; stamps project from the same registry)."""
    from knowledge.provider.weknora import (WeKnoraLiveProvider,
                                            WeKnoraLiveTransport)
    from knowledge.service import KnowledgeService
    if registry is None or krs is None:
        registry, krs = _pg_registry()
    cm = krs.content_map(only_active=True) if with_content_map else None
    return KnowledgeService(
        provider=WeKnoraLiveProvider(
            transport=WeKnoraLiveTransport(URL, KEY),
            kb_id=kb_id or KB,
            stamps=registry.provider_stamps(),
            content_map=cm),
        registry=registry,
        now_fn=lambda: "2026-09-21T00:00:00Z"), registry, krs


def _pg_registry():
    from knowledge.service import pg_registry
    return pg_registry()


def _cleanup_pg(prefix="p24l-"):
    store, krs = _krs()
    with store.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM knowledge_chunks WHERE version_id "
                        "LIKE %s", (prefix + "%",))
            cur.execute("DELETE FROM knowledge_versions WHERE "
                        "version_id LIKE %s", (prefix + "%",))
            cur.execute("DELETE FROM knowledge_sources WHERE source_id "
                        "LIKE %s", (prefix + "%",))
    return store, krs


# --------------------------------------------------------------------- #
@section
def test_s1_full_chain_and_f24(c):
    if not LIVE:
        return
    """§39 full lineage on the real pilot corpus + the F-24 proof:
    the same multi-chunk hit is DENIED without canonical re-anchoring
    and ALLOWED with it."""
    if not PILOT_KB:
        return
    from knowledge.governance.provenance import validate_provenance
    query = "互联网保险业务监管要求"
    t0 = time.perf_counter()
    svc, reg, krs = _live_service(kb_id=PILOT_KB)
    items, governed, decisions, ctx = svc.build_evidence(
        query, top_k=5, as_of="2026-09-21")
    dt = (time.perf_counter() - t0) * 1000
    METRICS["latency_ms"].append(dt)
    c.chk("pilot chain returned evidence", len(items) >= 1,
          governed.status)
    c.chk("evidence carries full citation tuple",
          all(i.get("version_id", "").startswith("cn-") for i in items),
          [i.get("version_id") for i in items])
    c.chk("evidence has source identity fields",
          all(i.get("source_id") and i.get("authority_level")
              and i.get("jurisdiction") and i.get("license_status")
              for i in items))
    c.chk("evidence retrieved_at stamped",
          all(i.get("retrieved_at") for i in items))
    # provenance P-chain over the LIVE evidence items
    prov_ok = 0
    for i in items:
        try:
            ok, reasons = validate_provenance(i, reg)
            if ok and not reasons:
                prov_ok += 1
        except Exception:  # noqa: BLE001
            pass
    c.chk("provenance valid for every live evidence item",
          prov_ok == len(items) and prov_ok >= 1,
          "%d/%d" % (prov_ok, len(items)))
    METRICS["governance"]["allow"] += len(items)
    # F-24: WITHOUT the content map the multi-chunk doc shows the
    # symptom (span windows deny on HASH_MISMATCH — single-chunk-
    # aligned hits still match directly); WITH it the symptom is gone
    # and the doc is allowed
    svc2, _, _ = _live_service(kb_id=PILOT_KB, with_content_map=False,
                               registry=reg, krs=krs)
    _, gov2, decisions2, _ = svc2.build_evidence(query, top_k=5,
                                                 as_of="2026-09-21")
    multi2 = [d for d in decisions2 if d["document_id"]
              == "pilot_reg_internet_ins_2020"]
    mm2 = sum(1 for d in multi2
              if any(r.startswith("HASH_MISMATCH") for r in d["reasons"]))
    mm1 = sum(1 for d in decisions
              if d["document_id"] == "pilot_reg_internet_ins_2020"
              and any(r.startswith("HASH_MISMATCH") for r in d["reasons"]))
    c.chk("F-24: without re-anchoring HASH_MISMATCH symptoms appear",
          multi2 and mm2 >= 1, mm2)
    METRICS["governance"]["deny"] += mm2
    c.chk("F-24: with re-anchoring the symptom is resolved (mm1 < mm2 "
          "or none left) and the doc is allowed",
          (mm1 < mm2 or mm1 == 0)
          and sum(1 for d in decisions if d["document_id"]
                  == "pilot_reg_internet_ins_2020" and d["allowed"])
          >= 1, "with=%d without=%d" % (mm1, mm2))


@section
def test_s2_dual_mode_agreement(c):
    if not LIVE:
        return
    """§36: mock vs live must agree at the DECISION level on the same
    fixtures-corpus queries (status + any-allowed), not on scores."""
    from knowledge.service import KnowledgeService
    queries = ["重疾险保额如何确定", "意外险保障范围", "医疗险免赔额",
               "量子色动力学的规范群结构"]      # last one must abstain
    mock_svc = KnowledgeService()          # default mock composition
    live_svc, _, _ = _live_service()
    agree = abstain_ok = 0
    for q in queries:
        m_items, m_gov, _, _ = mock_svc.build_evidence(q, top_k=3)
        l_items, l_gov, _, _ = live_svc.build_evidence(q, top_k=3)
        same_status = (m_gov.status == l_gov.status)
        same_allowed = (bool(m_items) == bool(l_items))
        if same_status and same_allowed:
            agree += 1
        METRICS["cases"].append({"query": q, "mode": "mock",
                                 "status": m_gov.status,
                                 "allowed": len(m_items)})
        METRICS["cases"].append({"query": q, "mode": "live",
                                 "status": l_gov.status,
                                 "allowed": len(l_items)})
        METRICS["governance"]["allow"] += len(l_items)
    c.chk("mock/live agreement >= 3/4", agree >= 3, "%d/4" % agree)
    # abstention correctness: nonsense query never yields evidence
    _, a_gov, _, _ = live_svc.build_evidence(queries[-1], top_k=3)
    c.chk("agent-side abstention on nonsense query",
          a_gov.status == "insufficient_evidence")
    METRICS["governance"]["deny"] += max(
        0, a_gov.retrieval_metadata.get("governance", {})
        .get("rejected", 0))


@section
def test_s3_governance_deny_cases(c):
    if not LIVE:
        return
    """§37/§40: crafted-but-REAL registrations on live retrieval:
    expired, future, license-unknown, authority-conflict, jurisdiction-
    conflict, unregistered, hash/chunk/registry mutation."""
    if not JWT:
        return
    store, krs = _cleanup_pg()
    # Upload one crafted doc into the FIXTURES KB (in the retrieve
    # key's scope; parses reliably — documents in a KB WITHOUT an
    # embedding model stall in "processing" forever, observed live).
    # The doc is DELETED again in the finally block so every other
    # suite sees the unchanged 6-document fixtures corpus.
    from knowledge.pilot.sync_weknora_registry import (
        _req, upload_if_absent, wait_parsed)
    doc_path = os.path.join(REPO, "tmp", "p24_live_case_doc.md")
    os.makedirs(os.path.dirname(doc_path), exist_ok=True)
    # unique content (a near-copy of a known-good parser input with a
    # distinctive title and clauses) so it RANKS for the case query and
    # is distinguishable from the original fixture document
    src = os.path.join(REPO, ".trae", "skills", "knowledge-search",
                       "evals", "fixtures", "kb", "03_accident_insurance.md")
    with open(src, encoding="utf-8-sig") as f:
        body = f.read()
    body = body.replace("# 意外险", "# 意外伤害特别保障条款（测试）") \
        if body.startswith("# 意外险") else body
    body += ("\n\n## 特别测试条款\n\n本特别测试条款用于治理用例验证："
             "意外伤害保险保障范围包含特别测试情形。意外伤害保险"
             "保障范围测试条款第二条：特别测试情形属于保障范围。\n")
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(body)
    smoke_kb = KB
    kid, _ = upload_if_absent(smoke_kb, doc_path)
    status = wait_parsed(smoke_kb, kid)
    c.chk("case doc parsed", status == "completed", status)
    doc_id = "p24_live_case_doc"

    def register(krs_, over):
        meta = {
            "source_id": "p24l-case", "document_id": doc_id,
            "source_name": "P24 Live Case", "source_type": "regulation",
            "authority_level": "A", "jurisdiction": "CN",
            "version": "2026", "effective_from": "2026-01-01",
            "effective_to": None, "license_status": "ALLOWED",
            "content_hashes": {},
        }
        meta.update(over)
        vid = "p24l-case@%s" % meta["version"]
        krs_.upsert_source(meta)
        krs_.upsert_version(meta, "DISCOVERED")
        from knowledge.pilot.sync_weknora_registry import fetch_chunks
        raw = fetch_chunks(kid)
        ordered = sorted(raw, key=lambda x: x.get("chunk_index") or 0)
        chunks = [{"chunk_id": x["id"], "chunk_index": i,
                   "content": x.get("content") or ""}
                  for i, x in enumerate(ordered) if x.get("id")]
        krs_.transition(vid, "INGESTED")
        krs_.upsert_chunks(vid, chunks)
        krs_.transition(vid, "REGISTERED")
        krs_.transition(vid, "VALIDATED")
        krs_.transition(vid, "ACTIVE")
        return vid, chunks

    def live_decisions(kb, registry, krs_):
        svc, _, _ = _live_service(kb_id=kb, registry=registry,
                                  krs=krs_)
        _, decisions, _ = svc.search("意外伤害特别保障条款 特别测试情形",
                                     top_k=5, as_of="2026-09-21")
        return [d for d in decisions if d["document_id"] == doc_id]

    try:
        # baseline: valid registration → the crafted doc is allowed
        _, krs = _cleanup_pg()
        vid, chunks = register(krs, {})
        reg, krs2 = _pg_registry()
        ds = live_decisions(smoke_kb, reg, krs2)
        c.chk("crafted baseline allowed", any(d["allowed"] for d in ds),
              [d["reasons"] for d in ds])
        METRICS["governance"]["allow"] += sum(1 for d in ds
                                              if d["allowed"])

        # case matrix: mutate the REGISTRATION (fresh registration per
        # case — retrieval is identical, only governance data changes)
        cases = [
            ("expired", {"effective_from": "2020-01-01",
                         "effective_to": "2021-01-01"},
             "WINDOW_EXPIRED"),
            ("future", {"effective_from": "2027-01-01"}, "WINDOW_FUTURE"),
            ("license-unknown", {"license_status": "UNKNOWN"},
             "LICENSE_UNKNOWN"),
            ("jurisdiction-conflict", {"jurisdiction": "CN-31"},
             "JURISDICTION_MISMATCH"),
        ]
        for name, over, expect in cases:
            _, krs = _cleanup_pg()
            register(krs, over)
            reg, krs2 = _pg_registry()
            ds = live_decisions(smoke_kb, reg, krs2)
            c.chk("case %s denied" % name,
                  ds and all(not d["allowed"] for d in ds),
                  [d["reasons"] for d in ds])
            if expect:
                c.chk("case %s reason %s" % (name, expect),
                      any(expect in r for d in ds
                          for r in d["reasons"]),
                      [d["reasons"] for d in ds])
            METRICS["governance"]["deny"] += len(ds)

        # authority conflict: a REAL retrieved hit whose CLAIMED
        # authority disagrees with the registry (backend-side
        # tampering) must deny (HG-24-05)
        from knowledge.governance.governance import validate_hit
        from knowledge.governance.model import QueryContext
        reg, krs2 = _pg_registry()
        svc, _, _ = _live_service(kb_id=smoke_kb, registry=reg,
                                  krs=krs2)
        raw = svc.provider.search("意外伤害特别保障条款 特别测试情形",
                                  top_k=5)
        target = next((h for h in raw.results
                       if h.document_id == doc_id), None)
        c.chk("authority-conflict: real hit retrieved",
              target is not None)
        if target is not None:
            tampered = copy.deepcopy(target)
            tampered.source_level = "S"      # claim ≠ registry "A"
            d = validate_hit(tampered,
                             QueryContext(as_of="2026-09-21"), reg)
            c.chk("authority-conflict denied",
                  not d.allowed
                  and any(r.startswith("AUTHORITY_CONFLICT")
                          for r in d.reasons), d.reasons)
            METRICS["governance"]["deny"] += 1

        # unregistered: delete the registration → REGISTRY_MISS
        _cleanup_pg()
        reg, krs2 = _pg_registry()
        ds = live_decisions(smoke_kb, reg, krs2)
        c.chk("unregistered denied (REGISTRY_MISS)",
              ds and all(not d["allowed"] and
                         any(r.startswith("REGISTRY_MISS")
                             for r in d["reasons"]) for d in ds),
              [d["reasons"] for d in ds])

        # hash mutation: register valid, then tamper the chunk content
        # at rest → selfcheck detects (HG-24-28)
        _, krs = _cleanup_pg()
        vid, chunks = register(krs, {})
        with store.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE knowledge_chunks SET content=%s "
                            "WHERE version_id=%s",
                            ("篡改后的内容", vid))
        sc = krs.selfcheck(vid)
        c.chk("chunk mutation detected at rest", not sc["ok"]
              and any(p.startswith("CHUNK_TAMPERED")
                      for p in sc["problems"]), sc)
        # registry mutation: corrupt the version projection hashes
        with store.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE knowledge_chunks SET content=%s "
                            "WHERE version_id=%s",
                            (chunks[0]["content"], vid))
                cur.execute("UPDATE knowledge_versions SET "
                            "content_hashes='{\"x\":\"y\"}'::jsonb, "
                            "version_hash='deadbeef' WHERE version_id=%s",
                            (vid,))
        sc2 = krs.selfcheck(vid)
        c.chk("registry mutation detected",
              not sc2["ok"], sc2)
    finally:
        _cleanup_pg()
        try:
            from knowledge.pilot.sync_weknora_registry import _req
            _req("DELETE", "/api/v1/knowledge/%s" % kid, auth=JWT)
        except Exception:  # noqa: BLE001 — best-effort corpus restore
            pass


@section
def test_s4_provider_failclosed_and_health(c):
    if not LIVE:
        return
    """§25/§27: every failure mode raises a ProviderError (never a
    fallback); health is reachability only."""
    from knowledge.provider.weknora import (WeKnoraLiveProvider,
                                            WeKnoraLiveTransport)
    from knowledge.provider.base import (ProviderResponseInvalid,
                                         ProviderUnavailable)
    ok = WeKnoraLiveTransport(URL, KEY)
    c.chk("health reachable", ok.health() is True)
    bad = WeKnoraLiveTransport(URL, "not-a-real-key")
    # health is REACHABILITY: a 401 answer still proves the service is
    # up (it does NOT validate credentials — that is the search path's
    # fail-closed job)
    c.chk("health bad key still reachable (401 answered)",
          bad.health() is True)
    dead = WeKnoraLiveTransport("http://127.0.0.1:9", KEY,
                                timeout=2)
    c.chk("health unreachable False", dead.health() is False)
    for label, transport in [
            ("connection refused", dead),
            ("wrong endpoint",
             # a base URL whose search path does not exist: the service
             # is up, the endpoint is wrong — must fail closed, not
             # silently succeed against something else
             WeKnoraLiveTransport(URL + "/api/v1", KEY)),
            ("401 unauthorized", bad)]:
        p = WeKnoraLiveProvider(transport=transport, kb_id=KB)
        try:
            p.search("测试查询")
            c.chk("%s fails closed" % label, False, "no exception")
        except (ProviderUnavailable, ProviderResponseInvalid):
            c.chk("%s fails closed" % label, True)
        except Exception as e:  # noqa: BLE001
            c.chk("%s fails closed" % label, False,
                  "%s: %s" % (type(e).__name__, str(e)[:80]))
        _ = (ProviderUnavailable, ProviderResponseInvalid)


@section
def test_s5_latency_and_metrics(c):
    if not LIVE:
        return
    """§51: N>=20 live retrievals through the FULL knowledge path with
    retrieval/governance/evidence latency percentiles; §38 metrics."""
    if not PILOT_KB:
        return
    svc, _, _ = _live_service(kb_id=PILOT_KB)
    queries = [
        "互联网保险业务监管", "保险销售行为规范", "医保基金使用",
        "保险公司信息披露", "反保险欺诈", "消费者权益保护",
        "健康保险管理办法", "医疗机构管理", "药店监督管理",
        "农业保险条例", "交通事故责任强制保险", "再保险业务",
    ] * 2                                   # 24 live retrievals
    total, gov_ms = [], []
    complete = total_items = 0
    for q in queries:
        t0 = time.perf_counter()
        items, governed, decisions, _ = svc.build_evidence(
            q, top_k=3, as_of="2026-09-21")
        total.append((time.perf_counter() - t0) * 1000)
        t1 = time.perf_counter()
        svc.search(q, top_k=3, as_of="2026-09-21")
        gov_ms.append((time.perf_counter() - t1) * 1000)
        METRICS["governance"]["allow"] += len(items)
        METRICS["governance"]["deny"] += len(decisions) - len(items)
        METRICS["cases"].append({"query": q, "mode": "live",
                                 "status": governed.status,
                                 "allowed": len(items)})
        for i in items:
            total_items += 1
            if all(i.get(k) for k in ("source_id", "version_id",
                                      "authority_level", "jurisdiction",
                                      "license_status", "content_hash",
                                      "retrieved_at")):
                complete += 1
    c.chk("N>=20 live retrievals", len(total) >= 20, len(total))

    def pct(xs, p):
        xs = sorted(xs)
        k = max(0, min(len(xs) - 1, int(round(p / 100 *
                     (len(xs) - 1)))))
        return xs[k]

    lat = {
        "n": len(total),
        "min": round(min(total), 1), "median": round(statistics
                                                     .median(total), 1),
        "p95": round(pct(total, 95), 1), "max": round(max(total), 1),
        "governance_only_median_ms": round(statistics.median(gov_ms), 1),
    }
    METRICS["latency"] = lat
    METRICS["evidence_completeness"] = round(
        complete / total_items, 3) if total_items else None
    METRICS["provenance_completeness"] = "verified per-item in s1"
    METRICS["production_scale_sla"] = "NOT_MEASURABLE (single host, " \
                                      "no production load)"
    c.chk("latency report has percentiles",
          all(k in lat for k in ("min", "median", "p95", "max")))
    os.makedirs(os.path.join(REPO, "tmp"), exist_ok=True)
    with open(os.path.join(REPO, "tmp", "p24_live_eval_report.json"),
              "w", encoding="utf-8") as f:
        json.dump(METRICS, f, ensure_ascii=False, indent=1)
    c.chk("metrics report written", True)


def main() -> int:
    if not LIVE:
        print("PHASE 24E LIVE EVAL: INTEGRATION SKIPPED "
              "(no PostgreSQL credential and/or WeKnora env)")
        return 0
    os.environ["AGENT_PG_PASSWORD"] = PG_PASSWORD
    os.chdir(REPO)
    return run_sections(SECTIONS, "p24_live_eval_log.txt",
                        "PHASE 24E LIVE KNOWLEDGE EVALUATION")


if __name__ == "__main__":
    sys.exit(main())
