"""Claim→Evidence Support — PRODUCTION deterministic layer
(28.K.28-II-IMPL / K.28-II-DESIGN §4-11; owner-authorized).

Sits STRICTLY AFTER C2 (evidence qualification — sealed, untouched)
and BESIDE the citation gate: the citation gate proves the model CITED
in-range evidence; this module proves the evidence actually SUPPORTS
each insurance-factual claim. Citation presence ≠ claim support
(RV4-A's 15×[E1] stuffing; shadow-verified escape 88.2%→0%).

Authority: DETERMINISTIC ONLY (K.28-II-SHADOW: the LLM comparator was
weaker and missed product/temporal structure classes — no LLM judge in
production, OD-11). Fail-closed: a C-FACT claim that is not fully
SUPPORTED fails the gate (PARTIAL regenerates via the existing loop,
then refuses — B+C policy, isomorphic to the K.26 held-segment).

Claim taxonomy (shadow-frozen six): C-FACT (must be supported) /
C-USER / C-RECOMMENDATION / C-CALCULATION / C-DERIVED (= planning
DERIVED) / C-UNCERTAIN (exempt; an UNCERTAIN claim must not be
upgraded to asserted fact by the model).

Rollback: rules claim_support.enabled=false, or env
CLAIM_SUPPORT_ENABLED=0 (env wins) — disabled returns {"ok": True}
and the loop is byte-identical to the pre-Phase-2 path.

Canonical naming note: the frozen shadow corpus + K.28-II-SHADOW use
C-FACT/C-USER/C-RECOMMENDATION/C-CALCULATION/C-DERIVED/C-UNCERTAIN;
K.28-II-IMPL task wording (USER/DERIVED-PLANNING) maps 1:1 onto them.
"""
from __future__ import annotations

import os
import re
from datetime import date
from typing import Optional

SUPPORTED = "SUPPORTED"
PARTIAL = "PARTIAL"
UNSUPPORTED = "UNSUPPORTED"
CONTRADICTED = "CONTRADICTED"
NOT_APPLICABLE = "NOT_APPLICABLE"

C_FACT = "C-FACT"
C_USER = "C-USER"
C_RECOMMENDATION = "C-RECOMMENDATION"
C_CALCULATION = "C-CALCULATION"
C_DERIVED = "C-DERIVED"
C_UNCERTAIN = "C-UNCERTAIN"

AS_OF = date(2026, 9, 29)   # corpus-frozen as-of (R5 governs retrieval
#                            windows; this is the support-layer bound)

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
_PRODUCT_NOUN_RE = re.compile(r"险|保险|重疾|医疗|寿险|年金|意外")
_NUM_ANCHOR_RE = re.compile(
    r"(等待期|犹豫期|免赔额|保额|保费|赔付比例|报销比例|投保年龄|续保)"
    r"[^\d]{0,8}(\d+(?:\.\d+)?)\s*(天|日|万|万元|元|%|岁|周岁)?")
_BARE_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(天|日|万|万元|元|%|岁|周岁)")
_CLAUSE_SPLIT_RE = re.compile(r"[，,、；;]|而且|并且|同时|另外|此外")
_EV_ANCHOR_RE = re.compile(
    r"(等待期|犹豫期|免赔额|保额|保费|赔付比例|报销比例|投保年龄|续保)"
    r"[^\d]{0,8}(\d+(?:\.\d+)?)")
_CITATION_RE = re.compile(r"\[E\d+\]")
_UNIT_NORM = {"日": "天", "万元": "万", "天/年": "天"}
_STOP_BIGRAMS = {"的了", "和与", "及或", "在对", "由为", "是有", "一般",
                 "通常", "可能", "需要", "应该", "可以", "投保", "产品",
                 "保险", "条款", "规定", "事项", "适用", "关于", "有关",
                 "这款", "那个", "以下", "以及", "并且"}


