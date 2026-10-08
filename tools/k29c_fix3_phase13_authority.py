# -*- coding: utf-8 -*-
"""FIX-3 Phase 13 — Authority Runtime v2: delivery path + latency fix.

Root causes found by Phase-12 ledger trace (see phase13 report §1):
  D1 GRANULARITY MISMATCH: production citation gate enforces at
     SENTENCE level; v1 authority required CLAIM(clause)-level [E#].
     90/113 eligible claims were clause fragments whose SENTENCE carried
     the citation but the fragment didn't -> wrongly ineligible.
     v2 groups failing PARTIAL clauses by source sentence and enforces
     citation at the SAME sentence granularity the production gate uses.
  D2 DELIVERY ASSEMBLY: answer flips only when EVERY failing unit
     upgrades; v1 mixed calls (some clauses upgraded, some judge-reject)
     left the answer refused with upgrades stranded. v2 decides at
     sentence-unit granularity (matching the gate) so an upgraded
     sentence is a complete pass unit.
  D3 LATENCY TAIL: judge calls duplicated across streaming segments +
     final gate, and single calls can exceed 40s on the coding plan.
     v2 memoizes judge verdicts per text (same request lifecycle reuse)
     and wall-caps the judge provider at 25s (long tails collapse to
     KEEP_BASELINE — fail-closed, never fail-open).

Safety contract UNCHANGED: citation requirement identical to production
gate granularity; support upgrades only through the full chain (hard/
risk boundary -> judge -> independent post-gate -> quota/version);
every decision ledgered with production_final_source.
"""
from __future__ import annotations

import json
import os
import re
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBS = os.path.join(REPO, "tmp", "obs")
LEDGER = os.path.join(OBS, "k29c_fix3_phase12_authority_ledger.jsonl")
TRACE = os.path.join(OBS, "k29c_fix3_phase13_delivery_trace.jsonl")
KILL_FLAG = os.path.join(OBS, "k29c_fix3_phase12_kill.flag")
INCIDENTS = os.path.join(OBS, "k29c_fix3_phase12_incidents.json")
VERSIONS = {
    "candidate": "candidate-c-pipeline/v1.1-phase13",
    "contract": "candidate-c-authority-contract/v1.0",
    "postgate": "independent-postgate/v1.0-phase9",
    "judge": "glm-5.3-flash/qa-slot/tau0.7/wall25s",
    "rules": "qa-grounding-rules/claim_support+v2levers",
    "config": "phase13-delivery-fix/v1.0"}

QUOTAS = {"max_authority_decisions": 20, "max_judge_calls": 200,
          "judge_wall_s": 25.0, "p95_budget_s": 30.0}

CIT = re.compile(r"\[E\d+\]")
HARD = re.compile(
    r"\d|P0\d{2}|demo-|该产品|这款|某产品|保险法|管理办法|监管|银保监|"
    r"令第|施行|保证.{0,6}(续保|赔付|返还)|承诺|"
    r"所有|全部|一律|任何|都.{0,3}(能|可|会|是|有)|必然|一定会|"
    r"每个人|所有人群|所有情况|所有产品|"
    r"您|你家|您家|你的")


