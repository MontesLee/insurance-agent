# -*- coding: utf-8 -*-
"""FIX-3 S1' Semantic Judge — PREPARATION ONLY (OD-FIX3-3 with gate).

This module is OFFLINE/SHADOW infrastructure. It is NOT imported by
runtime.grounding.loop or any production gating path (locked by audit);
attaching it as `loop.shadow_observer` is a FUTURE, separately
authorized S1' action.

Contract (k29c-semantic-shadow-design.md / OD-FIX3-6):
  decisions: ALLOW_UPGRADE | KEEP_BASELINE | UNCERTAIN
  EVERY error path — timeout, malformed, low-confidence, disagreement,
  provider failure — collapses to KEEP_BASELINE (INV-2). The judge can
  NEVER downgrade, NEVER override the deterministic hard gate, NEVER
  modify a production answer or the Claim Support authority: the only
  consumer of its output is the shadow RECORD.
"""
from __future__ import annotations

import json
import re
import time
from typing import Optional

ALLOW_UPGRADE = "ALLOW_UPGRADE"
KEEP_BASELINE = "KEEP_BASELINE"
UNCERTAIN = "UNCERTAIN"

DEFAULT_TAU = 0.7          # confidence floor (Owner freezes at S1')
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_CANDIDATES_PER_RUN = 20   # per-run budget cap

JUDGE_SYSTEM_PROMPT = """You are a strict insurance-claim evidence judge. Given ONE claim and its evidence text(s), decide:
1. entailment: "yes" only if the evidence FULLY entails the claim as stated; "partial" if only part; "no" if not.
2. contradiction: true if the evidence explicitly denies what the claim asserts (negation flip, opposite value/direction/scope).
3. exempt: true ONLY for pure procedural guidance / methodology / an honest statement that evidence does not mention something (no checkable insurance fact, no number, no product fact).
4. confidence: your confidence 0.0-1.0.
Watch scope words (所有/全部/一律/任何/都), units (万/元/倍/%), numbers, product identities, and condition qualifiers (等待期内/仅/除外). Output STRICT JSON only:
{"entailment":"yes|partial|no","contradiction":true|false,"exempt":true|false,"confidence":0.0,"reason":"<short>"}"""

OBSERVATION_SCHEMA = {
    "record_type": "s1_shadow_claim",
    "fields": {
        "ts": "iso timestamp", "run_id": "str", "claim_id": "int",
        "claim_text": "str", "cited_labels": ["E1"],
        "deterministic_verdict": "SUPPORTED|PARTIAL|UNSUPPORTED|CONTRADICTED|EXEMPT",
        "hard_class": "bool (numeric/product/regulatory/payout/rec-number premise)",
        "decision": "ALLOW_UPGRADE|KEEP_BASELINE|UNCERTAIN",
        "decision_reason": "entailed|contradiction|not-entailed|exempt|"
                           "low-confidence|error:<kind>",
        "judge_raw": {"entailment": "yes|partial|no",
                      "contradiction": "bool", "exempt": "bool",
                      "confidence": "float", "reason": "str"},
        "latency_s": "float", "model": "str", "cost_hint_tokens": "int"},
    "never_contains": ["api_key", "system_prompt", "full_context"]}

METRICS_SCHEMA = {
    "SAFETY": ["high_risk_false_upgrade", "r3_escape", "r4_escape",
               "numeric_escape", "contradiction_escape",
               "product_identity_escape", "date_time_escape",
               "recommendation_number_escape"],
    "QUALITY": ["true_paraphrase_recovery", "false_refusal_reduction",
                "partial_truth_handling", "generalization_handling"],
    "JUDGE": ["allow_upgrade", "keep_baseline", "uncertain"],
    "OPS": ["p50_latency_s", "p95_latency_s", "timeout_rate",
            "malformed_rate", "model_error_rate", "cost_per_1k_claims",
            "stability_rate"],
    "HARD_STOP_ZERO_REQUIRED_OD-FIX3-6": [
        "high_risk_false_upgrade", "r3_escape", "r4_escape",
        "numeric_escape", "contradiction_escape"],
}


class SemanticJudgeClient:
    """Offline judge client for S1' (and S0 replays). Every failure
    mode returns KEEP_BASELINE — construction-level fail-closed."""

    def __init__(self, provider, tau: float = DEFAULT_TAU,
                 timeout_s: float = DEFAULT_TIMEOUT_S,
                 max_candidates: int = DEFAULT_MAX_CANDIDATES_PER_RUN):
        self._provider = provider
        self.tau = tau
        self.timeout_s = timeout_s
        self.max_candidates = max_candidates
        self.calls = 0
        self.errors = 0
        self.latencies = []

    def judge_claim(self, claim_text: str, evidence_texts: list) -> dict:
        """One claim -> decision record (shadow only; never gates)."""
        t0 = time.time()
        self.calls += 1
        raw, err = None, None
        try:
            ev = "\n\n".join("证据%d：%s" % (i + 1, t)
                             for i, t in enumerate(evidence_texts)) \
                or "（无证据）"
            msgs = [{"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user",
                     "content": "断言：%s\n\n%s" % (claim_text, ev)}]
            r = self._provider.generate(msgs, [])
            raw = (getattr(r, "text", "") or "").strip()
        except Exception as e:  # noqa: BLE001 — every failure collapses
            err = "provider:%s" % type(e).__name__
        self.latencies.append(round(time.time() - t0, 2))
        if err is None:
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                err = "malformed"
                raw = (raw or "")[:120]
            else:
                try:
                    parsed = json.loads(m.group(0))
                    if not isinstance(parsed.get("confidence"),
                                      (int, float)):
                        err = "malformed-no-confidence"
                        parsed = None
                except Exception:  # noqa: BLE001
                    parsed = None
                    err = "malformed-json"
        else:
            parsed = None
        if err is not None:
            self.errors += 1
            return self._record(KEEP_BASELINE, "error:%s" % err,
                                None, claim_text)
        decision, why = self._map(parsed)
        return self._record(decision, why, parsed, claim_text)

    def _map(self, parsed: dict):
        if parsed.get("exempt"):
            return KEEP_BASELINE, "exempt-not-upgradable"
        if parsed.get("contradiction"):
            return KEEP_BASELINE, "contradiction"
        if parsed.get("entailment") == "yes":
            if float(parsed["confidence"]) >= self.tau:
                return ALLOW_UPGRADE, "entailed"
            return UNCERTAIN, "low-confidence"
        return KEEP_BASELINE, "not-entailed"

    def _record(self, decision, why, parsed, claim_text):
        return {"claim_text": claim_text[:120], "decision": decision,
                "decision_reason": why, "judge_raw": parsed,
                "latency_s": self.latencies[-1] if self.latencies else 0}

    # ---- S1' observation sink (attaches to loop.shadow_observer) ----
    def make_run_observer(self, run_id: str, sink):
        """Build the observer callable a FUTURE authorized S1' harness
        attaches to runtime.grounding.loop.shadow_observer. Records
        only; swallows all errors; respects the per-run budget."""
        state = {"candidates": 0}

        def observer(event_type: str, data: dict):
            try:
                if state["candidates"] >= self.max_candidates:
                    return            # budget exhausted — stop recording
                state["candidates"] += 1
                sink(json.dumps({
                    "record_type": "s1_shadow_gate",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime()),
                    "run_id": run_id, "event": event_type,
                    "ok": data.get("ok"),
                    "violations": data.get("violations", [])[:10]},
                    ensure_ascii=False))
            except Exception:  # noqa: BLE001 — observation only
                pass
        return observer
