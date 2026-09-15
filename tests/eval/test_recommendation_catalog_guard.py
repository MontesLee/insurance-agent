"""Fix 2 verification — defence-in-depth catalog guard on the primary recommendation product.

`catalog_has_primary_product` (runtime/resources/config/eval.rules.json) requires
``payload.primary_recommendation.product.product_id`` to exist in the demo catalog.
It is additive to the existing candidate_id -> catalog chain: it directly verifies the
embedded product_id so a recommendation can never vouch for a product that is not in
the catalog even if the candidate_id chain somehow resolved.

  * Positive: a real catalog product_id (P001)            -> PASS
  * Negative: a non-existent product_id (CATALOG_NON_EXISTENT) -> FAIL

Both assertions are checked for non-vacuousness: the positive id is provably present in
the catalog and the negative id is provably absent, so the check cannot pass by accident.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from runtime import eval_engine as ev  # noqa: E402


def _rules() -> dict:
    return ev.load_rules()


def _catalog_ids() -> set:
    return {p.get("product_id") for p in ev.load_catalog(_rules())}


def _artifact_with(product_id: str) -> dict:
    return {
        "artifact_type": "product-recommendation",
        "payload": {
            "status": "COMPLETE",
            "primary_recommendation": {
                "candidate_id": "C001",
                "product": {"product_id": product_id, "catalog_version": "0.1"},
            },
        },
    }


def _run_invariant(product_id: str) -> dict:
    rules = _rules()
    artifact = _artifact_with(product_id)
    checks = ev.check_invariant({}, artifact, "product-recommendation", rules)
    for c in checks:
        if c["check_id"] == "catalog_has_primary_product":
            return c
    raise AssertionError("catalog_has_primary_product invariant was not executed")


def test_catalog_has_primary_product_positive():
    ids = _catalog_ids()
    # non-vacuous: P001 must be a real catalog product
    assert "P001" in ids, "P001 missing from catalog — test premise broken"
    check = _run_invariant("P001")
    assert check["status"] == "PASS", check


def test_catalog_has_primary_product_negative():
    ids = _catalog_ids()
    # non-vacuous: the negative id is provably absent from the catalog
    assert "CATALOG_NON_EXISTENT" not in ids, "negative id unexpectedly present in catalog"
    check = _run_invariant("CATALOG_NON_EXISTENT")
    assert check["status"] == "FAIL", check
    assert "CATALOG_NON_EXISTENT" in check.get("message", ""), check


def test_catalog_has_primary_product_real_demo_passes():
    # No regression: the shipped demo recommendation's primary product is in the catalog.
    path = os.path.join(
        REPO, "tmp", "demo", "bm-complete-006-single-medical",
        "bm-complete-006-single-medical", "artifacts", "product-recommendation.json")
    if not os.path.exists(path):
        # The demo artifact is generated, not committed; skip gracefully if absent.
        return
    with open(path, encoding="utf-8") as f:
        artifact = json.load(f)
    rules = _rules()
    checks = ev.check_invariant({}, artifact, "product-recommendation", rules)
    target = [c for c in checks if c["check_id"] == "catalog_has_primary_product"]
    assert target, "catalog_has_primary_product not executed on real artifact"
    assert target[0]["status"] == "PASS", target[0]


if __name__ == "__main__":
    test_catalog_has_primary_product_positive()
    test_catalog_has_primary_product_negative()
    test_catalog_has_primary_product_real_demo_passes()
    print("ALL PASS")
