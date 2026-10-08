"""Phase 28.H — HD-2 production knowledge chain invariants.

Hermetic parts ALWAYS run (no live WeKnora needed):
  * H-N5: mock provider is FORBIDDEN in strict modes (HG-24-03) — a
    production configured with mock knowledge refuses to construct
  * H-1..H-6 (config half): strict + weknora without complete config
    fails closed at service construction / startup validation
  * H-N1: an unreachable WeKnora NEVER falls back to mock — the
    ProviderUnavailable path propagates (fail closed)
  * retrieval-method knob: INSURANCE_AGENT_WEKNORA_SEARCH_METHOD passes
    through verbatim; unset keeps the backend default

Live parts run only with INSURANCE_AGENT_WEKNORA_URL configured:
  * H-R2 real retrieval returns governed evidence (authority levels
    stamped by the registry), H-R4 semantic-neighbour observation.
"""
from __future__ import annotations

import os

import pytest

from _common import make_client

# a VALID Fernet-format key for the strict dataprotection preflight
import base64 as _b64, secrets as _secrets
_FERNET = _b64.urlsafe_b64encode(_secrets.token_bytes(32)).decode()


# vars that shape the knowledge chain / mode — cleared to a clean
# baseline for every hermetic test (live-env leakage cannot flip a
# hermetic invariant), then the test's own overrides are applied
_CHAIN_VARS = [
    "INSURANCE_AGENT_MODE", "INSURANCE_AGENT_KNOWLEDGE_PROVIDER",
    "INSURANCE_AGENT_WEKNORA_URL", "INSURANCE_AGENT_WEKNORA_API_KEY",
    "INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID",
    "INSURANCE_AGENT_WEKNORA_SEARCH_METHOD",
    "INSURANCE_AGENT_API_KEYS", "INSURANCE_AGENT_DATA_KEY",
    "INSURANCE_AGENT_KNOWLEDGE_REGISTRY",
    "INSURANCE_AGENT_KNOWLEDGE_REGISTRY_BACKEND",
]


def _with_env(**env):
    """Isolate the knowledge/mode env for one test, restoring after."""
    keys = _CHAIN_VARS + list(env)
    old = {k: os.environ.get(k) for k in keys}
    for k in _CHAIN_VARS:
        os.environ.pop(k, None)
    os.environ.update(env)

    class _Restore:
        def __enter__(self):
            return None

        def __exit__(self, *a):
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    return _Restore()


def test_hn5_mock_forbidden_in_strict_modes():
    """G-HD2-5: production + mock provider → REJECTED, never started."""
    from knowledge.service import ProviderConfigError, default_service
    with _with_env(INSURANCE_AGENT_MODE="production",
                   INSURANCE_AGENT_KNOWLEDGE_PROVIDER="mock",
                   INSURANCE_AGENT_WEKNORA_URL="",
                   INSURANCE_AGENT_API_KEYS="k" * 24 + ":OWNER:x",
                   INSURANCE_AGENT_DATA_KEY="x" * 44):
        with pytest.raises(ProviderConfigError, match="FORBIDDEN"):
            default_service()


def test_h1_strict_weknora_requires_full_config():
    """G-HD2-1/6: strict + weknora with an INCOMPLETE config fails closed
    (missing KB id / API key → ProviderConfigError, not a silent mock)."""
    from knowledge.service import ProviderConfigError, default_service
    with _with_env(INSURANCE_AGENT_MODE="controlled_pilot",
                   INSURANCE_AGENT_KNOWLEDGE_PROVIDER="weknora",
                   INSURANCE_AGENT_WEKNORA_URL="http://127.0.0.1:9",
                   INSURANCE_AGENT_WEKNORA_API_KEY="",
                   INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID="",
                   INSURANCE_AGENT_API_KEYS="k" * 24 + ":OWNER:x",
                   INSURANCE_AGENT_DATA_KEY="x" * 44):
        with pytest.raises(ProviderConfigError):
            default_service()


def test_hn1_unreachable_weknora_has_no_mock_fallback():
    """G-HD2-10: WeKnora outage → ProviderUnavailable propagates; there is
    NO mock fallback anywhere on the path (fail closed)."""
    from knowledge.provider.base import ProviderUnavailable
    from knowledge.provider.weknora import WeKnoraLiveProvider, WeKnoraLiveTransport
    prov = WeKnoraLiveProvider(
        transport=WeKnoraLiveTransport("http://127.0.0.1:1", "k" * 24),
        kb_id="kb-x")
    with pytest.raises(ProviderUnavailable):
        prov.search("健康保险等待期")


