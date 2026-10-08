# -*- coding: utf-8 -*-
"""FIX-3 Phase 11 — Preflight Authority Wrapper (tools-only).

Production-like control plane reproducing every control point of the
FUTURE Controlled Authority path:

  scope → baseline → evidence/citation → hard-class → risk → judge →
  independent post-gate → quota → observation-window → final decision
  → rollback decision

The wrapper computes a PREFLIGHT_RESULT only. It never writes to any
production final; production_final is an INPUT (echoed from the
baseline runtime) and can never be altered by this class. All state
lives in-process (self-contained), so OFF→ON→OFF switching is
deterministic and leaves zero residual state.
"""
from __future__ import annotations

import re
import time

CIT = re.compile(r"\[E\d+\]")
HARD = re.compile(
    r"\d|P0\d{2}|demo-|该产品|这款|某产品|保险法|管理办法|监管|银保监|"
    r"令第|施行|保证.{0,6}(续保|赔付|返还)|承诺|"
    r"所有|全部|一律|任何|都.{0,3}(能|可|会|是|有)|必然|一定会|"
    r"每个人|所有人群|所有情况|所有产品|"
    r"您|你家|您家|你的")

REQUIRED_VERSIONS = {
    "contract": "candidate-c-authority-contract/v1.0",
    "pipeline": "candidate-c-pipeline/v1.0-phase9",
    "postgate": "independent-postgate/v1.0-phase9",
    "judge": "glm-5.3-flash/qa-slot/tau0.7",
    "rules": "qa-grounding-rules/claim_support+v2levers",
    "config": "preflight-config/v1.0"}

TRUTHY = ("1", "true", "yes", "on")
FALSY = ("0", "false", "no", "off", "")


def _flag(value, default_off=True):
    """Config flag parsing: ONLY explicit truthy turns ON; anything
    else (missing/unknown/malformed/invalid) defaults OFF."""
    v = str(value if value is not None else "").strip().lower()
    if v in TRUTHY:
        return True
    if v in FALSY:
        return False
    return False        # unknown/malformed -> OFF (fail-closed)


