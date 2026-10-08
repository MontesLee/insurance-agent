"""AnswerContext construction + validation (Phase 28.C-1 / ruling D1;
shared home since 28.C-2: runtime/grounding/).

The AnswerContext is a RUNTIME-SCOPED RECORD, not an artifact: it is
schema-validated against schema/qa-answer-context.schema.json (closed,
draft-07), returned to the caller, persisted under the run dir for audit,
and summarized (metadata only) into the qa_answered event. It is NEVER
registered in the artifact registry and never enters the contracts/
artifact enum.

Every builder here returns a schema-VALID document or degrades to the
internal_error refusal — an invalid record must never leave this module.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
SCHEMA_PATH = os.path.join(REPO_ROOT, "schema",
                           "qa-answer-context.schema.json")
INTENT_SCHEMA_PATH = os.path.join(REPO_ROOT, "schema",
                                  "intent-result.schema.json")

_validator = None
_intent_validator = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validator():
    global _validator
    if _validator is None:
        from jsonschema import Draft7Validator
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            _validator = Draft7Validator(json.load(fh))
    return _validator


def validate(doc: dict) -> list:
    """Schema errors of an AnswerContext document (empty = valid)."""
    return [e.message for e in validator().iter_errors(doc)]


def validate_intent(intent_result: dict) -> list:
    """Schema errors of an IntentResult input (schema/intent-result)."""
    global _intent_validator
    if _intent_validator is None:
        from jsonschema import Draft7Validator
        with open(INTENT_SCHEMA_PATH, encoding="utf-8") as fh:
            _intent_validator = Draft7Validator(json.load(fh))
    return [e.message for e in _intent_validator.iter_errors(intent_result)]


def anchor(item: dict) -> dict:
    """Citation anchor subset of a governed evidence item (metadata only —
    chunk CONTENT is deliberately not duplicated into the record)."""
    return {
        "evidence_id": item.get("evidence_id", ""),
        "chunk_id": item.get("chunk_id", ""),
        "document_id": item.get("document_id", ""),
        "document_name": item.get("document_name", ""),
        "source_id": item.get("source_id", ""),
        "source_name": item.get("source_name", ""),
        "version_id": item.get("version_id", ""),
        "version": item.get("version", ""),
        "effective_from": item.get("effective_from"),
        "effective_to": item.get("effective_to"),
        "authority_level": item.get("authority_level", ""),
        "content_hash": item.get("content_hash", ""),
    }


_V1_INTENTS = ("insurance_qa", "product_qa", "insurance_plan",
               "modify_existing_plan", "unknown_insurance_intent")


def _intent_ref(intent_result: dict) -> dict:
    """Sanitized echo of the turn's input intent: values outside the
    frozen v1 vocabulary degrade to unknown_insurance_intent (the raw
    bogus input is already reported by failure_reason=invalid_input)."""
    raw_id = intent_result.get("intent_id")
    conf = intent_result.get("confidence", 0.0)
    src = intent_result.get("confidence_source", "rule")
    created = intent_result.get("created_at")
    return {
        "intent_id": raw_id if raw_id in _V1_INTENTS
        else "unknown_insurance_intent",
        "confidence": conf if isinstance(conf, (int, float))
        and not isinstance(conf, bool) and 0.0 <= conf <= 1.0 else 0.0,
        "confidence_source": src if src in ("rule", "llm", "hybrid")
        else "rule",
        "created_at": created if isinstance(created, str) else None,
    }


def _retrieval(query, top_k, provider, governed_status, allowed, denied,
               conflict, domain=None) -> dict:
    return {
        "query": query,
        "domain": domain,
        "top_k": int(top_k),
        "provider": provider,
        "governed_status": governed_status,
        "allowed_count": int(allowed),
        "denied_count": int(denied),
        "conflict": bool(conflict),
    }


def _no_generation() -> dict:
    return {"provider": "(not-attempted)", "model": "",
            "prompt_version": "", "gateway": False, "attempts": 0}


def grounded(answer: str, cited: list, evidence_map: dict,
             intent_result: dict, retrieval: dict,
             generation: dict, status: str = "grounded",
             product_ref: Optional[dict] = None) -> dict:
    doc = {
        "answer": answer,
        "evidence_refs": list(cited),
        "grounding_status": status,
        "failure_reason": None,
        "evidence_map": evidence_map,
        "intent_ref": _intent_ref(intent_result),
        "retrieval": retrieval,
        "generated_at": _now_iso(),
        "generation_provenance": generation,
    }
    if product_ref is not None:
        doc["product_ref"] = product_ref
    errs = validate(doc)
    if errs:        # programming error — degrade, never emit invalid
        return refused("internal_error", intent_result, retrieval,
                       generation)
    return doc


def refused(reason: str, intent_result: dict, retrieval: dict,
            generation: Optional[dict] = None,
            answer: Optional[str] = None,
            violations: Optional[list] = None,
            product_ref: Optional[dict] = None) -> dict:
    """Uniform honest-refusal record. answer defaults to the externalized
    template for the reason; generation defaults to not-attempted."""
    from runtime.grounding.gate import load_rules
    templates = (load_rules().get("templates") or {})
    gen = dict(generation or _no_generation())
    if violations:
        gen["gate_violations"] = list(violations)[:10]
    doc = {
        "answer": answer or templates.get(reason) or templates.get(
            "internal_error", "暂时无法回答。"),
        "evidence_refs": [],
        "grounding_status": "refused",
        "failure_reason": reason,
        "evidence_map": {},
        "intent_ref": _intent_ref(intent_result),
        "retrieval": retrieval or _retrieval("", 0, "", "not_attempted",
                                             0, 0, False),
        "generated_at": _now_iso(),
        "generation_provenance": gen,
    }
    if product_ref is not None:
        doc["product_ref"] = product_ref
    # a refusal's answer is template text produced by code — citations in
    # it are not evidence claims; evidence_refs stays empty by contract
    return doc


def retrieval(query, top_k, provider, governed_status, allowed, denied,
             conflict, domain=None) -> dict:
    """Public wrapper for the retrieval block (shared by both grounded
    agents; was module-private _retrieval in 28.C-1)."""
    return _retrieval(query, top_k, provider, governed_status, allowed,
                      denied, conflict, domain)


def not_attempted_retrieval() -> dict:
    return _retrieval("", 0, "", "not_attempted", 0, 0, False)
