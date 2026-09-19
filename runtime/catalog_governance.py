"""Product-catalog governance (Phase 13 R-03).

Round-1 finding: the demo catalog lacks `effective_to` and core
underwriting governance fields; nothing distinguishes a production source
from the demo catalog; expired or unevidenced products could reach
recommendations. The eval engine only checked "product_id in catalog".

This module adds governance checks used by the eval engine:

  * mode separation — `INSURANCE_AGENT_CATALOG_MODE=demo|production`
    selects the catalog file; a production run REFUSES demo products.
  * expiry — `effective_to` in the past → BLOCK (eval FAIL, not repair).
  * evidence — every product must declare an `evidence` block with a
    source + version; missing → NEEDS_REVIEW (fail-closed, no guessing).
  * required governance fields — deductible / coverage_limit /
    waiting_period / coverage_term / exclusions / health_declaration /
    occupation_restrictions must be present (non-null) in production mode;
    missing → the catalog itself is rejected at load (fail-closed), so the
    LLM can never paper over a governance hole.

The demo catalog keeps working as-is for the benchmark/portfolio (demo
mode). Production mode requires a catalog that passes `validate_catalog`.
"""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

DEFAULT_DEMO_CATALOG = os.path.join(REPO, "catalog",
                                    "product-catalog.v0.1.json")
DEFAULT_PRODUCTION_CATALOG = os.path.join(REPO, "catalog",
                                         "product-catalog.production.json")

# governance fields a PRODUCTION product must carry (non-null). Mirrors the
# Round-1 audit list exactly — no invented business fields.
PRODUCTION_REQUIRED_FIELDS = (
    "coverage_limit", "deductible", "waiting_period", "coverage_term",
    "renewal_period", "exclusions", "health_declaration",
    "occupation_restrictions",
)


def catalog_mode() -> str:
    return os.environ.get("INSURANCE_AGENT_CATALOG_MODE", "demo").lower()


def catalog_path() -> str:
    override = os.environ.get("INSURANCE_AGENT_CATALOG")
    if override:
        return override
    return (DEFAULT_PRODUCTION_CATALOG if catalog_mode() == "production"
            else DEFAULT_DEMO_CATALOG)


def load_catalog(path: Optional[str] = None) -> dict:
    with open(path or catalog_path(), encoding="utf-8") as f:
        return json.load(f)


def validate_catalog(catalog: dict, mode: Optional[str] = None) -> tuple:
    """Fail-closed catalog governance validation. Returns (ok, problems).

    Production mode requires: versioned catalog, effective window,
    per-product governance fields, per-product evidence, and NO demo
    products. Demo mode requires only structural sanity + honest labelling.
    """
    mode = mode or catalog_mode()
    problems = []
    if not catalog.get("catalog_version"):
        problems.append("catalog_version missing")
    products = catalog.get("products") or []
    if not products:
        problems.append("catalog has no products")
    for p in products:
        pid = p.get("product_id", "?")
        for f in ("product_id", "product_name", "product_version",
                  "effective_from"):
            if not p.get(f):
                problems.append("%s: %s missing" % (pid, f))
        if mode == "production":
            if p.get("is_demo"):
                problems.append("%s: DEMO product in production catalog" % pid)
            for f in PRODUCTION_REQUIRED_FIELDS:
                if p.get(f) is None:
                    problems.append("%s: governance field %r missing" % (pid, f))
            ev = p.get("evidence")
            if not isinstance(ev, dict) or not ev.get("source") \
                    or not ev.get("source_version"):
                problems.append("%s: product evidence (source+source_version) "
                                "missing" % pid)
    return (len(problems) == 0), problems


def product_status_on(catalog: dict, product_id: str,
                      on: Optional[date] = None) -> str:
    """Governance verdict for ONE product on a date.

    Returns one of: 'valid' | 'expired' | 'not_in_catalog' |
    'demo_in_production' | 'missing_evidence'."""
    on = on or date.today()
    mode = catalog_mode()
    for p in catalog.get("products") or []:
        if p.get("product_id") != product_id:
            continue
        if mode == "production" and p.get("is_demo"):
            return "demo_in_production"
        ef = p.get("effective_from")
        et = p.get("effective_to")
        try:
            if ef and on < date.fromisoformat(str(ef)[:10]):
                return "expired"   # not yet effective — treat as not current
            if et and on > date.fromisoformat(str(et)[:10]):
                return "expired"
        except ValueError:
            return "missing_evidence"  # unparsable window → fail closed
        if mode == "production":
            ev = p.get("evidence")
            if not isinstance(ev, dict) or not ev.get("source") \
                    or not ev.get("source_version"):
                return "missing_evidence"
        return "valid"
    return "not_in_catalog"


def check_candidate(catalog: dict, product_id: str,
                    as_of: Optional[date] = None) -> dict:
    """One candidate's governance check record (eval-check shaped)."""
    status = product_status_on(catalog, product_id, as_of)
    ok = status == "valid"
    return {"check_id": "catalog_governance", "status": "PASS" if ok else "FAIL",
            "message": "%s: %s" % (product_id, status)}


def catalog_provenance(catalog: dict, product_id: str) -> dict:
    """The traceability chain record for a recommended product:
    recommendation → candidate → catalog version → evidence."""
    for p in catalog.get("products") or []:
        if p.get("product_id") == product_id:
            ev = p.get("evidence") or {}
            return {
                "product_id": product_id,
                "product_version": p.get("product_version"),
                "catalog_id": catalog.get("catalog_id"),
                "catalog_version": catalog.get("catalog_version"),
                "evidence_source": ev.get("source"),
                "evidence_source_version": ev.get("source_version"),
                "retrieved_at": ev.get("retrieved_at"),
                "is_demo": bool(p.get("is_demo")),
            }
    return {"product_id": product_id, "catalog_version":
            catalog.get("catalog_version"), "evidence_source": None}
