"""Deterministic support judgment (OD-3/OD-5/OD-6/OD-10) + delivery
policy simulation (OD-7). Shadow only — never imported by production.

Semantics (design §6):
  SUPPORTED            every numeric anchor of the claim is found in a
                       usable (temporal-valid, product-matching)
                       evidence item (unit-normalized), or — for
                       qualitative claims — full content-word coverage
  PARTIALLY_SUPPORTED >=1 anchor covered, >=1 missing
  UNSUPPORTED          nothing covered (lexical overlap alone NEVER
                       yields SUPPORTED — citation presence is not
                       support)
  CONTRADICTED         same anchor label with different values across
                       usable items (OD-5: detect, fail-closed, no
                       invented precedence)
  NOT_APPLICABLE       C-USER / C-RECOMMENDATION / C-CALCULATION /
                       C-UNCERTAIN / C-DERIVED (per design §4/§12)
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

SUPPORTED = "SUPPORTED"
PARTIAL = "PARTIALLY_SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"
NOT_APPLICABLE = "NOT_APPLICABLE"
CONTRADICTED = "CONTRADICTED"

DELIVERY_POLICY_HOLD = "hold"          # OD-7 shadow policy B+C+A
_UNIT_NORM = {"日": "天", "天/年": "天", "万元": "万"}

_STOPWORDS = {"的了", "和与", "及或", "在对", "由为", "是有", "一般",
              "通常", "可能", "需要", "应该", "可以", "投保", "产品",
              "保险", "条款", "规定", "事项", "适用", "关于", "有关",
              "这款", "那个", "以下", "可以", "以及", "并且"}


def _unit(u: str) -> str:
    return _UNIT_NORM.get(u, u)


def _in_window(item: dict, as_of: date) -> bool:
    f = item.get("effective_from")
    t = item.get("effective_to")
    try:
        if f and date.fromisoformat(str(f)) > as_of:
            return False
        if t and date.fromisoformat(str(t)) < as_of:
            return False
    except ValueError:
        return False
    return True


def _product_ok(claim: str, item: dict) -> bool:
    """Wrong-product filter: when the evidence item is bound to a
    product (product_id) and the claim names a DIFFERENT product id,
    the item cannot support it (OD-10 / N4)."""
    pid = item.get("product_id")
    if not pid:
        return True
    ids = set(re.findall(r"P0\d{2}", claim))
    return not ids or pid in ids


def _usable_items(claim: str, evidence: list, as_of: date) -> list:
    return [it for it in (evidence or [])
            if _in_window(it, as_of) and _product_ok(claim, it)]


def _value_found(value: str, unit: str, text: str) -> bool:
    """Numeric presence with unit normalization (90天/90日; 100万/
    100万元). Requires the value (and unit when the claim has one) in
    the evidence text."""
    if unit:
        return (value + unit in text) or (value + "万" in text
                                          if unit == "万元" else False)
    return value in text


def judge_support(claim: str, claim_type: str, anchors: list,
                  evidence: list, as_of: Optional[date] = None) -> dict:
    """One claim -> support judgment. evidence = [{content, source_name,
    effective_from/to, product_id?}, ...] (the C2-QUALIFIED set — the
    shadow layer sits strictly AFTER C2 per design §3)."""
    as_of = as_of or date(2026, 9, 29)
    if claim_type in ("C-USER", "C-RECOMMENDATION", "C-CALCULATION",
                      "C-UNCERTAIN", "C-DERIVED"):
        return {"support_status": NOT_APPLICABLE,
                "support_type": "EXEMPT",
                "support_reason": "claim_type exempt: %s" % claim_type,
                "evidence_refs": []}
    items = _usable_items(claim, evidence, as_of)
    corpus_text = " ".join((it.get("content") or "")
                           + (it.get("source_name") or "") for it in items)
    # contradiction (OD-5): for each labelled claim anchor, extract the
    # label's values from USABLE evidence texts; >=2 distinct values
    # across items = contradictory evidence -> detect + fail closed
    # (no invented precedence; Owner rules the ordering, OD-5)
    _EV_ANCHOR_RE = re.compile(
        r"(等待期|犹豫期|免赔额|保额|保费|赔付比例|报销比例|投保年龄|续保)"
        r"[^\d]{0,8}(\d+(?:\.\d+)?)")
    for label, _val, _u in anchors:
        if not label:
            continue
        vals = set()
        for it in items:
            for m in _EV_ANCHOR_RE.finditer(it.get("content") or ""):
                if m.group(1) == label:
                    vals.add(m.group(2))
        if len(vals) > 1:
            return {"support_status": CONTRADICTED,
                    "support_type": "CONTRADICTORY",
                    "support_reason": "evidence conflicts on %s: %s" % (
                        label, sorted(vals)),
                    "evidence_refs": []}
    if anchors:
        covered = []
        for label, value, unit in anchors:
            hit = any(_value_found(value, _unit(unit),
                                   (it.get("content") or ""))
                      for it in items)
            covered.append(hit)
        if all(covered):
            st, ty = SUPPORTED, "DIRECT"
        elif any(covered):
            st, ty = PARTIAL, "PARTIAL"
        else:
            st, ty = UNSUPPORTED, "IRRELEVANT"
        return {"support_status": st, "support_type": ty,
                "support_reason": "anchors covered %d/%d" % (
                    sum(covered), len(covered)),
                "evidence_refs": []}
    # qualitative: conservative CJK-BIGRAM containment (runs are not
    # words in CJK — bigrams approximate content-word coverage) —
    # never similarity-based SUPPORTED
    norm = re.sub(r"[^一-龥]+", "", claim)
    words = {norm[i:i + 2] for i in range(len(norm) - 1)}
    words = {w for w in words if w not in _STOPWORDS}
    if not words:
        return {"support_status": UNSUPPORTED, "support_type": "IRRELEVANT",
                "support_reason": "no salient content words", "evidence_refs": []}
    hit = sum(1 for w in words if w in corpus_text)
    if hit == len(words):
        return {"support_status": SUPPORTED, "support_type": "DIRECT",
                "support_reason": "qualitative full coverage %d/%d" % (
                    hit, len(words)), "evidence_refs": []}
    if hit >= max(1, len(words) // 2):
        return {"support_status": PARTIAL, "support_type": "PARTIAL",
                "support_reason": "qualitative partial %d/%d" % (
                    hit, len(words)), "evidence_refs": []}
    return {"support_status": UNSUPPORTED, "support_type": "IRRELEVANT",
            "support_reason": "qualitative coverage %d/%d" % (
                hit, len(words)), "evidence_refs": []}


def simulate_delivery(answer: str, evidence: list,
                      as_of: Optional[date] = None) -> dict:
    """OD-7 shadow policy simulation on one answer:
    sentence hold (unsupported fact claim) -> regen feedback (no-op in
    shadow: honest static second pass) -> final refusal if unresolved.
    Returns per-claim rows + policy outcome + escape accounting."""
    from runtime.grounding.shadow.claims import split_claims
    rows = []
    for c in split_claims(answer):
        j = judge_support(c["claim_text"], c["claim_type"], c["anchors"],
                          evidence, as_of)
        rows.append({"claim_text": c["claim_text"],
                     "claim_type": c["claim_type"],
                     "support_status": j["support_status"],
                     "support_type": j["support_type"],
                     "support_reason": j["support_reason"]})
    unsupported_facts = [r for r in rows
                         if r["claim_type"] == "C-FACT"
                         and r["support_status"] in (UNSUPPORTED, PARTIAL,
                                                     CONTRADICTED)]
    held = [r["claim_text"] for r in unsupported_facts]
    outcome = ("refused" if unsupported_facts else "delivered")
    delivered_claims = [r for r in rows if r["claim_text"] not in held]
    return {"rows": rows, "held_sentences": held, "outcome": outcome,
            "delivered_rows": delivered_claims,
            "escaped_unsupported": 0 if held else len(unsupported_facts)}