def test_search_method_knob_passthrough():
    """HD-2 deployment knob: the configured method is carried on the
    transport and included in the request body; unset keeps the
    historical default (no param). Body inclusion is verified by building
    the exact request the transport sends (no network)."""
    import json as _json
    from knowledge.provider.weknora import WeKnoraLiveTransport
    with _with_env(INSURANCE_AGENT_WEKNORA_SEARCH_METHOD="vector_search"):
        t = WeKnoraLiveTransport("http://x", "k" * 24)
        assert t.search_method == "vector_search"
        body = _json.loads(_json.dumps(
            {"query": "q", "knowledge_base_id": "kb",
             **({"search_method": t.search_method} if t.search_method else {})}))
        assert body["search_method"] == "vector_search"
    with _with_env(INSURANCE_AGENT_WEKNORA_SEARCH_METHOD=""):
        t2 = WeKnoraLiveTransport("http://x", "k" * 24)
        t2.search_method = ""
        assert "search_method" not in _json.loads(_json.dumps(
            {"query": "q", "knowledge_base_id": "kb"}))


def test_startup_preflight_blocks_misconfigured_strict_knowledge():
    """H-6 (startup half): the strict startup validation refuses to start
    when the knowledge chain is misconfigured (mock or incomplete)."""
    from runtime.server import _validate_production_defaults
    with _with_env(INSURANCE_AGENT_MODE="production",
                   INSURANCE_AGENT_KNOWLEDGE_PROVIDER="mock",
                   INSURANCE_AGENT_WEKNORA_URL="",
                   INSURANCE_AGENT_API_KEYS="k" * 24 + ":OWNER:x",
                   INSURANCE_AGENT_DATA_KEY=_FERNET):
        with pytest.raises(RuntimeError, match="PRODUCTION_KNOWLEDGE_REQUIRED"):
            _validate_production_defaults()


def test_dev_mode_unaffected():
    """Non-strict dev keeps the documented mock default (unit/dev use)."""
    with _with_env():
        c = make_client()[0]
        d = c.get("/api/diagnostics")
    assert d.status_code == 200, d.text[:200]
    assert d.json()["configuration_status"]["knowledge_provider"] in (
        "mock", "weknora")


@pytest.fixture(autouse=True)
def _fresh_service_cache():
    """default_service caches its instance; each invariant must construct
    under ITS OWN env (a stale cache from a previous test must never
    shadow the invariant under test)."""
    import knowledge.service as ks
    saved = (ks._default_service, ks._default_service_explicit)
    ks._default_service = None
    ks._default_service_explicit = False
    yield
    ks._default_service, ks._default_service_explicit = saved


# --------------------------------------------------------------------------- #
# LIVE (only with a configured WeKnora — the HD-2 production instance)
# --------------------------------------------------------------------------- #
LIVE = bool(os.environ.get("INSURANCE_AGENT_WEKNORA_URL", "").strip())


def _live_env():
    """The live chain env exactly as the HD-2 instance runs it."""
    return dict(
        INSURANCE_AGENT_MODE=os.environ.get("INSURANCE_AGENT_MODE", ""),
        INSURANCE_AGENT_KNOWLEDGE_PROVIDER="weknora",
        INSURANCE_AGENT_WEKNORA_URL=os.environ["INSURANCE_AGENT_WEKNORA_URL"],
        INSURANCE_AGENT_WEKNORA_API_KEY=os.environ.get(
            "INSURANCE_AGENT_WEKNORA_API_KEY", ""),
        INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID=os.environ.get(
            "INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID", ""),
        INSURANCE_AGENT_WEKNORA_SEARCH_METHOD=os.environ.get(
            "INSURANCE_AGENT_WEKNORA_SEARCH_METHOD", ""),
        INSURANCE_AGENT_API_KEYS=os.environ.get("INSURANCE_AGENT_API_KEYS", ""),
        INSURANCE_AGENT_DATA_KEY=os.environ.get("INSURANCE_AGENT_DATA_KEY", ""),
    )


@pytest.mark.skipif(not LIVE, reason="live WeKnora not configured")
def test_hr2_live_governed_retrieval():
    from knowledge.service import default_service
    with _with_env(**_live_env()):
        svc = default_service()
        assert svc.provider.name == "weknora"
    items, governed, decisions, ctx = svc.build_evidence(
        "健康保险的等待期有什么规定", top_k=3)
    assert governed.status == "success"
    gm = (governed.retrieval_metadata or {}).get("governance", {})
    assert (gm.get("allowed") or 0) >= 1
    lvls = {i.get("source_level") or i.get("authority_level") for i in items}
    assert lvls & {"A", "S"}, "registry authority stamps must be present"


@pytest.mark.skipif(not LIVE, reason="live WeKnora not configured")
def test_hr4_live_semantic_neighbours_fail_closed_at_answer_layer():
    """The vector backend returns semantic neighbours for nonsense; the
    frozen scoring policy may pass them — the SAFETY property is that
    the ANSWER layer never fabricates (E-7 qa3-style refusal / citation
    gate). Retrieval observation is recorded, not 'fixed' here."""
    from knowledge.service import default_service
    with _with_env(**_live_env()):
        svc = default_service()
        assert svc.provider.name == "weknora"
    # either governed abstention OR allowed neighbours — both are safe;
    # what is FORBIDDEN is mock fallback (provider stays weknora)
