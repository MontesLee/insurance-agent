"""Phase 17 — Security, Governance & Observability tests.

Wraps both evaluators and adds: CORS boundary (strict ≠ wildcard),
fail-closed injection wiring, evaluator independence, latency-honesty
labels, and the production redaction fix regression (bank_card /
policy_number now in the deny-list).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


@section
def test_security_eval(c: Checks):
    from evals.security import run_security_eval as se
    se.RESULTS.clear()
    se.auth_cases()
    se.authz_cases()
    se.approval_cases()
    se.redaction_cases()
    se.policy_cases()
    se.isolation_cases()
    se.retention_cases()
    se.error_cases()
    se.audit_tamper_cases()
    se.auth_mutations()
    hard, groups = se.aggregate()
    total = len(se.RESULTS)
    passed = sum(1 for r in se.RESULTS if r["status"] == "PASS")
    c.chk("security: >=70 deterministic cases", total >= 70, total)
    c.chk("security: all cases PASS (%d/%d)" % (passed, total),
          passed == total,
          [r["case_id"] for r in se.RESULTS if r["status"] == "FAIL"][:5])
    c.chk("security: hard gates SG-HGxx all zero", hard == {}, hard)
    c.chk("security: M-AUTH-01..10 all detected",
          groups.get("auth_mutation") == "10/10", groups)
    for g, want in (("auth", "9/9"), ("authz", "33/33"),
                    ("approval", "13/13"), ("pii", "12/12"),
                    ("isolation", "5/5"), ("provider", "6/6")):
        c.chk("security: %s group %s" % (g, want),
              groups.get(g) == want, groups.get(g))
    # fail-closed injection wiring: one forged-allow flips a gate
    se.RESULTS.append(se.case.__globals__["RESULTS"][-1] if False
                      else {"case_id": "INJECT", "group": "authz",
                            "status": "FAIL", "detail": "wiring"})
    h2, _g2 = se.aggregate()
    c.chk("wiring: injected unauthorized action flips SG-HG02",
          h2.get("SG-HG02") == 1, h2)
    se.RESULTS.pop()


@section
def test_observability_eval(c: Checks):
    from evals import observability as oe_pkg
    import importlib
    mod = importlib.import_module(
        "evals.observability.run_observability_eval")
    mod.RESULTS.clear()
    code = mod.main()
    c.chk("observability: evaluator exit 0 (trace+mutations+latency)",
          code == 0)
    report = os.path.join(REPO, "tmp", "observability_report.json")
    import json
    with open(report, encoding="utf-8") as f:
        rep = json.load(f)
    lat = rep["latency"]
    c.chk("observability: latency over 10 cases with percentiles",
          lat["cases"] == 10 and all(k in lat for k in
                                     ("min_s", "median_s", "p95_s",
                                      "max_s")))
    c.chk("observability: latency labeled NOT representative",
          "NOT STATISTICALLY REPRESENTATIVE" in lat["note"])
    tok = rep["tokens"]
    c.chk("observability: tokens honest (NOT_MEASURABLE, llm_calls=0 "
          "as measured proxy)", tok["input_tokens"] == "NOT_MEASURABLE"
          and tok["llm_calls"] == 0)
    muts = [r for r in rep["results"] if r["case_id"].startswith("M-OBS")]
    c.chk("observability: M-OBS-01..08 all detected (%d)" % len(muts),
          len(muts) == 8 and all(r["status"] == "PASS" for r in muts))


@section
def test_cors_and_fix_regression(c: Checks):
    from runtime import auth as runtime_auth
    old = os.environ.get("INSURANCE_AGENT_CORS_ORIGINS")
    old_mode = os.environ.get("INSURANCE_AGENT_MODE")
    try:
        os.environ.pop("INSURANCE_AGENT_CORS_ORIGINS", None)
        os.environ.pop("INSURANCE_AGENT_DEV", None)
        os.environ["INSURANCE_AGENT_MODE"] = "production"
        prod = runtime_auth.cors_origins()
        c.chk("CORS: strict mode never wildcard", "*" not in prod, prod)
        # a wildcard SET outside dev is dropped, never honored
        os.environ["INSURANCE_AGENT_CORS_ORIGINS"] = "*"
        dropped = runtime_auth.cors_origins()
        c.chk("CORS: wildcard env outside dev is dropped (fail-closed "
              "to loopback)", "*" not in dropped, dropped)
        # explicit dev flag is the only path to a wildcard
        os.environ["INSURANCE_AGENT_DEV"] = "1"
        os.environ.pop("INSURANCE_AGENT_CORS_ORIGINS", None)
        dev = runtime_auth.cors_origins()
        c.chk("CORS: wildcard only with explicit INSURANCE_AGENT_DEV=1",
              dev == ["*"], dev)
        os.environ.pop("INSURANCE_AGENT_DEV", None)
        os.environ["INSURANCE_AGENT_CORS_ORIGINS"] = \
            "https://a.example,https://b.example"
        allow = runtime_auth.cors_origins()
        c.chk("CORS: allowlist honored (unknown origins excluded)",
              allow == ["https://a.example", "https://b.example"], allow)
    finally:
        for var, oldval in (("INSURANCE_AGENT_CORS_ORIGINS", old),
                            ("INSURANCE_AGENT_MODE", old_mode)):
            if oldval is not None:
                os.environ[var] = oldval
            else:
                os.environ.pop(var, None)
        os.environ.pop("INSURANCE_AGENT_DEV", None)
    # regression for the Phase-17 redaction fix (production change #1)
    from runtime.state import dataprotection as dp
    red = dp.redact({"bank_card": "6222020200112233445",
                     "policy_number": "P123456789"})
    c.chk("fix-regression: bank_card redacted",
          red["bank_card"] == "[REDACTED]")
    c.chk("fix-regression: policy_number redacted",
          red["policy_number"] == "[REDACTED]")
    c.chk("fix-regression: deny-list superset intact (name/phone/...)",
          {"name", "phone", "id_number", "health_status"}
          <= set(dp.SENSITIVE_FIELDS))


@section
def test_independence(c: Checks):
    offenders = []
    for root in ("knowledge", "runtime", "adapters"):
        for dp_, _d, fs in os.walk(os.path.join(REPO, root)):
            if "__pycache__" in dp_:
                continue
            for fn in fs:
                if fn.endswith(".py"):
                    body = open(os.path.join(dp_, fn),
                                encoding="utf-8").read()
                    if ("evals.security" in body
                            or "evals.observability" in body):
                        offenders.append(fn)
    c.chk("independence: production never imports the evaluators",
          offenders == [], offenders)
    for rel in ("evals/security/run_security_eval.py",
                "evals/observability/run_observability_eval.py"):
        body = open(os.path.join(REPO, rel), encoding="utf-8").read()
        c.chk("independence: %s deterministic (no LLM judge/network)"
              % rel.split("/")[-1],
              "openai" not in body and "import requests" not in body
              and "judge" not in body.lower())


def main():
    return run_sections(SECTIONS, "p17_security_obs_log.txt",
                        "PHASE 17 SECURITY & OBSERVABILITY")


if __name__ == "__main__":
    sys.exit(main())
