"""Catalog product-reference matching (Phase 28.C-2).

Deterministic, cached, fail-quiet helper shared by:
  * runtime/intent/classifier.py — a catalog product name/id in the
    message is the STRONGEST specific-product reference (fires the
    product_qa branch; ADR-019 rule vocabulary is externalized data,
    and the versioned catalog is data);
  * runtime/product_qa_agent/    — product resolution (message first,
    then recent conversation context).

Matching rule (exact, no fuzzy): a product matches a text iff one of
its match-names appears as a SUBSTRING of the text. match-names per
product: product_id (P0xx), full product_name, and the paren-stripped
base name ("demo-百万医疗险A（标准版）" -> "demo-百万医疗险A"). Longest
match-name wins (deterministic tie-break). The catalog is read through
the GOVERNED loader (runtime/catalog_governance.load_catalog); any
failure degrades to zero references — callers fall back to their
previous behavior (fail-closed, never a guess).
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

_refs_cache = None


def _load():
    from runtime.catalog_governance import load_catalog
    doc = load_catalog()
    products = doc.get("products", doc if isinstance(doc, list) else [])
    refs = []
    for p in products:
        pid = str(p.get("product_id", ""))
        name = str(p.get("product_name", ""))
        names = []
        if pid:
            names.append(pid)
        if name:
            names.append(name)
            base = name.split("（")[0].split("(")[0].strip()
            if base and base != name:
                names.append(base)
        if names:
            refs.append({"product_id": pid, "product_name": name,
                         "match_names": sorted(names, key=len,
                                               reverse=True),
                         "product": p})
    # longest-first across products for deterministic resolution
    refs.sort(key=lambda r: len(r["match_names"][0]), reverse=True)
    return refs


def product_references(refresh: bool = False) -> list:
    global _refs_cache
    if _refs_cache is None or refresh:
        try:
            _refs_cache = _load()
        except Exception:  # noqa: BLE001 — unreadable catalog = no refs
            _refs_cache = []
    return _refs_cache


def find_product_in(text: str) -> Optional[dict]:
    """The catalog product referenced in `text` (longest match-name
    wins), or None. Returns {'product_id','product_name','matched_by',
    'product'} or None."""
    t = text or ""
    for ref in product_references():
        for i, name in enumerate(ref["match_names"]):
            if name and name in t:
                return {"product_id": ref["product_id"],
                        "product_name": ref["product_name"],
                        "matched_by": ("product_id" if i == 0 and
                                       name == ref["product_id"]
                                       else "product_name"),
                        "product": ref["product"]}
    return None


def find_product(text: str, context: Optional[list] = None,
                 context_scan: int = 8) -> Tuple[Optional[dict], Optional[dict]]:
    """Resolve the referenced product: message first, then the most
    recent context mention (demonstrative follow-ups). Returns
    (match_or_None, source_or_None) where source describes WHERE it was
    found: None | {'matched_by': 'context_product_name'|'context_product_id'}.
    """
    hit = find_product_in(text)
    if hit is not None:
        return hit, {"matched_by": hit["matched_by"]}
    for c in reversed([str(x) for x in (context or [])][-context_scan:]):
        hit = find_product_in(c)
        if hit is not None:
            return hit, {"matched_by": "context_" + hit["matched_by"]}
    return None, None
