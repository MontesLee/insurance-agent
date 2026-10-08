# -*- coding: utf-8 -*-
"""Phase16 offline D-04 refusal classifier (Task 3).

Pure function over refusal records — no LLM, no production contact.
Labels:
  SAFE_REFUSAL / UTILITY_FALSE_REFUSAL / PARTIAL_CEILING /
  WHOLE_QUESTION_GATE / R4_PERSONALIZATION / HARD_CLASS_BLOCK /
  INSUFFICIENT_EVIDENCE / CLAIM_SUPPORT_FAILURE / OTHER

A record is any dict with the observation fields we already capture:
  query, category (NEGATIVE/normal/high_risk/...), refusal_reason,
  qualified_n, retrieved (bool/docs), viol_kinds, viol_detail
  (partial/unsupported counts), minimal_answer_pass (optional test),
  draft (optional), r4 (optional flag)
"""
from __future__ import annotations

import re

_R4 = re.compile(r"我|我家|孩子|父母|预算|收入|岁|房贷|怎么配|推荐|适合我")
_HARD = re.compile(
    r"\d|该产品|这款|某产品|保险法|管理办法|监管|银保监|令第|施行|"
    r"保证.{0,6}(续保|赔付|返还)|承诺|所有|全部|一律|任何|必然|一定|您|你的")


def classify(rec: dict) -> dict:
    """-> {classification, reason, supporting_evidence, source_event,
    confidence}."""
    q = str(rec.get("query", ""))
    cat = str(rec.get("category", "")).upper()
    reason = rec.get("refusal_reason", "")
    qual = rec.get("qualified_n", 0) or 0
    retrieved = rec.get("retrieved", True)
    viol = rec.get("viol_kinds") or []
    detail = rec.get("viol_detail") or {}

    def out(cls, why, ev, conf):
        return {"classification": cls, "reason": why,
                "supporting_evidence": ev,
                "source_event": rec.get("source_event", "-"),
                "confidence": conf}

    if "NEGATIVE" in cat:
        return out("SAFE_REFUSAL", "negative/out-of-scope query",
                   "category=NEGATIVE", 0.99)
    if reason == "insufficient_evidence" or (not retrieved) or qual == 0:
        if _R4.search(q) and "personal" in cat.lower() or \
                rec.get("r4"):
            return out("R4_PERSONALIZATION",
                       "personalization ask without user facts "
                       "(relevance floor empty)", "qualified_n=0 + "
                       "personal phrasing", 0.85)
        return out("INSUFFICIENT_EVIDENCE",
                   "no qualified evidence (governed floor)",
                   "qualified_n=%d" % qual, 0.9)
    if reason == "llm_unavailable":
        return out("OTHER", "provider transient", "llm_unavailable", 0.95)
    if "fact_sentence" in viol and "claim_support" not in viol:
        return out("WHOLE_QUESTION_GATE",
                   "citation presence failure (model omitted [E#])",
                   "viol=fact_sentence only", 0.8)
    if "claim_support" in viol:
        partial = detail.get("partial", 0) or 0
        unsup = detail.get("unsupported", 0) or 0
        if unsup and not partial:
            return out("SAFE_REFUSAL",
                       "unsupported/overreaching claims correctly "
                       "refused", "unsupported=%d partial=%d"
                       % (unsup, partial), 0.85)
        if _HARD.search(rec.get("draft") or q) and rec.get(
                "hard_blocked"):
            return out("HARD_CLASS_BLOCK",
                       "failing sentences are hard-class "
                       "(KEEP_BASELINE by design)",
                       "hard patterns in failing sentences", 0.8)
        if rec.get("minimal_answer_pass"):
            # verified subset demonstrably deliverable but whole answer
            # was refused
            if partial >= 2:
                return out("WHOLE_QUESTION_GATE",
                           "multi-sentence answer: partial-ceiling "
                           "sentences sank the whole answer though a "
                           "verified subset passed",
                           "minimal-answer gate PASS + partial=%d"
                           % partial, 0.9)
            return out("UTILITY_FALSE_REFUSAL",
                       "minimal cited answer passes both gates; "
                       "whole answer refused",
                       "minimal_answer_pass=True", 0.9)
        return out("PARTIAL_CEILING",
                   "lexical support cannot verify evidence-grounded "
                   "paraphrases (PARTIAL dominant)",
                   "partial=%d unsupported=%d" % (partial, unsup), 0.75)
    return out("CLAIM_SUPPORT_FAILURE" if "claim" in " ".join(viol)
               else "OTHER", "gate family: %s" % ",".join(viol) or "-",
               "reason=%s" % reason, 0.5)
