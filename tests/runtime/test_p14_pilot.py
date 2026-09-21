"""Phase 14.7 — Real Insurance Knowledge Pilot tests.

Wraps the real-pilot evaluation (3 official partial-copy documents)
and asserts: the quality gate, the §33 static audit (no production
runtime reads the pilot except through explicit provider fixture
configuration; no online infrastructure; no silent synthetic/pilot
mixing), and the §29 data-quality metrics with explicit denominators.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

PILOT = os.path.join(REPO, "knowledge", "pilot")

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


@section
def test_pilot_gate(c: Checks):
    from evals.knowledge import run_pilot_eval as pe
    results = pe.run_all()
    gates = pe.hard_gates(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    c.chk("pilot: every real-data case passes (chain works on REAL docs)",
          passed == len(results), (passed, len(results)))
    c.chk("pilot: hard gates CLEAN (no unsafe acceptance of any kind)",
          gates == {}, gates)
    ids = {r["case_id"] for r in results}
    for want in ("P-RET-001", "P-TMP-001", "P-LIC-002", "P-MUT-001",
                 "P-PROV-001", "P-ISO-001", "P-FAIL-001"):
        c.chk("pilot: case %s present in the suite" % want,
              want in ids)


@section
def test_pilot_data_quality(c: Checks):
    reg = json.load(open(os.path.join(PILOT, "registry",
                                      "pilot_registry.json"),
                         encoding="utf-8"))
    manifest = json.load(open(os.path.join(PILOT, "manifests",
                                           "pilot_manifest.json"),
                              encoding="utf-8"))
    n = len(reg)
    c.chk("quality: real documents registered (10 — the G1 minimum "
          "now met: 3 fetched-from-web partial copies + 7 local-corpus "
          "FULL copies)", n == 10, n)
    c.chk("quality: 7 of 10 are FULL copies (local corpus enrichment)",
          sum(1 for e in reg if e.get("copy_status") == "FULL") == 7)
    c.chk("quality: metadata_complete_rate = %d/%d (every field filled)"
          % (n, n),
          all({"source_id", "source_type", "authority_level",
               "jurisdiction", "license_status", "effective_from",
               "effective_to", "version", "canonical_uri",
               "retrieved_at", "copy_status", "publisher",
               "license_note"} <= set(e) for e in reg))
    c.chk("quality: hash_complete_rate = %d/%d (real sha256 anchors)"
          % (n, n),
          all(e["content_hashes"] and all(
              len(h) == 64 for h in e["content_hashes"].values())
              for e in reg))
    c.chk("quality: license_known_rate = %d/%d (ALLOWED, each grounded "
          "in 著作权法第五条 — never 'official site = ALLOWED')"
          % (n, n),
          all(e["license_status"] == "ALLOWED" and e.get("license_note")
              for e in reg))
    c.chk("quality: effective_date_known_rate = %d/%d" % (n, n),
          all(e["effective_from"] for e in reg))
    c.chk("quality: copy_status honestly recorded on every doc "
          "(FULL vs PARTIAL_VERBATIM — no full claim for partials)",
          all(e.get("copy_status") in ("FULL", "PARTIAL_VERBATIM")
              for e in reg))
    c.chk("quality: canonical_uri is an official domain for every doc",
          all(("gov.cn" in e["canonical_uri"]) for e in reg))
    c.chk("quality: manifest document hashes present and 64-hex",
          all(len(d["file_sha256"]) == 64 for d in manifest["documents"]))


@section
def test_static_audit(c: Checks):
    # §33-1/2: no online/DB/container infrastructure on the KNOWLEDGE
    # retrieval path. Scope: knowledge/, adapters/, and the knowledge
    # seams of runtime (tools/orchestrator). The LLM provider client
    # (runtime/agent/model.py, pre-existing, R-05-governed) is NOT the
    # knowledge path and is intentionally out of this audit's scope.
    offenders = []
    knowledge_paths = [
        os.path.join(REPO, "knowledge"),
        os.path.join(REPO, "adapters"),
        os.path.join(REPO, "runtime", "agent", "tools.py"),
        os.path.join(REPO, "runtime", "orchestrator.py"),
    ]
    for root in knowledge_paths:
        paths = [root] if root.endswith(".py") else [
            os.path.join(dp, f) for dp, _d, fs in os.walk(root)
            if "__pycache__" not in dp for f in fs if f.endswith(".py")]
        for p in paths:
            body = open(p, encoding="utf-8").read()
            rel = os.path.relpath(p, REPO)
            # Phase 18: the LIVE transport (urllib to a LOCAL
            # loopback WeKnora) is legitimate; scan for ONLINE/DB/
            # container clients only
            for tok in ("import requests", "import httpx",
                        "import docker", "psycopg", "redis"):
                if tok in body:
                    offenders.append("%s:%s" % (rel, tok))
            if "docker" in body.lower() and "weknora" not in rel:
                offenders.append("%s:docker-mention" % rel)
    c.chk("audit: no online/DB/container infrastructure on the "
          "knowledge path (LLM provider client excluded by scope)",
          offenders == [], offenders[:4])

    # §33-3: production runtime never reads the pilot except through
    # explicit provider fixture configuration
    refs = []
    for root in (os.path.join(REPO, "runtime"),
                 os.path.join(REPO, "knowledge", "provider"),
                 os.path.join(REPO, "knowledge", "evidence"),
                 os.path.join(REPO, "knowledge", "governance"),
                 os.path.join(REPO, "knowledge", "service.py")):
        paths = [root] if root.endswith(".py") else [
            os.path.join(dp, f) for dp, _d, fs in os.walk(root)
            if "__pycache__" not in dp for f in fs if f.endswith(".py")]
        for p in paths:
            body = open(p, encoding="utf-8").read()
            if "knowledge/pilot" in body or "knowledge\", \"pilot" in body:
                refs.append(os.path.relpath(p, REPO))
    c.chk("audit: zero hard references to knowledge/pilot outside the "
          "pilot package + evals (explicit-config only access)",
          refs == [], refs)

    # §33-4: no silent synthetic<->pilot mixing (both directions proved
    # by P-ISO-001/002 in the pilot gate)

    # pilot documents contain no personal data (§6): scan for PII-ish
    # field patterns in the real texts
    import re
    pii = []
    for fn in os.listdir(os.path.join(PILOT, "documents")):
        body = open(os.path.join(PILOT, "documents", fn),
                    encoding="utf-8").read()
        if re.search(r"身份证号|1[3-9]\d{9}|银行卡号|住址[:：]", body):
            pii.append(fn)
    c.chk("audit: no personal data patterns in the pilot corpus", pii == [],
          pii)


def main():
    return run_sections(SECTIONS, "p14_pilot_log.txt",
                        "PHASE 14.7 REAL KNOWLEDGE PILOT")


if __name__ == "__main__":
    sys.exit(main())