def enabled(rules: Optional[dict] = None) -> bool:
    """Rollback switch: env CLAIM_SUPPORT_ENABLED wins over rules."""
    env = str(os.environ.get("CLAIM_SUPPORT_ENABLED", "")).strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    if rules is None:
        from runtime.grounding import gate as ggate
        rules = ggate.load_rules()
    return bool(((rules.get("claim_support") or {}).get("enabled", True)))


def classify_claim(text: str) -> str:
    """Deterministic claim typing (order: UNCERTAIN > REC > CALC >
    DERIVED > FACT > USER)."""
    t = (text or "").strip()
    if not t:
        return C_UNCERTAIN
    if any(m in t for m in _UNCERTAIN_MARKERS):
        return C_UNCERTAIN
    if any(m in t for m in _REC_MARKERS):
        return C_RECOMMENDATION
    if any(m in t for m in _CALC_MARKERS):
        return C_CALCULATION
    if (any(m in t for m in _DERIVED_MARKERS)
            and any(m in t for m in _USER_MARKERS)):
        return C_DERIVED
    if _FACT_ANCHOR_RE.search(t) or _PRODUCT_NOUN_RE.search(t):
        return C_FACT
    if any(m in t for m in _USER_MARKERS):
        return C_USER
    return C_FACT


def numeric_anchors(text: str) -> list:
    """[(label|None, value, unit), ...] deterministic numeric anchors."""
    out, covered = [], set()
    for m in _NUM_ANCHOR_RE.finditer(text):
        out.append((m.group(1), m.group(2), m.group(3) or ""))
        covered.add((m.start(2), m.end(2)))
    for m in _BARE_NUM_RE.finditer(text):
        if any(s <= m.start(1) < e for s, e in covered):
            continue
        out.append((None, m.group(1), m.group(2) or ""))
    return out


def split_claims(answer: str, rules: Optional[dict] = None) -> list:
    """Sentence-first (gate.split_sentences — same separators as the
    K.26 segmenter) + deterministic clause split on multi-clause
    sentences. NO semantic decomposition."""
    from runtime.grounding import gate as ggate
    claims = []
    for s in ggate.split_sentences(answer, rules):
        parts = [p.strip() for p in _CLAUSE_SPLIT_RE.split(s)
                 if p.strip()] or [s]
        for p in parts:
            # citation markers are the MODEL's act, not claim content —
            # strip before typing/anchoring ([E1]'s digit must never
            # become an anchor value)
            bare = _CITATION_RE.sub("", p)
            claims.append({"claim_text": p,
                           "claim_type": classify_claim(bare),
                           "anchors": numeric_anchors(bare)})
    return claims


# ------------------------------------------------------------------ #

def _cjk_norm(text: str) -> str:
    """K.28-II-FIX1 shared normalization: strip every non-CJK char.
    BOTH the claim side and the evidence corpus side use this exact
    rule before qualitative bigram membership — a cross-punctuation
    bigram (（五）自营 -> 五自) must therefore exist on BOTH sides or
    neither. (Live defect 2026-09-29: claim-side-only normalization
    made verbatim quotes with enumeration punctuation score 27/28 ->
    PARTIAL -> false refusal. Fail-closed direction; semantics and
    thresholds unchanged.)"""
    return re.sub(r"[^一-龥]+", "", text or "")


def _items_from_evidence(evidence: list) -> list:
    """Normalize loop evidence [(label, {content, header, anchor})] (or
    corpus-style raw dicts) into support-item shape. Temporal/product
    metadata comes from the ANCHOR (gctx.anchor already carries
    document_id/version/effective window) when present."""
    out = []
    for entry in evidence or []:
        e = entry[1] if isinstance(entry, (tuple, list)) else entry
        a = e.get("anchor") or {}
        out.append({
            "content": e.get("content", ""),
            "source_name": e.get("header") or a.get("source_name", ""),
            "document_id": a.get("document_id") or e.get("document_id",
                                                         ""),
            "document_name": a.get("document_name")
            or e.get("document_name", ""),
            "version": a.get("version") or e.get("version"),
            "effective_from": a.get("effective_from")
            or e.get("effective_from"),
            "effective_to": a.get("effective_to") or e.get("effective_to"),
            "product_id": e.get("product_id"),
        })
    return out


