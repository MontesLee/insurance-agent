"""Product resolution + deterministic catalog evidence (Phase 28.C-2).

Resolution (via runtime/catalog_refs — longest match, message-first then
context) and the version-pinned CATALOG RECORD anchor: the E1 evidence
every resolved product turn carries. Catalog facts are relayed by the
LLM verbatim (formatting only) — the record IS the fact source
(ADR-022: Catalog = deterministic product facts, version-pinned).
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
RULES_PATH = os.path.join(REPO_ROOT, "config", "product-qa-rules.yaml")

_rules_cache = None
_catalog_version_cache = None


def load_rules(path: Optional[str] = None, refresh: bool = False) -> dict:
    global _rules_cache
    if _rules_cache is not None and not refresh and path is None:
        return _rules_cache
    import yaml  # noqa: WPS433 — lazy, house style
    with open(path or RULES_PATH, encoding="utf-8") as fh:
        rules = yaml.safe_load(fh)
    if not isinstance(rules, dict) or rules.get("version") != 1:
        raise ValueError("%s: version must be 1" % (path or RULES_PATH))
    if not isinstance((rules.get("catalog") or {}).get("rendered_fields"),
                      list):
        raise ValueError("%s: catalog.rendered_fields missing" % (path or RULES_PATH))
    if path is None:
        _rules_cache = rules
    return rules


def catalog_version() -> str:
    global _catalog_version_cache
    if _catalog_version_cache is None:
        try:
            from runtime.catalog_governance import load_catalog
            doc = load_catalog()
            _catalog_version_cache = str(
                doc.get("catalog_version", "") if isinstance(doc, dict)
                else "")
        except Exception:  # noqa: BLE001 — unreadable = unversioned
            _catalog_version_cache = ""
    return _catalog_version_cache


def _render_value(v) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return str(v)


def catalog_record(product: dict, rules: Optional[dict] = None) -> dict:
    """The deterministic version-pinned catalog evidence entry:
    {"content": rendered-record text, "header": display header,
    "anchor": citation anchor}. Only PRESENT fields render — absence
    stays honest (the record shows what the catalog HAS)."""
    r = rules or load_rules()
    pid = str(product.get("product_id", ""))
    lines = []
    for f in r["catalog"]["rendered_fields"]:
        v = product.get(f)
        if v is None or v == "" or v == []:
            continue
        lines.append("%s: %s" % (f, _render_value(v)))
    text = "\n".join(lines)
    ver = str(product.get("product_version", ""))
    return {
        "content": text,
        "header": "CATALOG RECORD (deterministic, version-pinned) "
                  "product: %s | catalog_version: %s" % (
                      product.get("product_name", ""), catalog_version()),
        "anchor": {
            "evidence_id": "catalog:%s" % pid,
            "chunk_id": "catalog-record",
            "document_id": pid,
            "document_name": str(product.get("product_name", "")),
            "source_id": "catalog:%s@%s" % (catalog_version(), ver),
            "source_name": str(product.get("company", "")),
            "version_id": "catalog:%s@%s" % (catalog_version(), ver),
            "version": ver,
            "effective_from": product.get("effective_from"),
            "effective_to": product.get("effective_to"),
            "authority_level": "catalog",
            "content_hash": hashlib.sha256(
                text.encode("utf-8")).hexdigest(),
            "source_type": "catalog",
        },
    }


def qualifies(item: dict, product: dict) -> bool:
    """Does a governed WeKnora evidence item belong to THIS product's
    scope? Deterministic: the item's document is linked in the product's
    evidence_refs, or the item content names the product (full/base name
    or id). Generic category knowledge that neither is linked nor names
    the product does NOT qualify (no substitution for a specific
    product's facts)."""
    doc_stem = str(item.get("document_id", ""))
    refs = [str(x).rsplit(".", 1)[0] for x in (product.get("evidence_refs")
                                               or [])]
    if doc_stem and doc_stem in refs:
        return True
    pid = str(product.get("product_id", ""))
    name = str(product.get("product_name", ""))
    base = name.split("（")[0].split("(")[0].strip()
    content = str(item.get("content", ""))
    return any(s and s in content for s in (pid, name, base))
