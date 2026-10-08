# -*- coding: utf-8 -*-
"""FIX-3 Phase 12 — CONTROLLED AUTHORITY RUNTIME (ops-layer, in-process).

Owner-approved 2026-10-03 (OD-FIX3-49..65 bundle):
  scope = FACTUAL_PARAPHRASE only (19-condition conjunction)
  cohort = SCRIPTED_PROBE traffic (Batch-2 undistributed)
  wiring = in-process ops launcher (zero git production change;
           restart = complete removal)
  window = session-controlled; >=30 eligible; <=20 authority decisions;
           <=200 judge calls; p95<=30s; rollback threshold=0

Installed by the ops launcher as an attribute-swap of
runtime.grounding.loop.csupp with AuthorityClaimSupportProxy — the
production module itself is untouched on disk. Kill switch = kill-file
(tmp/obs/k29c_fix3_phase12_kill.flag) checked before EVERY authority
decision, so an operator kill takes effect on the next gate call
without restart; in-memory auto-kill arms on any hard-stop condition.

Every authority claim writes the full §14 ledger record.
"""
from __future__ import annotations

import json
import os
import re
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBS = os.path.join(REPO, "tmp", "obs")
LEDGER = os.path.join(OBS, "k29c_fix3_phase12_authority_ledger.jsonl")
KILL_FLAG = os.path.join(OBS, "k29c_fix3_phase12_kill.flag")
INCIDENTS = os.path.join(OBS, "k29c_fix3_phase12_incidents.json")
VERSIONS = {
    "candidate": "candidate-c-pipeline/v1.0-phase9",
    "contract": "candidate-c-authority-contract/v1.0",
    "postgate": "independent-postgate/v1.0-phase9",
    "judge": "glm-5.3-flash/qa-slot/tau0.7",
    "rules": "qa-grounding-rules/claim_support+v2levers",
    "config": "phase12-controlled-authority/v1.0"}

QUOTAS = {"max_authority_decisions": 20, "max_judge_calls": 200,
          "max_latency_s": 30.0, "p95_budget_s": 30.0}

CIT = re.compile(r"\[E\d+\]")
HARD = re.compile(
    r"\d|P0\d{2}|demo-|该产品|这款|某产品|保险法|管理办法|监管|银保监|"
    r"令第|施行|保证.{0,6}(续保|赔付|返还)|承诺|"
    r"所有|全部|一律|任何|都.{0,3}(能|可|会|是|有)|必然|一定会|"
    r"每个人|所有人群|所有情况|所有产品|"
    r"您|你家|您家|你的")