def _in_window(item: dict, as_of: date) -> bool:
    f, t = item.get("effective_from"), item.get("effective_to")
    try:
        if f and date.fromisoformat(str(f)) > as_of:
            return False
        if t and date.fromisoformat(str(t)) < as_of:
            return False
    except ValueError:
        return False
    return True


def _claim_product(text: str):
    """Resolve the SPECIFIC product the claim refers to (name→id via the
    existing catalog matcher — FS-04 fix: product NAME similarity is
    never product identity)."""
    try:
        from runtime.catalog_refs import find_product_in
        return find_product_in(text)
    except Exception:  # noqa: BLE001 — catalog unreadable = no signal
        return None


def _product_ok(claim: str, item: dict) -> bool:
    """Deterministic product identity: when BOTH the claim and the
    evidence carry an explicit product binding they must agree. An
    evidence item bound to product A cannot support a claim on product
    B (uses the existing pr.qualifies scope rule)."""
    pid_ids = set(re.findall(r"P0\d{2}", claim))
    if pid_ids:
        return not item.get("product_id") or item["product_id"] in pid_ids
    cp = _claim_product(claim)
    if cp is None:
        return True
    product = cp.get("product") or cp
    doc = str(item.get("document_id") or "")
    if doc:
        refs = [str(x) for x in (product.get("evidence_refs") or [])]
        stems = {r.rsplit(".", 1)[0] for r in refs}
        doc_stem = doc.rsplit(".", 1)[0]
        if refs and doc not in refs and doc_stem not in stems                 and doc not in stems:
            # document is linked to OTHER products — check content naming
            pid = str(product.get("product_id", ""))
            name = str(product.get("product_name", ""))
            base = name.split("（")[0].split("(")[0].strip()
            content = item.get("content", "") or ""
            if not any(s and s in content for s in (pid, name, base)):
                return False
    return True


def _value_found(value: str, unit: str, text: str) -> bool:
    if not unit:
        return value in text
    if value + unit in text:
        return True
    return unit == "万" and (value + "万元" in text)


def _norm_unit(u: str) -> str:
    return _UNIT_NORM.get(u, u)