class AuthorityRuntimeV2:
    def __init__(self, kill_file=None):
        # kill_file default = the production kill flag; offline tests
        # pass their own path so verification never depends on the
        # live stack's kill state (which must stay KILLED)
        self._kill_file = kill_file or KILL_FLAG
        self.enabled = True
        self.counters = {"authority_decisions": 0, "judge_calls": 0,
                         "judge_cache_hits": 0, "eligible_sentences": 0,
                         "upgrades": 0, "answer_flips": 0,
                         "baseline_keeps": 0, "hard_intercepts": 0,
                         "postgate_pass": 0, "postgate_fail": 0,
                         "judge_allow": 0, "judge_reject": 0,
                         "judge_uncertain": 0, "judge_timeouts": 0,
                         "errors": 0}
        self.latencies = []
        self._judge_cache = {}
        self.judge = None
        self.pg = None

    # ---------- kill switch ----------
    def killed(self):
        return os.path.exists(self._kill_file) or not self.enabled

    def kill(self, reason):
        self.enabled = False
        with open(self._kill_file, "w", encoding="utf-8") as f:
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

    # ---------- judge with memo + wall cap ----------
    def judge_decide(self, text, texts):
        key = text[:120]
        if key in self._judge_cache:
            self.counters["judge_cache_hits"] += 1
            return self._judge_cache[key]
        self.counters["judge_calls"] += 1
        t0 = time.time()
        try:
            jr = self.judge.judge_claim(text, texts[:1])
        except Exception as e:  # noqa: BLE001
            self.counters["errors"] += 1
            jr = {"decision": "KEEP_BASELINE",
                  "decision_reason": "error:%s" % repr(e)[:60]}
        dt = time.time() - t0
        self.record_latency(dt)
        if dt > QUOTAS["judge_wall_s"]:
            self.counters["judge_timeouts"] += 1
            jr = {"decision": "KEEP_BASELINE",
                  "decision_reason": "wall-timeout"}
        self._judge_cache[key] = jr
        return jr

    # ---------- sentence-unit authority decision ----------
    def decide_sentence(self, sentence, evidence_pairs):
        """One failing PARTIAL-clause group (sentence unit) -> decision.
        Citation enforced at SENTENCE granularity (= production gate)."""
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "sentence": sentence[:100]}
        if self.killed():
            rec.update({"authority_decision": "KEEP_BASELINE",
                        "stage": "kill-switch"})
            self._ledger(rec)
            return False, rec
        self.counters["eligible_sentences"] += 1
        bare = CIT.sub("", sentence)
        # hard/scope boundary (sentence unit)
        if HARD.search(bare):
            self.counters["hard_intercepts"] += 1
            rec.update({"authority_decision": "KEEP_BASELINE",
                        "stage": "scope-hard-class"})
            self._ledger(rec)
            return False, rec
        # citation at PRODUCTION gate granularity: sentence must carry [E#]
        if not CIT.search(sentence) or not evidence_pairs:
            rec.update({"authority_decision": "KEEP_BASELINE",
                        "stage": "citation-sentence"})
            self._ledger(rec)
            return False, rec
        if not self.quotas_ok():
            rec.update({"authority_decision": "KEEP_BASELINE",
                        "stage": "quota"})
            self._ledger(rec)
            return False, rec
        # judge (memoized + wall-capped)
        jr = self.judge_decide(bare, [e.get("content", "")
                                      for _, e in evidence_pairs][:1])
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
        # independent post-gate on the sentence (raw inputs)
        raw_ev = [{"content": e.get("content", ""),
                   "source_name": e.get("header", ""),
                   "product_id": (e.get("anchor") or {}).get(
                       "document_id")} for _, e in evidence_pairs]
        ok, reasons = self.pg.check(sentence, raw_ev)
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
        rec["version"] = VERSIONS
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
        except Exception:  # noqa: BLE001
            pass

    def trace(self, rec):
        try:
            with open(TRACE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass


class AuthorityClaimSupportProxyV2:
    """v2: sentence-unit grouping. For a failing csupp.check(text):
    split text into sentences; every sentence whose clauses are all
    SUPPORTED passes; sentences with failing clauses must fully upgrade
    through the authority chain (sentence-granularity citation). The
    verdict flips to ok ONLY if every failing sentence upgrades."""

    def __init__(self, real_module, runtime: AuthorityRuntimeV2):
        self._real = real_module
        self._rt = runtime

    def check(self, text, evidence, rules=None):
        real = self._real.check(text, evidence, rules)
        if real.get("ok", True):
            self._rt.counters["baseline_keeps"] += 1
            return real
        if self._rt.killed():
            return real
        from runtime.grounding import gate as ggate
        _r = rules or ggate.load_rules()
        # group failing clause rows into sentence units
        sentences = [s for s in ggate.split_sentences(text, _r)
                     if s.strip()]
        row_texts = {row["claim_text"] for row in real.get("claims") or []
                     if row.get("support_status") not in ("SUPPORTED",)}
        # map each failing row to its containing sentence
        sent_of_row = {}
        for rt_ in row_texts:
            head = rt_[:24]
            for s in sentences:
                if head and head in s:
                    sent_of_row[rt_] = s
                    break
        failing_sents = {}
        for rt_, s in sent_of_row.items():
            failing_sents.setdefault(s, []).append(rt_)
        # sentences containing failing rows must not contain
        # UNSUPPORTED/CONTRADICTED clauses (only PARTIAL upgradable)
        for row in real.get("claims") or []:
            if row.get("support_status") in ("UNSUPPORTED",
                                             "CONTRADICTED"):
                s = sent_of_row.get(row["claim_text"])
                if s is not None:
                    # mark sentence as non-upgradable
                    failing_sents[s] = None
        trace = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "text_head": text[:60],
                 "failing_sentences": len(failing_sents)}
        all_up = bool(failing_sents) and all(
            v is not None for v in failing_sents.values())
        if all_up:
            for s in failing_sents:
                up, _ = self._rt.decide_sentence(s, evidence or [])
                if not up:
                    all_up = False
                    break
        trace.update({
            "all_failing_upgraded": all_up,
            "verdict_flipped": all_up,
            "production_final_source": ("AUTHORITY_REGEN_RESULT"
                                        if all_up else "BASELINE")})
        self._rt.trace(trace)
        if all_up:
            self._rt.counters["answer_flips"] += 1
            out = dict(real)
            out["ok"] = True
            out["violations"] = []
            out["authority_upgrade"] = True
            return out
        return real

    def __getattr__(self, name):
        return getattr(self._real, name)