class AuthorityRuntime:
    """Holds all mutable state; one instance per process."""

    def __init__(self):
        self.enabled = True
        self.counters = {"authority_decisions": 0, "judge_calls": 0,
                         "eligible_claims": 0, "upgrades": 0,
                         "baseline_keeps": 0, "hard_intercepts": 0,
                         "postgate_pass": 0, "postgate_fail": 0,
                         "judge_allow": 0, "judge_reject": 0,
                         "judge_uncertain": 0, "errors": 0,
                         "timeouts": 0}
        self.latencies = []
        self.judge = None
        self.pg = None
        self._real_cs = None

    # ---------- kill switch ----------
    def killed(self):
        if os.path.exists(KILL_FLAG):
            return True
        return not self.enabled

    def kill(self, reason):
        self.enabled = False
        with open(KILL_FLAG, "w", encoding="utf-8") as f:
            f.write(reason + "\t" + time.strftime("%Y-%m-%d %H:%M:%S"))
        self.incident("KILL", reason)

    def incident(self, kind, detail):
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "kind": kind, "detail": detail[:160]}
        try:
            arr = json.load(open(INCIDENTS, encoding="utf-8"))
        except Exception:
            arr = []
        arr.append(rec)
        json.dump(arr, open(INCIDENTS, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    # ---------- guards ----------
    def quotas_ok(self):
        return (self.counters["authority_decisions"]
                < QUOTAS["max_authority_decisions"]
                and self.counters["judge_calls"]
                < QUOTAS["max_judge_calls"])

    def record_latency(self, s):
        self.latencies.append(round(s, 2))
        if len(self.latencies) >= 20:
            srt = sorted(self.latencies)
            if srt[int(len(srt) * .95)] > QUOTAS["p95_budget_s"]:
                self.kill("latency p95 over budget")

    # ---------- the authority claim decision ----------
    def decide_claim(self, claim_text, evidence_pairs, rules):
        """One failing C-FACT claim -> authority decision. Returns
        (upgraded: bool, record: dict). Writes the ledger record."""
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "claim": claim_text[:100]}
        # G0 kill
        if self.killed():
            rec.update({"authority_decision": "KEEP_BASELINE",
                        "kill_state": "KILLED"})
            self._ledger(rec)
            return False, rec
        self.counters["eligible_claims"] += 1
        bare = CIT.sub("", claim_text)
        # G1 hard-class / scope
        if HARD.search(bare):
            self.counters["hard_intercepts"] += 1
            rec.update({"authority_decision": "KEEP_BASELINE",
                        "stage": "scope-hard-class"})
            self._ledger(rec)
            return False, rec
        # G2 citation
        if not CIT.search(claim_text) or not evidence_pairs:
            rec.update({"authority_decision": "KEEP_BASELINE",
                        "stage": "citation"})
            self._ledger(rec)
            return False, rec
        # G3 quota
        if not self.quotas_ok():
            rec.update({"authority_decision": "KEEP_BASELINE",
                        "stage": "quota"})
            self._ledger(rec)
            return False, rec
        # G4 baseline (re-derived; caller passes real verdict)
        # (checked by caller — must be PARTIAL)
        # G5 semantic judge (real LLM, wall-bounded)
        from k29c_fix3_candidate_c import items_of
        items = items_of(evidence_pairs)
        texts = [it.get("content", "") for it in items]
        t0 = time.time()
        self.counters["judge_calls"] += 1
        try:
            jr = self.judge.judge_claim(bare, texts[:1])
        except Exception as e:  # noqa: BLE001
            self.counters["errors"] += 1
            jr = {"decision": "KEEP_BASELINE",
                  "decision_reason": "error:%s" % repr(e)[:60]}
        dt = time.time() - t0
        self.record_latency(dt)
        if dt > QUOTAS["max_latency_s"]:
            self.counters["timeouts"] += 1
            jr = {"decision": "KEEP_BASELINE",
                  "decision_reason": "timeout"}
        dec = jr.get("decision")
        rec["judge_result"] = dec
        if dec == "ALLOW_UPGRADE":
            self.counters["judge_allow"] += 1
        elif dec == "UNCERTAIN":
            self.counters["judge_uncertain"] += 1
        else:
            self.counters["judge_reject"] += 1
        if dec != "ALLOW_UPGRADE":
            rec.update({"authority_decision": "KEEP_BASELINE",
                        "stage": "semantic-judge"})
            self._ledger(rec)
            return False, rec
        # G6 independent post-gate (raw inputs)
        raw_ev = [{"content": e.get("content", ""),
                   "source_name": e.get("header", ""),
                   "product_id": (e.get("anchor") or {}).get(
                       "document_id")} for _, e in evidence_pairs]
        ok, reasons = self.pg.check(claim_text, raw_ev)
        if ok:
            self.counters["postgate_pass"] += 1
        else:
            self.counters["postgate_fail"] += 1
        rec["post_gate_result"] = {"ok": ok, "reasons": reasons[:2]}
        if not ok:
            rec.update({"authority_decision": "KEEP_BASELINE",
                        "stage": "post-gate"})
            self._ledger(rec)
            return False, rec
        # G7 version binding (static, in-process pinned)
        rec["version"] = VERSIONS
        # ALL GUARDS PASSED -> the only upgrade point
        self.counters["authority_decisions"] += 1
        self.counters["upgrades"] += 1
        rec.update({"authority_decision": "ALLOW_UPGRADE",
                    "stage": "all-pass"})
        self._ledger(rec)
        return True, rec

    def _ledger(self, rec):
        rec["counters_snapshot"] = dict(self.counters)
        try:
            with open(LEDGER, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 — ledger failure must not
            pass            # change the authority decision (observability)


class AuthorityClaimSupportProxy:
    """Attribute-swapped for runtime.grounding.loop.csupp by the ops
    launcher. check() first runs the REAL deterministic check; only
    when it fails does the bounded authority path run — and only if
    EVERY failing claim upgrades does the verdict flip to ok. All
    other attributes delegate to the real module."""

    def __init__(self, real_module, runtime: AuthorityRuntime):
        self._real = real_module
        self._rt = runtime

    def check(self, text, evidence, rules=None):
        real = self._real.check(text, evidence, rules)
        if real.get("ok", True):
            self._rt.counters["baseline_keeps"] += 1
            return real
        if not self._rt.enabled or self._rt.killed():
            return real
        # authority path: every failing PARTIAL claim must upgrade
        rows = real.get("claims") or []
        from runtime.grounding import gate as ggate
        _r = rules or ggate.load_rules()
        all_upgraded = True
        any_partial = False
        for row in rows:
            if row.get("support_status") == "SUPPORTED":
                continue
            if row.get("support_status") != "PARTIAL":
                all_upgraded = False     # UNSUPPORTED/CONTRADICTED: not eligible
                break
            any_partial = True
            up, _ = self._rt.decide_claim(row["claim_text"], evidence,
                                          _r)
            if not up:
                all_upgraded = False
                break
        if any_partial and all_upgraded:
            out = dict(real)
            out["ok"] = True
            out["violations"] = []
            out["authority_upgrade"] = True
            return out
        return real

    def __getattr__(self, name):
        return getattr(self._real, name)