def judge_claim(claim_text: str, claim_type: str, anchors: list,
                 items: list, as_of: Optional[date] = None) -> dict:
    """One claim → support judgment (deterministic authority)."""
    as_of = as_of or AS_OF
    if claim_type != C_FACT:
        return {"support_status": NOT_APPLICABLE, "support_type": "EXEMPT",
                "support_reason": "exempt: %s" % claim_type,
                "violations": []}
    usable = [it for it in items
              if _in_window(it, as_of) and _product_ok(claim_text, it)]
    # numbers INSIDE a resolved product name (定期至70岁) are not
    # asserted facts — strip matched names before anchoring
    anchor_text = claim_text
    cp = _claim_product(claim_text)
    if cp:
        name = str(cp.get("product_name") or "")
        names = {name, str(cp.get("product_id") or ""),
                 name.split("（")[0].split("(")[0].strip()}
        for nm in sorted((n for n in names if n), key=len, reverse=True):
            if nm and nm in anchor_text:
                anchor_text = anchor_text.replace(nm, "")
        anchors = numeric_anchors(anchor_text) or anchors
    corpus_text = " ".join((it.get("content") or "")
                           + (it.get("source_name") or "") for it in usable)
    # CONTRADICTED (OD-5 detect + fail closed): claim anchor value
    # conflicts with the evidence's value for the same label
    for label, value, _u in anchors:
        if not label:
            continue
        vals = set()
        for it in usable:
            for m in _EV_ANCHOR_RE.finditer(it.get("content") or ""):
                if m.group(1) == label:
                    vals.add(m.group(2))
        if len(vals) > 1:
            return {"support_status": CONTRADICTED,
                    "support_type": "CONTRADICTORY",
                    "support_reason": "evidence conflicts on %s: %s" % (
                        label, sorted(vals)), "violations": [
                        "claim_support:contradicted:%s" % label]}
        if len(vals) == 1 and value not in vals:
            return {"support_status": CONTRADICTED,
                    "support_type": "CONTRADICTORY",
                    "support_reason": "claim %s=%s vs evidence %s=%s" % (
                        label, value, label, sorted(vals)[0]),
                    "violations": [
                        "claim_support:contradicted:%s" % label]}
    if anchors:
        covered = [any(_value_found(v, _norm_unit(u), it.get("content")
                                   or "") for it in usable)
                   for _l, v, u in anchors]
        if all(covered):
            st, ty = SUPPORTED, "DIRECT"
        elif any(covered):
            st, ty = PARTIAL, "PARTIAL"
        else:
            st, ty = UNSUPPORTED, "NONE"
        reason = "anchors covered %d/%d" % (sum(covered), len(covered))
    else:
        norm = _cjk_norm(claim_text)
        words = {norm[i:i + 2] for i in range(len(norm) - 1)}
        words -= _STOP_BIGRAMS
        if not words:
            return {"support_status": UNSUPPORTED, "support_type": "NONE",
                    "support_reason": "no salient content",
                    "violations": ["claim_support:unsupported"]}
        # FIX1: same normalizer on the evidence side (was raw text —
        # the asymmetric-membership false-refusal defect)
        corpus_norm = _cjk_norm(corpus_text)
        hit = sum(1 for w in words if w in corpus_norm)
        if hit == len(words):
            st, ty, reason = SUPPORTED, "DIRECT", (
                "qualitative full coverage %d/%d" % (hit, len(words)))
        elif hit >= max(1, len(words) // 2):
            st, ty, reason = PARTIAL, "PARTIAL", (
                "qualitative partial %d/%d" % (hit, len(words)))
        else:
            st, ty, reason = UNSUPPORTED, "NONE", (
                "qualitative coverage %d/%d" % (hit, len(words)))
    viol = [] if st == SUPPORTED else ["claim_support:%s" % st.lower()]
    return {"support_status": st, "support_type": ty,
            "support_reason": reason, "violations": viol}


def check(text: str, evidence: list, rules: Optional[dict] = None) -> dict:
    """GATE-shaped verdict for the loop: every C-FACT claim must be
    SUPPORTED; PARTIAL/UNSUPPORTED/CONTRADICTED fail (regenerate via
    the existing loop, then refuse — B+C policy). Disabled → ok."""
    if not enabled(rules):
        return {"ok": True, "violations": [], "claims": []}
    if rules is None or "gate" not in (rules or {}):
        from runtime.grounding import gate as ggate
        rules = ggate.load_rules()
    items = _items_from_evidence(evidence)
    rows, violations = [], []
    for c in split_claims(text, rules):
        j = judge_claim(c["claim_text"], c["claim_type"], c["anchors"],
                        items)
        rows.append({"claim_text": c["claim_text"],
                     "claim_type": c["claim_type"],
                     "support_status": j["support_status"],
                     "support_type": j["support_type"],
                     "support_reason": j["support_reason"]})
        violations.extend(j["violations"])
    return {"ok": not violations, "violations": violations[:10],
            "claims": rows}


def merge_verdict(citation_verdict: dict, support_verdict: dict) -> dict:
    """Combine the citation gate verdict with the support verdict
    (support only tightens; it never relaxes the citation gate)."""
    if support_verdict.get("ok", True):
        return citation_verdict
    out = dict(citation_verdict)
    out["ok"] = False
    out["violations"] = list(citation_verdict.get("violations", [])) + list(
        support_verdict.get("violations", []))
    return out