class PreflightAuthorityWrapper:
    """STATE machine: authority_on (bool), quotas, incident, versions.

    Kill switch: `kill()` sets authority_on=False and arms
    `incident` recording; recovery to baseline is immediate (same
    object state; no restart needed — verified by rehearsal)."""

    def __init__(self, config: dict = None, judge_fn=None, pg=None):
        cfg = config or {}
        self.config_version = cfg.get("config_version", "")
        self.authority_on = _flag(cfg.get("authority_enabled"))
        self.versions = cfg.get("versions") or {}
        self.quotas = {
            "max_authority_decisions": int(cfg.get(
                "max_authority_decisions", 10)),
            "max_judge_calls": int(cfg.get("max_judge_calls", 20)),
            "max_cost": float(cfg.get("max_cost", 100.0)),
            "max_latency_s": float(cfg.get("max_latency_s", 30.0))}
        self.counters = {"authority_decisions": 0, "judge_calls": 0,
                         "cost": 0.0, "latency_s": 0.0}
        self.incidents = []
        self.quota_service_ok = True
        self.monitoring_ok = True
        self.observation_ok = True
        self.rollback_mechanism_ok = True
        self._judge_fn = judge_fn or (lambda c, e: {
            "decision": "KEEP_BASELINE", "reason": "no-judge"})
        self._pg = pg

    # ---------- control-plane operations ----------
    def kill(self, reason="manual"):
        self.authority_on = False
        self.incidents.append({"reason": reason,
                               "ts": time.strftime("%H:%M:%S")})

    def arm(self):
        self.authority_on = True

    def trigger_incident(self, kind):
        """Any incident → immediate OFF + KEEP_BASELINE contract."""
        self.kill("incident:" + kind)

    def versions_ok(self):
        for k, want in REQUIRED_VERSIONS.items():
            if self.versions.get(k) != want:
                return False
        return True

    def quota_ok(self):
        if not self.quota_service_ok:
            return False            # quota service unavailable -> closed
        return (self.counters["authority_decisions"]
                < self.quotas["max_authority_decisions"]
                and self.counters["judge_calls"]
                < self.quotas["max_judge_calls"]
                and self.counters["cost"] < self.quotas["max_cost"])

    def latency_ok(self):
        return self.counters["latency_s"] < self.quotas["max_latency_s"]

    # ---------- the authority path (PREFLIGHT RESULT ONLY) ----------
    def decide(self, claim, evidence_items, production_final,
               judge_override=None, judge_raw=None, pg_check=None,
               pg_sim=None):
        """Returns a record with candidate_result / preflight_result /
        production_final (echoed, untouched). Guard order mirrors the
        Phase-10 contract: every guard failure -> KEEP_BASELINE and
        the pipeline is never consulted beyond the failing stage."""
        rec = {"claim": claim[:60],
               "production_final": production_final,   # echo only
               "ts": time.strftime("%H:%M:%S")}
        guards = []

        def fail(stage, why):
            guards.append({"stage": stage, "ok": False, "why": why})
            rec.update({"preflight_result": "KEEP_BASELINE",
                        "candidate_result": "NOT_REACHED",
                        "block": stage})
            return rec

        # G0 kill switch
        if not self.authority_on:
            return fail("kill-switch", "authority OFF")
        # G1 monitoring/observation/rollback health (Task 12): if these
        # are down the authority MUST NOT continue blindly
        if not (self.monitoring_ok and self.observation_ok
                and self.rollback_mechanism_ok):
            self.kill("infrastructure-down")
            return fail("infrastructure",
                        "monitoring/observation/rollback unavailable")
        # G2 version + config lock
        if not self.versions_ok() or self.config_version != \
                REQUIRED_VERSIONS["config"]:
            self.kill("version-or-config-mismatch")
            return fail("version-lock", "version/config mismatch")
        # G3 quota + budget
        if not self.quota_ok():
            return fail("quota", "quota/budget exhausted or unavailable")
        # G4 latency budget
        if not self.latency_ok():
            return fail("latency", "latency budget exceeded")
        # G5 scope: hard-class boundary on the RAW claim
        bare = CIT.sub("", claim)
        if HARD.search(bare):
            return fail("scope-hard-class", "hard class not eligible")
        # G6 evidence/citation
        if not evidence_items or not CIT.search(claim):
            return fail("evidence-citation", "missing evidence/citation")
        # G7 deterministic baseline (delegated, read-only)
        from runtime.grounding import claim_support as cs
        base = cs.judge_claim(bare, cs.classify_claim(bare),
                              cs.numeric_anchors(bare), evidence_items)
        rec["baseline"] = base["support_status"]
        if base["support_status"] != "PARTIAL":
            return fail("baseline", "baseline != PARTIAL")
        # G8 semantic judge
        self.counters["judge_calls"] += 1
        if judge_override is not None:
            jd = judge_override
        elif judge_raw is not None:
            jd = self._map_raw(judge_raw)
        else:
            try:
                r = self._judge_fn(claim, evidence_items)
                jd = r.get("decision", "KEEP_BASELINE")
                self.counters["cost"] += r.get("cost", 0.0)
                self.counters["latency_s"] += r.get("latency_s", 0.0)
            except Exception:  # noqa: BLE001 — judge failure -> closed
                jd = "KEEP_BASELINE"
        rec["judge"] = jd
        if jd != "ALLOW_UPGRADE":
            return fail("semantic-judge", "judge %s" % jd)
        # G9 independent post-gate
        if pg_sim:
            pg_ok = False
        else:
            pg_ok, _ = (pg_check or self._default_pg())(claim,
                                                        evidence_items)
        rec["post_gate"] = pg_ok
        if not pg_ok:
            return fail("post-gate", "independent post-gate FAIL")
        # all guards passed -> the ONLY ALLOW point
        self.counters["authority_decisions"] += 1
        rec.update({"candidate_result": "ALLOW_UPGRADE",
                    "preflight_result": "ALLOW_UPGRADE"})
        guards.append({"stage": "all", "ok": True})
        rec["guards"] = guards
        return rec

    def _default_pg(self):
        from k29c_fix3_independent_postgate import IndependentPostGate
        pg = IndependentPostGate()

        def _check(claim, ev):
            ok, r = pg.check(claim, ev)
            return ok, r
        return _check

    @staticmethod
    def _map_raw(raw):
        if not isinstance(raw, dict) or raw.get("error"):
            return "KEEP_BASELINE"
        if raw.get("exempt") or raw.get("contradiction"):
            return "KEEP_BASELINE"
        if raw.get("entailment") == "yes":
            c = raw.get("confidence")
            c = float(c) if isinstance(c, (int, float)) else 0.0
            return "ALLOW_UPGRADE" if c >= 0.7 else "UNCERTAIN"
        return "KEEP_BASELINE"
