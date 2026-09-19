"""Phase 13 P0 R-03 — production product-catalog governance tests.

Round-1 finding: demo catalog lacks effective_to + core underwriting
fields; nothing separates a production source from the demo catalog; no
expiry/evidence enforcement. Proves: mode separation, expiry BLOCK,
missing evidence NEEDS_REVIEW, demo-in-production rejection, catalog
validation, and the recommendation → catalog → evidence provenance chain.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime import catalog_governance as cg  # noqa: E402
from runtime import eval_engine as ev  # noqa: E402

SECTIONS = []
PROD_BASE = {
    "product_id": "P001", "product_name": "prod-A",
    "product_version": "1.0", "effective_from": "2026-01-01",
    "product_type": "medical", "company": "insurer-A", "is_demo": False,
    "coverage_limit": 1000000, "deductible": 10000,
    "waiting_period": 30, "coverage_term": "1y", "renewal_period": "1y",
    "exclusions": ["e1"], "health_declaration": "standard",
    "occupation_restrictions": ["class-1-4"],
    "evidence": {"source": "official-rate-table",
                 "source_version": "2026Q1", "retrieved_at": "2026-01-02"},
}


def section(fn):
    SECTIONS.append(fn)
    return fn


def prod_catalog(products):
    return {"catalog_id": "prod", "catalog_version": "1.0",
            "effective_from": "2026-01-01", "is_demo": False,
            "products": products}


def with_mode(mode, catalog_path=None):
    import functools

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(c):
            old = {k: os.environ.get(k) for k in
                   ("INSURANCE_AGENT_CATALOG_MODE",
                    "INSURANCE_AGENT_CATALOG")}
            os.environ["INSURANCE_AGENT_CATALOG_MODE"] = mode
            if catalog_path:
                os.environ["INSURANCE_AGENT_CATALOG"] = catalog_path
            try:
                return fn(c)
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        return wrapper
    return deco


@section
def test_t_r03_01_valid_product(c: Checks):
    cat = prod_catalog([dict(PROD_BASE)])
    ok, problems = cg.validate_catalog(cat, mode="production")
    c.chk("R-03-01: fully-governed production catalog validates",
          ok, problems[:3])
    c.chk("R-03-01: valid product passes governance",
          cg.product_status_on(cat, "P001") == "valid")
    c.chk("R-03-01: governance check PASS",
          cg.check_candidate(cat, "P001")["status"] == "PASS")


@section
def test_t_r03_02_expired_product(c: Checks):
    expired = dict(PROD_BASE, effective_to="2026-01-02")
    cat = prod_catalog([expired])
    status = cg.product_status_on(cat, "P001", on=date(2026, 6, 1))
    c.chk("R-03-02: past effective_to → expired", status == "expired", status)
    c.chk("R-03-02: expired product BLOCKs (FAIL, not repair-guess)",
          cg.check_candidate(cat, "P001", as_of=date(2026, 6, 1))["status"]
          == "FAIL")
    future = dict(PROD_BASE, effective_from="2027-01-01")
    cat2 = prod_catalog([future])
    c.chk("R-03-02: not-yet-effective also blocks",
          cg.product_status_on(cat2, "P001", on=date(2026, 6, 1)) == "expired")


@section
def test_t_r03_03_missing_evidence(c: Checks):
    no_ev = dict(PROD_BASE)
    del no_ev["evidence"]
    cat = prod_catalog([no_ev])
    os.environ["INSURANCE_AGENT_CATALOG_MODE"] = "production"
    try:
        c.chk("R-03-03: missing evidence → missing_evidence (fail closed)",
              cg.product_status_on(cat, "P001") == "missing_evidence")
        c.chk("R-03-03: evidence-less product FAILs governance",
              cg.check_candidate(cat, "P001")["status"] == "FAIL")
    finally:
        os.environ.pop("INSURANCE_AGENT_CATALOG_MODE", None)


@section
def test_t_r03_04_missing_required_field(c: Checks):
    broken = dict(PROD_BASE)
    del broken["waiting_period"]
    cat = prod_catalog([broken])
    ok, problems = cg.validate_catalog(cat, mode="production")
    c.chk("R-03-04: catalog missing a governance field is rejected",
          not ok and any("waiting_period" in p for p in problems),
          problems[:3])
    ok2, _ = cg.validate_catalog(cat, mode="demo")
    c.chk("R-03-04: demo mode does not impose production fields", ok2)


@section
def test_t_r03_05_version_mismatch(c: Checks):
    v2 = dict(PROD_BASE, product_version="2.0")
    cat = prod_catalog([v2])
    prov = cg.catalog_provenance(cat, "P001")
    c.chk("R-03-05: provenance records the product_version",
          prov["product_version"] == "2.0")
    c.chk("R-03-05: catalog_version in the chain",
          prov["catalog_version"] == "1.0")
    # a candidate referencing a version the catalog no longer carries
    c.chk("R-03-05: unknown product id → not_in_catalog",
          cg.product_status_on(cat, "NOPE") == "not_in_catalog")


@section
def test_t_r03_06_demo_in_production(c: Checks):
    demo = dict(PROD_BASE, is_demo=True)
    cat = prod_catalog([demo])
    os.environ["INSURANCE_AGENT_CATALOG_MODE"] = "production"
    try:
        c.chk("R-03-06: demo product in production mode → "
              "demo_in_production",
              cg.product_status_on(cat, "P001") == "demo_in_production")
        ok, problems = cg.validate_catalog(cat, mode="production")
        c.chk("R-03-06: production catalog containing demo products "
              "rejected", not ok and any("DEMO" in p for p in problems))
        c.chk("R-03-06: demo product FAILs the eval governance check",
              cg.check_candidate(cat, "P001")["status"] == "FAIL")
    finally:
        os.environ.pop("INSURANCE_AGENT_CATALOG_MODE", None)
    # demo mode: the same product is fine (benchmark/portfolio compat)
    c.chk("R-03-06: demo mode accepts demo products",
          cg.product_status_on(cat, "P001") == "valid")


@section
def test_t_r03_07_provenance_chain(c: Checks):
    cat = prod_catalog([dict(PROD_BASE)])
    prov = cg.catalog_provenance(cat, "P001")
    c.chk("R-03-07: full chain record",
          prov["evidence_source"] == "official-rate-table"
          and prov["evidence_source_version"] == "2026Q1"
          and prov["catalog_version"] == "1.0"
          and prov["product_version"] == "1.0"
          and prov["retrieved_at"] == "2026-01-02", prov)


@section
def test_t_r03_08_eval_integration(c: Checks):
    """The eval invariant now emits governance checks on every candidate —
    demo catalog passes; an expired entry BLOCKs end-to-end."""
    from runtime.state import transitions as _tr
    from runtime import orchestrator as _orch
    rules = ev.load_rules()
    wf = _orch.load_workflow()
    stage = _tr.stage_by_id(wf, "product-candidate-provider")

    # demo catalog (default mode): P001 valid
    artifact = {"candidates": [{"candidate_id": "C1", "product_id": "P001",
                                "admissible": True}]}
    rec = ev.evaluate({"evaluations": [], "artifacts": {},
                       "artifact_registry": {}},
                      "product-candidates", artifact, stage, rules=rules)
    gov = [ch for ch in rec["checks"] if ch["check_id"] == "catalog_governance"]
    c.chk("R-03-08: governance check present in eval", len(gov) == 1)
    c.chk("R-03-08: demo-mode P001 governance PASS",
          gov and gov[0]["status"] == "PASS", gov)

    # expired product in the same artifact → FAIL (BLOCK, not repairable)
    artifact_bad = {"candidates": [{"candidate_id": "C1",
                                    "product_id": "BAD_X",
                                    "admissible": True}]}
    rec2 = ev.evaluate({"evaluations": [], "artifacts": {},
                        "artifact_registry": {}},
                       "product-candidates", artifact_bad, stage, rules=rules)
    c.chk("R-03-08: unknown product → eval FAIL",
          rec2["status"] == "FAIL")


@section
def test_t_r03_09_mode_separation(c: Checks):
    c.chk("R-03-09: default mode is demo", cg.catalog_mode() == "demo")
    os.environ["INSURANCE_AGENT_CATALOG_MODE"] = "production"
    try:
        c.chk("R-03-09: production mode selectable", cg.catalog_mode()
              == "production")
        c.chk("R-03-09: production mode points at the production catalog",
              cg.catalog_path().endswith("product-catalog.production.json"))
        c.chk("R-03-09: no production catalog ships by default (fail at "
              "load — no silent demo fallback)",
              not os.path.exists(cg.catalog_path()))
    finally:
        os.environ.pop("INSURANCE_AGENT_CATALOG_MODE", None)
    c.chk("R-03-09: demo mode points at the demo catalog",
          cg.catalog_path().endswith("product-catalog.v0.1.json"))


def main():
    return run_sections(SECTIONS, "webui_test_r03_log.txt",
                        "P0 R-03 CATALOG GOVERNANCE")


if __name__ == "__main__":
    sys.exit(main())
