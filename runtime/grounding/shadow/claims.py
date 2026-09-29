"""Claim typing + atomicity (OD-1/OD-2) — deterministic only.

Sentence-first (reuses the production sentence splitter
runtime/grounding/gate.py::split_sentences — same separators as the
K.26 segmenter), plus deterministic sub-clause split when a sentence
carries >= 2 heterogeneous numeric-fact anchors. NO semantic
decomposition (design §5, C-5A lesson).
"""
from __future__ import annotations

import re
from typing import List, Optional

from runtime.grounding import gate as ggate

# OD-1 six classes (canonical naming per owner baseline)
C_FACT = "C-FACT"
C_USER = "C-USER"
C_RECOMMENDATION = "C-RECOMMENDATION"
C_CALCULATION = "C-CALCULATION"
C_DERIVED = "C-DERIVED"
C_UNCERTAIN = "C-UNCERTAIN"

_USER_MARKERS = ("我", "我们", "我家", "配偶", "老公", "老婆", "孩子",
                 "娃", "儿子", "女儿", "爸妈", "爸爸", "妈妈", "老人",
                 "家庭", "本人")
_REC_MARKERS = ("建议", "推荐", "可以考虑", "优先", "应该优先", "值得考虑",
                "不妨", "最好")
_CALC_MARKERS = ("计算", "测算", "合计", "等于", "×", "*", "倍", "减去",
                 "扣除", "公式", "预算按", "缺口为")
_DERIVED_MARKERS = ("因此", "由此", "说明", "这意味着", "据此推断",
                    "从而", "进而")
_UNCERTAIN_MARKERS = ("无法确认", "无法确定", "需进一步核实", "需要核实",
                      "尚不确定", "不一定", "可能因", "视具体情况",
                      "以条款为准", "以合同约定为准")
_FACT_ANCHOR_RE = re.compile(
    r"(等待期|犹豫期|免赔额|保额|保费|赔付比例|报销比例|年龄|天数|"
    r"免赔|续保|定额|偿付)")


def _hit(text: str, markers) -> bool:
    return any(m in text for m in markers)


def classify_claim(text: str) -> str:
    """Deterministic claim typing. Order: UNCERTAIN > RECOMMENDATION >
    CALCULATION > DERIVED > USER > FACT > fallback."""
    t = (text or "").strip()
    if not t:
        return C_UNCERTAIN
    if _hit(t, _UNCERTAIN_MARKERS):
        return C_UNCERTAIN
    if _hit(t, _REC_MARKERS):
        return C_RECOMMENDATION
    if _hit(t, _CALC_MARKERS):
        return C_CALCULATION
    if _hit(t, _DERIVED_MARKERS) and _hit(t, _USER_MARKERS):
        return C_DERIVED
    # product/insurance nouns force C-FACT even with family words
    # (定期寿险适合家庭经济支柱 is a product claim, not a user fact)
    if (_FACT_ANCHOR_RE.search(t)
            or _hit(t, ("险", "保险", "重疾", "医疗", "寿险", "年金", "意外"))):
        return C_FACT
    # user-fact: self/family reference WITHOUT an external-fact anchor
    if _hit(t, _USER_MARKERS):
        return C_USER
    if _FACT_ANCHOR_RE.search(t) or _hit(t, ("保险", "险", "条款", "疾病")):
        return C_FACT
    if _hit(t, _USER_MARKERS):
        return C_USER
    return C_FACT


# numeric fact anchor: label + value(+unit)
_NUM_ANCHOR_RE = re.compile(
    r"(等待期|犹豫期|免赔额|保额|保费|赔付比例|报销比例|投保年龄|续保)"
    r"[^\d]{0,8}(\d+(?:\.\d+)?)\s*(天|日|天/年|万|万元|元|%|岁|周岁)?")
_BARE_NUM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(天|日|万|万元|元|%|岁|周岁)")

_CLAUSE_SPLIT_RE = re.compile(r"[，,、；;]|而且|并且|同时|另外|此外")


def numeric_anchors(text: str) -> list:
    """[(label|None, value_str, unit), ...] — deterministic anchors."""
    out = []
    for m in _NUM_ANCHOR_RE.finditer(text):
        out.append((m.group(1), m.group(2), m.group(3) or ""))
    covered = set()
    for m in _NUM_ANCHOR_RE.finditer(text):
        covered.add((m.start(2), m.end(2)))
    for m in _BARE_NUM_RE.finditer(text):
        if any(s <= m.start(1) < e for s, e in covered):
            continue
        out.append((None, m.group(1), m.group(2) or ""))
    return out


def split_claims(answer: str, rules: Optional[dict] = None) -> List[dict]:
    """Sentence-first atomicity. Returns claim dicts
    {claim_text, claim_type, source_span(sentence idx), anchors}."""
    sents = ggate.split_sentences(answer, rules)
    claims: List[dict] = []
    for i, s in enumerate(sents):
        # OD-2: deterministic clause split on EVERY multi-clause
        # sentence (a single verified numeric fact must not vouch for
        # an unverified qualitative tail — N3 compound finding)
        parts = [p.strip() for p in _CLAUSE_SPLIT_RE.split(s)
                 if p.strip()] or [s]
        for p in parts:
            claims.append({"claim_text": p, "claim_type": classify_claim(p),
                           "sentence_idx": i,
                           "anchors": numeric_anchors(p)})
    return claims
