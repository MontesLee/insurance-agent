"""Attribute-level evidence grounding (Step 4 · Phase 7) — the "V0.2" upgrade.

Step 2 left the evidence chain at:

    Product --> required evidence DOMAIN --> Evidence Available

which is too coarse: a medical product is treated as "backed by evidence" merely because
some medical document was retrieved, even if that document says nothing about the product's
actual terms. This module tightens it to:

    Product Attribute --> Evidence Requirement --> Evidence Chunk --> SUPPORTED / UNSUPPORTED / CONFLICT

Scope is deliberately bounded (spec §19): only a small set of material product attributes
is grounded (`renewal_period`, `coverage_type`, `eligibility_age`, `deductible`,
`coverage_term`). Anything outside that set is NOT_CHECKABLE.

Two design rules matter here:

  * NOT_CHECKABLE is an independent THIRD state. It is never folded into SUPPORTED —
    "we could not check it" must not read as "we checked and it is fine". It also must
    not, by itself, block a product: only a positive UNSUPPORTED (the evidence exists and
    does not say this) downgrades.
  * The matcher is deterministic and rules-driven; every term/synonym lives in the
    externalized rules file, never in code.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RULES = os.path.join(HERE, "resources", "config", "attribute-grounding.rules.json")

_RULES_CACHE: Optional[dict] = None


def load_rules(path: Optional[str] = None) -> dict:
    global _RULES_CACHE
    if path is None and _RULES_CACHE is not None:
        return _RULES_CACHE
    with open(path or DEFAULT_RULES, encoding="utf-8") as f:
        rules = json.load(f)
    if path is None:
        _RULES_CACHE = rules
    return rules


# --------------------------------------------------------------------------- #
# claim extraction
# --------------------------------------------------------------------------- #
def _claim_value(product: dict, spec: dict) -> Any:
    """The value the product DECLARES for this attribute (None when it declares nothing)."""
    src = spec.get("claim") or {}
    origin = src.get("from")
    if origin == "product":
        cur: Any = product
        for part in (src.get("path") or "").split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur
    if origin == "constraint":
        name = src.get("name")
        for c in (product.get("constraints") or []):
            if isinstance(c, dict) and c.get("constraint") == name:
                return c.get("value")
    return None


def _norm(s: str, rules: dict) -> str:
    """Normalise a string for matching. Whitespace is stripped so that the catalog's
    `10000元` and the knowledge base's `1 万元` can be compared at all."""
    s = str(s).lower()
    if (rules.get("term_expansion") or {}).get("strip_whitespace", True):
        s = "".join(s.split())
    return s


