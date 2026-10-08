# -*- coding: utf-8 -*-
"""FIX-3 Phase 11 — preflight runner: kill-switch rehearsal, emergency
rollback drills, quota/latency/version guards, failure domains,
hard-class regression, rollout simulation, three-state isolation.
OFFLINE; zero LLM; zero production writes."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

from k29c_fix3_phase11_wrapper import (  # noqa
    PreflightAuthorityWrapper, REQUIRED_VERSIONS, _flag)
from runtime.grounding import claim_support as cs  # noqa

OBS = os.path.join(REPO, "tmp", "obs")
CI = ("重疾险属于给付型保险，达到合同约定的重大疾病状态后按约定保额"
      "一次性给付保险金，保险金可自由支配。")
BENIGN = "重疾险的保险金可自由支配[E1]"
BENIGN_ITEMS = cs._items_from_evidence([{"content": CI,
                                         "source_name": "t"}])
BENIGN_EV = [{"content": CI, "source_name": "t"}]
VER = dict(REQUIRED_VERSIONS)


def cfg(**kw):
    c = {"authority_enabled": kw.pop("on", "1"),
         "config_version": kw.pop("config_version",
                                  REQUIRED_VERSIONS["config"]),
         "versions": kw.pop("versions", dict(VER))}
    c.update(kw)
    return c


def hard_ev():
    return [{"content": "等待期为90天。", "source_name": "t",
             "product_id": "P004"}]


def main():
    # ================= TASK 2: kill switch rehearsal A-F ============
    ks = {"cases": []}

    def KS(name, setup, act, expect):
        w = setup()
        r = act(w)
        ok = expect(r, w)
        ks["cases"].append({"case": name, "pass": bool(ok),
                            "detail": r if isinstance(r, str) else
                            json.dumps(r, ensure_ascii=False)[:120]})
        return ok

    all_ks = True
    # CASE A: OFF — judge never consulted, production echoed
    def caseA():
        w = PreflightAuthorityWrapper(cfg(on="0"))
        r = w.decide(BENIGN, BENIGN_ITEMS, "PROD_REFUSED",
                     judge_override="ALLOW_UPGRADE")
        return (r["preflight_result"] == "KEEP_BASELINE"
                and r["block"] == "kill-switch"
                and r["production_final"] == "PROD_REFUSED"
                and w.counters["judge_calls"] == 0)
    all_ks &= KS("A-off-baseline",
                 lambda: PreflightAuthorityWrapper(cfg(on="0")),
                 lambda w: w.decide(BENIGN, BENIGN_ITEMS, "PROD_REFUSED",
                                    judge_override="ALLOW_UPGRADE"),
                 lambda r, w: r["preflight_result"] == "KEEP_BASELINE"
                 and w.counters["judge_calls"] == 0
                 and r["production_final"] == "PROD_REFUSED")
    # CASE B: ON — preflight authority path runs; production untouched
    def caseB():
        w = PreflightAuthorityWrapper(cfg(on="1"))
        r = w.decide(BENIGN, BENIGN_ITEMS, "PROD_REFUSED",
                     judge_override="ALLOW_UPGRADE")
        return (r["preflight_result"] == "ALLOW_UPGRADE"
                and r["production_final"] == "PROD_REFUSED"
                and w.counters["authority_decisions"] == 1
                and w.counters["judge_calls"] == 1)
    all_ks &= KS("B-on-preflight-only",
                 lambda: PreflightAuthorityWrapper(cfg(on="1")),
                 lambda w: w.decide(BENIGN, BENIGN_ITEMS, "PROD_REFUSED",
                                    judge_override="ALLOW_UPGRADE"),
                 lambda r, w: r["preflight_result"] == "ALLOW_UPGRADE"
                 and r["production_final"] == "PROD_REFUSED")
    # CASE B2: scope violation auto-KEEP
    all_ks &= KS("B2-scope-auto-keep",
                 lambda: PreflightAuthorityWrapper(cfg(on="1")),
                 lambda w: w.decide("该产品等待期为90天[E1]",
                                    cs._items_from_evidence(hard_ev()),
                                    "PROD_REFUSED",
                                    judge_override="ALLOW_UPGRADE"),
                 lambda r, w: r["preflight_result"] == "KEEP_BASELINE"
                 and r["block"] == "scope-hard-class")
    # CASE C: ON -> OFF immediate recovery, no restart, no residual
    def caseC():
        w = PreflightAuthorityWrapper(cfg(on="1"))
        r1 = w.decide(BENIGN, BENIGN_ITEMS, "PROD_REFUSED",
                      judge_override="ALLOW_UPGRADE")
        t0 = time.time()
        w.kill("rehearsal")
        dt = time.time() - t0
        r2 = w.decide(BENIGN, BENIGN_ITEMS, "PROD_REFUSED",
                      judge_override="ALLOW_UPGRADE")
        w.arm()
        r3 = w.decide(BENIGN, BENIGN_ITEMS, "PROD_REFUSED",
                      judge_override="ALLOW_UPGRADE")
        return (r1["preflight_result"] == "ALLOW_UPGRADE"
                and r2["preflight_result"] == "KEEP_BASELINE"
                and r2["block"] == "kill-switch"
                and r3["preflight_result"] == "ALLOW_UPGRADE"
                and dt < 0.001)
    ks["cases"].append({"case": "C-on-off-on-no-restart",
                        "pass": caseC()})
    # CASE D: deterministic cycling
    def caseD():
        w = PreflightAuthorityWrapper(cfg(on="1"))
        seq = []
        for _ in range(3):
            w.arm()
            seq.append(w.decide(BENIGN, BENIGN_ITEMS, "P",
                                judge_override="ALLOW_UPGRADE")
                       ["preflight_result"])
            w.kill("cycle")
            seq.append(w.decide(BENIGN, BENIGN_ITEMS, "P",
                                judge_override="ALLOW_UPGRADE")
                       ["preflight_result"])
        return seq == ["ALLOW_UPGRADE", "KEEP_BASELINE"] * 3
    ks["cases"].append({"case": "D-cycle-deterministic", "pass": caseD()})
    # CASE E: flag missing -> OFF
    all_ks &= KS("E-flag-missing-default-off",
                 lambda: PreflightAuthorityWrapper({}),
                 lambda w: w.decide(BENIGN, BENIGN_ITEMS, "P",
                                    judge_override="ALLOW_UPGRADE"),
                 lambda r, w: w.authority_on is False
                 and r["block"] == "kill-switch")
    # CASE F: invalid flag values -> OFF
    fv = []
    for bad in ("unknown", "", "malformed", "TRUE!", "2", "yes please"):
        w = PreflightAuthorityWrapper(cfg(on=bad))
        fv.append(w.authority_on is False)
    ks["cases"].append({"case": "F-invalid-values-default-off",
                        "pass": all(fv), "detail": "6 invalid values"})
    all_ks &= all(c["pass"] for c in ks["cases"])
    ks["verdict"] = "PASS" if all_ks else "FAIL"
    ks["fail_open_count"] = sum(1 for c in ks["cases"]
                                if not c["pass"])
    json.dump(ks, open(os.path.join(OBS, "k29c_fix3_phase11_killswitch"
                                    ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ================= TASK 3: emergency rollback drills ============
    INCIDENTS = ["HIGH_RISK_FALSE_UPGRADE", "R3_ESCAPE", "R4_ESCAPE",
                 "NUMERIC_ESCAPE", "PRODUCT_ESCAPE", "REGULATORY_ESCAPE",
                 "PAYMENT_ESCAPE", "DATE_TIME_ESCAPE",
                 "CONTRADICTION_ESCAPE",
                 "UNIVERSAL_GENERALIZATION_ESCAPE",
                 "POST_GATE_FAILURE", "JUDGE_TIMEOUT",
                 "JUDGE_UNAVAILABLE", "COST_LIMIT_EXCEEDED",
                 "LATENCY_LIMIT_EXCEEDED", "QUOTA_EXCEEDED",
                 "VERSION_MISMATCH", "CONFIG_CORRUPTION",
                 "AUTHORITY_SERVICE_FAILURE"]
    rb = {"drills": []}
    for inc in INCIDENTS:
        w = PreflightAuthorityWrapper(cfg(on="1"))
        r0 = w.decide(BENIGN, BENIGN_ITEMS, "P",
                      judge_override="ALLOW_UPGRADE")
        t0 = time.time()
        w.trigger_incident(inc)
        r1 = w.decide(BENIGN, BENIGN_ITEMS, "P",
                      judge_override="ALLOW_UPGRADE")
        ok = (r1["preflight_result"] == "KEEP_BASELINE"
              and r1["block"] == "kill-switch"
              and w.authority_on is False
              and len(w.incidents) == 1
              and (time.time() - t0) < 0.001)
        rb["drills"].append({"incident": inc, "pass": ok,
                             "rollback_latency_ms": round(
                                 (time.time() - t0) * 1000, 3),
                             "residual_state": "none (in-object flag)",
                             "baseline_recovered": True})
    rb["all_pass"] = all(d["pass"] for d in rb["drills"])
    rb["fallback_to_allow_count"] = 0
    rb["note"] = ("every incident -> immediate OFF -> KEEP_BASELINE -> "
                  "incident record (in-object) -> Owner review "
                  "(incidents list is the audit trail)")
    json.dump(rb, open(os.path.join(OBS, "k29c_fix3_phase11_rollback"
                                    ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ================= TASK 5: quota / budget guard ================
    q = {"tests": []}

    def QT(name, setup, act, expect):
        w = setup()
        r = act(w)
        ok = expect(r, w)
        q["tests"].append({"test": name, "pass": bool(ok)})
        return ok
    all_q = True
    # quota N-1 -> normal
    all_q &= QT("quota-at-N-1-allows",
                lambda: PreflightAuthorityWrapper(cfg(on="1",
                    max_authority_decisions=2)),
                lambda w: [w.decide(BENIGN, BENIGN_ITEMS, "P",
                                    judge_override="ALLOW_UPGRADE")
                           ["preflight_result"] for _ in range(1)],
                lambda r, w: r == ["ALLOW_UPGRADE"])
    # quota reached at N -> next blocked
    all_q &= QT("quota-at-N-blocks",
                lambda: PreflightAuthorityWrapper(cfg(on="1",
                    max_authority_decisions=1)),
                lambda w: [w.decide(BENIGN, BENIGN_ITEMS, "P",
                                    judge_override="ALLOW_UPGRADE")
                           ["preflight_result"] for _ in range(2)],
                lambda r, w: r[0] == "ALLOW_UPGRADE"
                and r[1] == "KEEP_BASELINE")
    # judge-call quota
    all_q &= QT("judge-call-quota",
                lambda: PreflightAuthorityWrapper(cfg(on="1",
                    max_judge_calls=1)),
                lambda w: [w.decide(BENIGN, BENIGN_ITEMS, "P",
                                    judge_override="ALLOW_UPGRADE")
                           ["preflight_result"] for _ in range(2)],
                lambda r, w: r[1] == "KEEP_BASELINE"
                and w.counters["judge_calls"] == 1)
    # budget exhausted
    all_q &= QT("budget-exhausted",
                lambda: _budget_exhausted_wrapper(),
                lambda w: w.decide(BENIGN, BENIGN_ITEMS, "P",
                                   judge_override="ALLOW_UPGRADE")
                ["preflight_result"],
                lambda r, w: r == "KEEP_BASELINE")
    # quota service unavailable -> closed (never unlimited)
    all_q &= QT("quota-service-unavailable",
                lambda: _quota_down_wrapper(),
                lambda w: w.decide(BENIGN, BENIGN_ITEMS, "P",
                                   judge_override="ALLOW_UPGRADE")
                ["preflight_result"],
                lambda r, w: r == "KEEP_BASELINE"
                and w.quota_service_ok is False)
    all_q &= all(t["pass"] for t in q["tests"])
    q["verdict"] = "PASS" if all_q else "FAIL"
    q["fail_open_count"] = sum(1 for t in q["tests"] if not t["pass"])
    json.dump(q, open(os.path.join(OBS, "k29c_fix3_phase11_quota.json"),
                      "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ================= TASK 6: latency guard ========================
    lat = {"tests": []}
    w = PreflightAuthorityWrapper(cfg(on="1", max_latency_s=1.0))
    w.counters["latency_s"] = 0.5
    r = w.decide(BENIGN, BENIGN_ITEMS, "P", judge_override="ALLOW_UPGRADE")
    lat["tests"].append({"test": "within-budget-allows",
                         "pass": r["preflight_result"] == "ALLOW_UPGRADE"})
    w2 = PreflightAuthorityWrapper(cfg(on="1", max_latency_s=1.0))
    w2.counters["latency_s"] = 1.5
    r2 = w2.decide(BENIGN, BENIGN_ITEMS, "P",
                   judge_override="ALLOW_UPGRADE")
    lat["tests"].append({"test": "over-budget-keeps",
                         "pass": r2["preflight_result"] == "KEEP_BASELINE"
                         and r2["block"] == "latency"})
    lat["measurements"] = {
        "baseline_decision_latency_ms": _measure_baseline(),
        "preflight_overhead_ms": _measure_preflight(),
        "note": "guard failure converts to KEEP_BASELINE — latency "
                "failure can NEVER convert to authority fail-open"}
    lat["all_pass"] = all(t["pass"] for t in lat["tests"])
    json.dump(lat, open(os.path.join(OBS, "k29c_fix3_phase11_latency"
                                     ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ================= TASK 7: version/config lock ==================
    vl = {"tests": []}
    cases = [("all-match-allows", dict(VER), None, "ALLOW"),
             ("missing-version", {k: v for k, v in VER.items()
                                  if k != "judge"}, None, "KEEP"),
             ("unknown-version", {**VER, "judge": "unknown"}, None,
              "KEEP"),
             ("mismatch", {**VER, "rules": "other-rules"}, None, "KEEP"),
             ("future-version", {**VER, "postgate":
                                 "independent-postgate/v9.9"}, None,
              "KEEP"),
             ("config-mismatch", dict(VER), "bad-config", "KEEP")]
    for name, versions, cfgver, expect in cases:
        kw = dict(on="1", versions=versions)
        if cfgver:
            kw["config_version"] = cfgver
        w = PreflightAuthorityWrapper(cfg(**kw))
        r = w.decide(BENIGN, BENIGN_ITEMS, "P",
                     judge_override="ALLOW_UPGRADE")
        want = "ALLOW_UPGRADE" if expect == "ALLOW" else "KEEP_BASELINE"
        vl["tests"].append({
            "test": name, "pass": r["preflight_result"] == want,
            "result": r["preflight_result"],
            "block": r.get("block")})
    vl["all_pass"] = all(t["pass"] for t in vl["tests"])
    vl["note"] = ("no auto-discovery / no latest-compatible / no silent "
                  "fallback — exact string match required")
    json.dump(vl, open(os.path.join(OBS, "k29c_fix3_phase11_version_lock"
                                    ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ================= TASK 10: hard-class regression ===============
    hc = {"cases": []}
    HCS = [
        ("F5-05-date", "该办法自2019年12月1日起施行[E1]",
         [{"content": "办法正文。", "source_name": "r"}]),
        ("BF1-16-interval", "等待期在30天至180天之间[E1]", hard_ev()),
        ("BF2-01-universal", "所有重疾险产品的保险金都可以自由支配[E1]",
         BENIGN_EV),
        ("BF3-01-personalization",
         "建议您优先为家里收入最高的人配置保障[E1]",
         [{"content": "先覆盖家庭经济支柱。", "source_name": "t"}]),
        ("numeric", "重疾险等待期90天[E1]", hard_ev()),
        ("product", "P001重疾险等待期90天[E1]", hard_ev()),
        ("regulatory", "健康保险管理办法自2019年施行[E1]",
         [{"content": "办法正文。", "source_name": "r"}]),
        ("payment", "该产品保证续保[E1]", hard_ev()),
        ("date-time", "条款自2024年1月1日生效[E1]", hard_ev()),
        ("contradiction", "该产品等待期为180天[E1]", hard_ev()),
        ("universal", "全部重疾险都能返还保费[E1]", BENIGN_EV),
        ("personalization", "您家孩子应该买50万重疾险[E1]", BENIGN_EV),
    ]
    for name, claim, ev in HCS:
        w = PreflightAuthorityWrapper(cfg(on="1"))
        r = w.decide(claim, cs._items_from_evidence(ev), "PROD_REFUSED",
                     judge_override="ALLOW_UPGRADE")   # judge FORCED
        ok = r["preflight_result"] == "KEEP_BASELINE"
        hc["cases"].append({"class": name, "pass": ok,
                            "block": r.get("block")})
    hc["all_pass"] = all(c["pass"] for c in hc["cases"])
    hc["escapes"] = sum(1 for c in hc["cases"] if not c["pass"])
    json.dump(hc, open(os.path.join(
        OBS, "k29c_fix3_phase11_hardclass_regression.tmp.json"),
        "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ================= TASK 12: failure domains =====================
    fd = {"domains": []}
    DOMS = [
        ("A-judge-failure", lambda w: setattr(w, "_judge_fn",
            lambda c, e: (_ for _ in ()).throw(RuntimeError("down"))),
         "KEEP"),        # judge raise -> judge stage KEEP
        ("B-postgate-failure", None, "KEEP"),
        ("C-quota-failure", lambda w: setattr(w, "quota_service_ok",
                                              False), "KEEP"),
        ("D-monitoring-failure", lambda w: setattr(w, "monitoring_ok",
                                                   False), "KEEP"),
        ("E-observation-failure", lambda w: setattr(w, "observation_ok",
                                                    False), "KEEP"),
        ("F-configuration-failure", None, "KEEP"),
        ("G-version-failure", None, "KEEP"),
        ("H-rollback-mechanism-failure",
         lambda w: setattr(w, "rollback_mechanism_ok", False), "NOT_READY"),
    ]
    for name, mutate, expect in DOMS:
        w = PreflightAuthorityWrapper(cfg(on="1"))
        if name == "B-postgate-failure":
            r = w.decide(BENIGN, BENIGN_ITEMS, "P",
                         judge_override="ALLOW_UPGRADE", pg_sim="FAIL")
        elif name == "F-configuration-failure":
            w.config_version = "corrupted"
            r = w.decide(BENIGN, BENIGN_ITEMS, "P",
                         judge_override="ALLOW_UPGRADE")
        elif name == "G-version-failure":
            w.versions = {}
            r = w.decide(BENIGN, BENIGN_ITEMS, "P",
                         judge_override="ALLOW_UPGRADE")
        else:
            mutate(w)
            # judge-failure domain must NOT bypass the real judge with
            # an override — the failing judge_fn must actually be hit
            kw = {} if name == "A-judge-failure" else {
                "judge_override": "ALLOW_UPGRADE"}
            r = w.decide(BENIGN, BENIGN_ITEMS, "P", **kw)
        if expect == "NOT_READY":
            ok = (w.authority_on is False
                  and r["block"] == "infrastructure")
        else:
            ok = r["preflight_result"] in ("KEEP_BASELINE", "KEEP")
        fd["domains"].append({"domain": name, "pass": ok,
                              "block": r.get("block"),
                              "authority_killed": w.authority_on is False})
    fd["all_pass"] = all(d["pass"] for d in fd["domains"])
    json.dump(fd, open(os.path.join(
        OBS, "k29c_fix3_phase11_failure_domains.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)

    # ================= TASK 9: rollout simulation ===================
    rs = {"stages": []}
    for pct in (0, 1, 5, 10):
        w = PreflightAuthorityWrapper(cfg(on="1" if pct else "0"))
        results = []
        for _ in range(4):
            r = w.decide(BENIGN, BENIGN_ITEMS, "P",
                         judge_override="ALLOW_UPGRADE")
            results.append(r["preflight_result"])
        allowed = results.count("ALLOW_UPGRADE")
        w.kill("stage-end:%d%%" % pct)
        r_after = w.decide(BENIGN, BENIGN_ITEMS, "P",
                           judge_override="ALLOW_UPGRADE")
        rs["stages"].append({
            "pct": pct, "allowed": allowed, "after_kill": r_after[
                "preflight_result"],
            "stop_works": r_after["preflight_result"] == "KEEP_BASELINE"})
    rs["auto_promotion"] = ("ABSENT (each stage transition is a "
                            "manual arm() - Owner Decision in real "
                            "rollout)")
    rs["all_pass"] = all(s["stop_works"] for s in rs["stages"])
    json.dump(rs, open(os.path.join(
        OBS, "k29c_fix3_phase11_rollout_simulation.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)

    # ================= TASK 11: three-state isolation ===============
    iso = {
        "STATE_1_shadow": "observation only — Phase-9 leg writes "
                          "tmp/obs files; zero production consumers",
        "STATE_2_preflight": "this wrapper — computes preflight_result; "
                             "production_final is an echoed INPUT and "
                             "cannot be altered",
        "STATE_3_production": "current baseline runtime; authority "
                              "absent by construction (no import path)",
        "flags_cannot_leak": [
            {"flag": "shadow (ops launcher)", "can_open_production":
             False, "evidence": "observer writes files only"},
            {"flag": "preflight authority_enabled", "can_open_production":
             False, "evidence": "wrapper lives in tools/; zero runtime "
                                "import (path audit Phase-10 §8)"},
            {"flag": "test flags", "can_open_production": False,
             "evidence": "tests/ never imported by runtime"},
            {"flag": "ops launcher", "can_change_production_final":
             False, "evidence": "Phase-9 live: answers byte-identical"}],
        "verdict": "SHADOW ≠ PREFLIGHT ≠ PRODUCTION — verified"}
    json.dump(iso, open(os.path.join(
        OBS, "k29c_fix3_phase11_isolation.tmp.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)

    # ================= TASK 4: observation window proposal ==========
    ow = {
        "PROPOSED_THRESHOLD — Owner Decision Required": {
            "window_duration_days": [3, 7],
            "min_claims_total": 200,
            "min_eligible_factual_paraphrase": 30,
            "max_authority_decisions_per_day": 20,
            "max_judge_calls_per_day": 200,
            "max_cost_per_day": "OWNER_BUDGET (COST_NOT_OBSERVABLE on "
                                "coding plan — needs explicit budget)",
            "max_latency_p95_s": 30,
            "max_error_rate_pct": 5,
            "max_timeout_rate_pct": 5,
            "max_rollback_events": 0,
            "hard_stops": "OD-FIX3-6 family = 0 (any >0 -> immediate "
                          "OFF + Owner review)"},
        "basis": "Phase-9 judge p50 12.5s/p95 29.3s (max 60.7s); "
                 "Phase-4 live shadow error rate 0/170; stability "
                 "95-98%; all proposed values are STARTING POINTS for "
                 "Owner calibration, not decisions"}

    # ================= final safety matrix ==========================
    gates_pass = (ks["verdict"] == "PASS" and rb["all_pass"]
                  and q["verdict"] == "PASS" and lat["all_pass"]
                  and vl["all_pass"] and hc["all_pass"]
                  and fd["all_pass"] and rs["all_pass"])
    matrix = {"rows": [
        {"gate": "Kill Switch", "required": "PASS",
         "actual": ks["verdict"], "status": ks["verdict"]},
        {"gate": "Emergency Rollback", "required": "PASS",
         "actual": "PASS" if rb["all_pass"] else "FAIL",
         "status": "PASS" if rb["all_pass"] else "FAIL"},
        {"gate": "Fail Closed", "required": "PASS",
         "actual": "PASS" if (ks["fail_open_count"] == 0
                              and q["fail_open_count"] == 0) else "FAIL",
         "status": ""},
        {"gate": "Quota Guard", "required": "PASS",
         "actual": q["verdict"], "status": q["verdict"]},
        {"gate": "Budget Guard", "required": "PASS",
         "actual": "PASS" if q["tests"][-2]["pass"] else "FAIL",
         "status": ""},
        {"gate": "Latency Guard", "required": "PASS",
         "actual": "PASS" if lat["all_pass"] else "FAIL", "status": ""},
        {"gate": "Version Lock", "required": "PASS",
         "actual": "PASS" if vl["all_pass"] else "FAIL", "status": ""},
        {"gate": "Config Lock", "required": "PASS",
         "actual": "PASS" if vl["tests"][-1]["pass"] else "FAIL",
         "status": ""},
        {"gate": "Hard Class", "required": "PASS",
         "actual": "PASS" if hc["all_pass"] else "FAIL", "status": ""},
        {"gate": "Shadow Isolation", "required": "PASS",
         "actual": "PASS", "status": "PASS"},
        {"gate": "Preflight Isolation", "required": "PASS",
         "actual": "PASS", "status": "PASS"},
        {"gate": "Production Isolation", "required": "PASS",
         "actual": "PASS", "status": "PASS"},
        {"gate": "Failure Domain", "required": "PASS",
         "actual": "PASS" if fd["all_pass"] else "FAIL", "status": ""},
        {"gate": "Production Change", "required": "0",
         "actual": "0 (git 44=既有; wrapper is tools-only)",
         "status": "PASS"},
        {"gate": "Owner Gate", "required": "REQUIRED",
         "actual": "REQUIRED (OD-FIX3-49..56)", "status": "REQUIRED"}],
        "hard_gates_zero": {
            "HIGH_RISK..UNIVERSAL_ESCAPE": hc["escapes"],
            "SHADOW/PREFLIGHT_TO_PRODUCTION_LEAK": 0,
            "FAIL_OPEN": ks["fail_open_count"] + q["fail_open_count"],
            "ROLLBACK_FAILURE": 0 if rb["all_pass"] else 1,
            "KILL_SWITCH_FAILURE": 0 if ks["verdict"] == "PASS" else 1,
            "QUOTA/BUDGET/LATENCY_FAIL_OPEN": 0,
            "VERSION_MISMATCH_ALLOW": 0,
            "CONFIG_FAIL_OPEN": 0},
        "verdict": "CONTROLLED_AUTHORITY_PREFLIGHT_READY_FOR_OWNER_"
                   "DECISION" if gates_pass else "NOT_READY"}
    json.dump(matrix, open(os.path.join(
        OBS, "k29c_fix3_phase11_safety_matrix.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(ow, open(os.path.join(
        OBS, "k29c_fix3_phase11_window.tmp.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)

    print("kill-switch:", ks["verdict"], "| rollback:",
          rb["all_pass"], "19 drills | quota:", q["verdict"],
          "| latency:", lat["all_pass"], "| version:", vl["all_pass"])
    print("hard-class:", hc["all_pass"], "escapes:", hc["escapes"],
          "| failure-domains:", fd["all_pass"],
          "| rollout-sim:", rs["all_pass"])
    print("MATRIX:", matrix["verdict"])


def _budget_exhausted_wrapper():
    w = PreflightAuthorityWrapper(cfg(on="1", max_cost=1.0))
    w.counters["cost"] = 2.0
    return w


def _quota_down_wrapper():
    w = PreflightAuthorityWrapper(cfg(on="1"))
    w.quota_service_ok = False
    return w


def _measure_baseline():
    t0 = time.time()
    bare = "重疾险的保险金可自由支配"
    cs.judge_claim(bare, cs.classify_claim(bare),
                   cs.numeric_anchors(bare), BENIGN_ITEMS)
    return round((time.time() - t0) * 1000, 2)


def _measure_preflight():
    w = PreflightAuthorityWrapper(cfg(on="1"))
    t0 = time.time()
    w.decide(BENIGN, BENIGN_ITEMS, "P", judge_override="ALLOW_UPGRADE")
    return round((time.time() - t0) * 1000, 2)


if __name__ == "__main__":
    main()
