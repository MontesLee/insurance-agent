# -*- coding: utf-8 -*-
"""FIX-3 Phase 9 — INDEPENDENT post-gate (test-only checker).

Independence contract (Phase-9 §3): this checker does NOT read the
pipeline's intermediate decisions, the semantic judge's verdict, or the
upstream normalized claim. It re-derives safety from RAW inputs:

  raw claim text + raw evidence structure + risk class + candidate flag

Checks (each independently implemented from raw inputs):
  PG-1 hard-pattern scan on the RAW claim (own regex, compiled here)
  PG-2 citation closure: every [E#] label in the raw claim exists in the
      raw evidence structure (label count)
  PG-3 numeric closure: every numeric anchor in the raw claim occurs in
      the raw evidence CONTENT (value+unit, boundary-aware via cs utils
      on raw text only)
  PG-4 product identity: product_id-bearing evidence items are not used
      to support a claim naming a DIFFERENT product (name check on raw)
  PG-5 evidence presence: non-empty raw evidence
FAIL-CLOSED: any error, missing metadata, or exception -> FAIL (never
fail-open). The checker's PASS is a necessary condition, never a
sufficient one — the pipeline still owns the final conjunction.
"""
from __future__ import annotations

import re

_CIT = re.compile(r"\[E(\d+)\]")
_PG_HARD = re.compile(
    r"\d|P0\d{2}|demo-|该产品|这款|某产品|保险法|管理办法|监管|银保监|"
    r"令第|施行|保证.{0,6}(续保|赔付|返还)|承诺|"
    r"所有|全部|一律|任何|都.{0,3}(能|可|会|是|有)|必然|一定会|"
    r"每个人|所有人群|所有情况|所有产品|"
    r"您|你家|您家|你的")
_PG_PRODUCT = re.compile(
    r"(?:重疾险|医疗险|寿险|意外险|年金险|护理险|防癌险|团险)")


class IndependentPostGate:
    """Returns (ok: bool, reasons: list[str]) — FAIL-closed."""

    def check(self, raw_claim: str, raw_evidence, risk_class=None,
              candidate_decision=None) -> tuple:
        try:
            reasons = []
            if not isinstance(raw_claim, str) or not raw_claim.strip():
                return False, ["PG-5 empty/missing raw claim"]
            # PG-5 evidence presence (raw structure may be [] = missing)
            evs = list(raw_evidence or [])
            if not evs:
                return False, ["PG-5 missing raw evidence"]
            # PG-1 hard patterns on RAW claim (citations INCLUDED: a
            # citation digit is not a fact, so strip ONLY citations)
            bare = _CIT.sub("", raw_claim)
            m = _PG_HARD.search(bare)
            if m:
                reasons.append("PG-1 hard pattern: %s" % m.group(0))
            # PG-2 citation closure against raw evidence labels
            labels = {int(x) for x in _CIT.findall(raw_claim)}
            if labels and max(labels) > len(evs):
                reasons.append("PG-2 citation label out of range")
            # PG-3 numeric closure (raw claim vs raw content)
            from runtime.grounding import claim_support as cs
            anchors = cs.numeric_anchors(bare)
            corpus = " ".join((e.get("content") or "") for e in evs)
            for _l, v, u in anchors:
                if not cs._value_found(v, cs._norm_unit(u), corpus):
                    reasons.append("PG-3 numeric %s%s not in evidence"
                                   % (v, u))
                    break
            # PG-4 product identity (raw name variants vs item identity)
            bound = [e for e in evs if e.get("product_id")]
            if bound:
                identity = " ".join(
                    str(e.get("product_id")) + " "
                    + str(e.get("document_name") or "") + " "
                    + str(e.get("source_name") or "") + " "
                    + (e.get("content") or "") for e in bound)
                hit = False
                for m2 in _PG_PRODUCT.finditer(bare):
                    end = m2.end()
                    for k in range(0, 7):
                        cand = bare[max(0, m2.start() - k):end]
                        if len(cand) >= 3 and cand in identity:
                            hit = True
                            break
                    if hit:
                        break
                has_name = bool(_PG_PRODUCT.search(bare))
                if has_name and not hit:
                    reasons.append("PG-4 product name not in bound "
                                   "evidence identity")
            ok = not reasons
            return ok, reasons
        except Exception as e:  # noqa: BLE001 — fail-closed by contract
            return False, ["PG-X exception: %s" % repr(e)[:60]]

    def check_timeout_sim(self):
        """Simulated post-gate timeout — contract: FAIL."""
        return False, ["PG-T timeout"]

    def check_malformed_sim(self):
        """Simulated malformed output — contract: FAIL."""
        return False, ["PG-M malformed"]
