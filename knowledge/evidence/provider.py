"""Shared Evidence Provider (Phase 4) — the "Knowledge Search" side.

Knowledge Search is a SHARED PROVIDER, not a fixed workflow step. This module is the single
seam through which any skill obtains evidence:

    Skill --(Evidence Request: KnowledgeQuery)--> provide_evidence() --> KnowledgeEvidence

Design rules:
  * It invokes the existing knowledge-search engine. It does NOT modify that skill, and it
    does NOT re-implement retrieval.
  * It never decides: it returns Evidence, never a recommendation, score-of-fit, or product.
  * It never fabricates: when the engine abstains (insufficient_evidence), the empty result
    is propagated verbatim.
  * Both the request and the response are validated against their Canonical Contracts.
"""
from __future__ import annotations

import importlib.util
import json
import os
from typing import Any, Optional

import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

KS_INVOKE = os.path.join(
    REPO_ROOT, ".trae", "skills", "knowledge-search", "scripts", "invoke-knowledge-search.py"
)
EVIDENCE_SCHEMA = os.path.join(REPO_ROOT, "contracts", "knowledge-evidence.schema.json")
QUERY_SCHEMA = os.path.join(REPO_ROOT, "contracts", "knowledge-query.schema.json")


def _load_ks_module():
    """Load the knowledge-search entry point (hyphenated filename -> importlib)."""
    spec = importlib.util.spec_from_file_location("_ks_invoke", KS_INVOKE)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load knowledge-search entry point: {KS_INVOKE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_engine(kb_dir: Optional[str] = None):
    """Legacy construction helper — NOT on the runtime evidence path
    since Phase 14.4 (F-01). Retained as the mock provider's lazy
    build seam and for test injection; runtime retrieval goes through
    knowledge.service.KnowledgeService. The constructed engine carries
    `_kb_dir` so a governed service can pair it with the right
    registry (a KB without its registry fails closed)."""
    mod = _load_ks_module()
    eng = mod.build_engine(kb_dir) if kb_dir else mod.build_engine()
    eng._kb_dir = kb_dir
    return eng


def extract_payload(artifact: Any) -> Any:
    if isinstance(artifact, dict) and isinstance(artifact.get("payload"), dict):
        return artifact["payload"]
    return artifact


def validate(artifact: dict, schema_path: str) -> tuple:
    from jsonschema import Draft7Validator

    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(artifact), key=lambda e: list(e.path))
    msgs = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
    return (len(msgs) == 0, msgs)


def provide_evidence(
    query_artifact: Any,
    top_k: Optional[int] = None,
    engine: Any = None,
    kb_dir: Optional[str] = None,
    do_validate: bool = True,
    service: Any = None,
) -> tuple:
    """Consume a canonical KnowledgeQuery and return a canonical KnowledgeEvidence.

    Phase 14.4 (F-01 closed): the evidence round goes through the
    KnowledgeService — Provider → Governance → evidence — NEVER
    directly through the deterministic engine. `engine=` survives as a
    TEST-INJECTION seam only (wrapped as a provider; its documents
    must be registry-covered or every hit fails closed);
    `kb_dir=` composes a governed service over that KB (unregistered
    documents are rejected by governance — fail-closed by design);
    `service=` is the composition-root injection point.

    Returns (evidence_artifact, ok, errors).
    """
    from adapters.knowledge_search_adapter import to_canonical
    from knowledge.service import KnowledgeService, default_service

    query = extract_payload(query_artifact) or {}
    query_text = query.get("query") or ""

    if do_validate and isinstance(query_artifact, dict) and "artifact_type" in query_artifact:
        ok, errs = validate(query_artifact, QUERY_SCHEMA)
        if not ok:
            return (None, False, ["QUERY_INVALID: " + e for e in errs])

    if service is not None:
        svc = service
    elif engine is not None:
        # TEST-INJECTION seam: wrap the (possibly dict-shaped) test
        # engine as a provider. If the engine records its KB (see
        # build_engine._kb_dir), pair it with THAT KB's registry —
        # otherwise the default registry applies and unregistered
        # documents fail governance (no ungoverned escape).
        from knowledge.provider import MockKnowledgeProvider
        from knowledge.service import wrap_test_engine, registry_for
        eng_kb = getattr(engine, "_kb_dir", None)
        reg = registry_for(eng_kb) if eng_kb else None
        svc = KnowledgeService(
            provider=MockKnowledgeProvider(
                engine=wrap_test_engine(engine),
                **({"stamps": reg.provider_stamps()} if reg else {})),
            **({"registry": reg} if reg else {}))
    elif kb_dir is not None:
        from knowledge.provider import MockKnowledgeProvider
        from knowledge.service import registry_for
        reg = registry_for(kb_dir)
        svc = KnowledgeService(
            provider=MockKnowledgeProvider(
                kb_dir=kb_dir, stamps=reg.provider_stamps()),
            registry=reg)
    else:
        svc = default_service()

    ks_output = svc.governed_output(query_text, top_k=top_k)

    artifact = to_canonical(ks_output)
    if do_validate:
        ok, errs = validate(artifact, EVIDENCE_SCHEMA)
        if not ok:
            return (artifact, False, ["EVIDENCE_INVALID: " + e for e in errs])
    return (artifact, True, [])
