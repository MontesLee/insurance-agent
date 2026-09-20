"""Stage 14.2 — WeKnora INTEGRATION test (env-gated; LIVE SERVICE ONLY).

Layer separation (§十六):
    unit      → tests/runtime/test_p14_provider.py
    contract  → tests/runtime/test_p14_weknora_poc.py (fake transport)
    integration → THIS FILE — runs ONLY against a REAL WeKnora instance.

Gate: set INSURANCE_AGENT_WEKNORA_URL (e.g. http://localhost:8080,
the backend API port documented in WeKnora's README). Optional:
  INSURANCE_AGENT_WEKNORA_API_KEY    — scoped API key (sent as Bearer)
  INSURANCE_AGENT_WEKNORA_KB_ID      — knowledge base to query
  INSURANCE_AGENT_WEKNORA_SEARCH_PATH — retrieval endpoint path

Without the URL this suite reports an explicit INTEGRATION SKIPPED and
exits 0 — it NEVER fakes a live connection. NOTE: the default search
path below is the documented ASSUMPTION from knowledge/provider/
weknora.py; the first live run must confirm/adjust it against the real
API (WeKnora documents ~360 endpoints; this file is where the raw
response contract gets pinned). The transport uses ONLY the stdlib
(urllib) — no new dependency.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

URL_ENV = "INSURANCE_AGENT_WEKNORA_URL"
KEY_ENV = "INSURANCE_AGENT_WEKNORA_API_KEY"
KB_ENV = "INSURANCE_AGENT_WEKNORA_KB_ID"
PATH_ENV = "INSURANCE_AGENT_WEKNORA_SEARCH_PATH"
DEFAULT_SEARCH_PATH = "/api/knowledge/search"   # ASSUMPTION — pin live

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def weknora_available() -> bool:
    return bool(os.environ.get(URL_ENV, "").strip())


def make_transport(url: str, api_key: str, search_path: str):
    def transport(payload: dict) -> dict:
        req = urllib.request.Request(
            url.rstrip("/") + search_path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     **({"Authorization": "Bearer " + api_key}
                        if api_key else {})},
            method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return transport


if weknora_available():
    @section
    def test_live_weknora_retrieval(c: Checks):
        """REAL integration — only reachable with a configured instance."""
        from knowledge.provider import WeKnoraKnowledgeProvider
        url = os.environ[URL_ENV].strip()
        key = os.environ.get(KEY_ENV, "").strip()
        kb = os.environ.get(KB_ENV, "").strip() or None
        path = os.environ.get(PATH_ENV, "").strip() or DEFAULT_SEARCH_PATH
        prov = WeKnoraKnowledgeProvider(
            transport=make_transport(url, key, path), kb_id=kb)
        res = prov.search("synthetic medical insurance waiting period",
                          top_k=3)
        c.chk("LIVE: canonical result returned",
              res.status in ("success", "partial_evidence",
                             "insufficient_evidence"))
        c.chk("LIVE: hits carry resolvable identifiers",
              all(h.document_id and h.chunk_id for h in res.results))
        from knowledge.evidence.provider import validate, EVIDENCE_SCHEMA
        from adapters.knowledge_search_adapter import to_canonical
        ok, errs = validate(to_canonical(res.to_dict()), EVIDENCE_SCHEMA)
        c.chk("LIVE: canonical artifact schema-valid downstream",
              ok, errs[:3])
        c.chk("LIVE: retrieval-only surface (no ask/chat/react verb "
              "anywhere in the request path)",
              "ask" not in path and "chat" not in path
              and "react" not in path)
else:
    @section
    def test_integration_skipped(c: Checks):
        c.chk("INTEGRATION SKIPPED — no live WeKnora configured "
              "(%s unset); real integration NOT claimed" % URL_ENV, True)


def main():
    return run_sections(SECTIONS, "p14_weknora_integration_log.txt",
                        "STAGE 14.2 WEKNORA INTEGRATION "
                        + ("(LIVE)" if weknora_available()
                           else "(SKIPPED — NO ENDPOINT)"))


if __name__ == "__main__":
    sys.exit(main())