def _amount_variants(text: str, rules: dict) -> list:
    """`10000元` -> also `1万元` / `1万` / `10000`. Rules-driven; no magic numbers."""
    exp = rules.get("term_expansion") or {}
    if not exp.get("amount_variants"):
        return []
    step = int(exp.get("ten_thousand") or 10000)
    units = exp.get("amount_units") or ["元", "万元"]
    out: list = []
    raw = _norm(text, rules)
    for unit in units:
        if raw.endswith(_norm(unit, rules)):
            digits = raw[: -len(_norm(unit, rules))]
            try:
                num = float(digits)
            except ValueError:
                return []
            if num.is_integer():
                out.append(str(int(num)))
            if unit == units[0] and num and num % step == 0:
                wan = int(num // step)
                out.extend(["%d万" % wan, "%d万元" % wan])
            return out
    return out


def _terms_for(spec: dict, value: Any, rules: dict) -> list:
    """Expand the rules file's templates + synonyms into lowercase search terms."""
    terms: list = []
    templates = spec.get("evidence_terms") or []
    if isinstance(value, dict):
        mn, mx = value.get("min"), value.get("max")
        for tpl in templates:
            if not any(t in tpl for t in ("{min}", "{max}", "{range}")):
                continue
            t = (tpl.replace("{min}", "" if mn is None else str(mn))
                    .replace("{max}", "" if mx is None else str(mx))
                    .replace("{range}", "%s-%s" % (mn, mx)))
            terms.append(t)
    else:
        text = str(value)
        for tpl in templates:
            if "{value}" in tpl:
                terms.append(tpl.replace("{value}", text))
        for syn in (spec.get("synonyms") or {}).get(text) or []:
            terms.append(syn)
        terms.extend(_amount_variants(text, rules))
    seen, out = set(), []
    for t in terms:
        n = _norm(t, rules)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


# --------------------------------------------------------------------------- #
# grounding
# --------------------------------------------------------------------------- #
def ground_product_attributes(product: dict, evidence_items: list,
                              rules: Optional[dict] = None) -> dict:
    """Ground each configured attribute of `product` against `evidence_items`.

    Returns {"rollup": ..., "attributes": {attr_id: {status, value, matched|terms, reason}}}.
    """
    rules = rules or load_rules()
    statuses = rules.get("statuses") or {}
    S_OK = statuses.get("supported", "SUPPORTED")
    S_UNSUP = statuses.get("unsupported", "UNSUPPORTED")
    S_CONFLICT = statuses.get("conflict", "CONFLICT")
    S_NC = statuses.get("not_checkable", "NOT_CHECKABLE")

    texts = []
    for it in evidence_items or []:
        if isinstance(it, dict):
            texts.append(str(it.get("content") or ""))
    blob = _norm("\n".join(texts), rules)
    conflict_flag = any(bool(it.get("conflict")) for it in (evidence_items or [])
                        if isinstance(it, dict))
    min_chars = int(rules.get("min_evidence_chars") or 1)
    have_evidence = len(blob.strip()) >= min_chars

    per: dict = {}
    for spec in rules.get("attributes") or []:
        aid = spec.get("id")
        if not aid:
            continue
        value = _claim_value(product, spec)
        if value in (None, "", [], {}):
            per[aid] = {"status": S_NC, "value": None,
                        "reason": "product declares no value for this attribute"}
            continue
        if not have_evidence:
            per[aid] = {"status": S_NC, "value": value,
                        "reason": "no evidence text available for this product"}
            continue
        terms = _terms_for(spec, value, rules)
        if not terms:
            per[aid] = {"status": S_NC, "value": value,
                        "reason": "no matchable term configured for this value"}
            continue
        hit = next((t for t in terms if t in blob), None)
        if hit is None:
            per[aid] = {"status": S_UNSUP, "value": value, "terms": terms[:6],
                        "reason": "no evidence chunk mentions this attribute value"}
        elif conflict_flag:
            per[aid] = {"status": S_CONFLICT, "value": value, "matched": hit,
                        "reason": "evidence chunk is flagged as conflicting"}
        else:
            per[aid] = {"status": S_OK, "value": value, "matched": hit}
        per[aid]["required"] = bool(spec.get("required"))

    return {"rollup": _rollup(per, rules), "attributes": per}


def _rollup(per: dict, rules: dict) -> str:
    """Worst-relevant verdict over the REQUIRED attributes.

    NOT_CHECKABLE is stricter than SUPPORTED but must not block a product on its own, so
    it only wins once nothing is positively UNSUPPORTED or CONFLICTing.
    """
    st = rules.get("statuses") or {}
    S_OK = st.get("supported", "SUPPORTED")
    S_UNSUP = st.get("unsupported", "UNSUPPORTED")
    S_CONFLICT = st.get("conflict", "CONFLICT")
    S_NC = st.get("not_checkable", "NOT_CHECKABLE")

    required = [v for v in per.values() if v.get("required")]
    scope = required if required else list(per.values())
    if not scope:
        return S_NC
    verdicts = [v.get("status") for v in scope]
    if S_UNSUP in verdicts:
        return S_UNSUP
    if S_CONFLICT in verdicts:
        return S_CONFLICT
    if any(v not in (S_OK,) for v in verdicts):
        # nothing was positively contradicted, but we could not confirm every required
        # attribute -> the honest answer is "cannot fully check", never "supported".
        return S_NC
    return S_OK


def summarize(grounding: dict) -> str:
    """One-line human summary for traces / reports (never a decision)."""
    if not grounding:
        return "no attribute grounding"
    roll = grounding.get("rollup")
    per = grounding.get("attributes") or {}
    buckets: dict = {}
    for aid, v in per.items():
        buckets.setdefault(v.get("status"), []).append(aid)
    parts = ", ".join("%s=%s" % (k, "/".join(sorted(v))) for k, v in sorted(buckets.items()))
    return "rollup=%s [%s]" % (roll, parts)
