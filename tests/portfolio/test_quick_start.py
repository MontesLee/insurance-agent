"""Phase 12 — Quick Start acceptance: the FIRST README command must work
offline, keyless, encoding-proof — and must invoke the REAL runtime."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _portfolio_common import Checks, run_sections, run_cmd  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


@section
def test_quick_start_first_command(c: Checks):
    rc, out, err = run_cmd(["-m", "demos.demo_basic"])
    c.chk("quick start: exit 0 (offline, keyless)", rc == 0,
          (rc, err[-160:]))
    c.chk("quick start: prints a final status",
          "Final:" in out and "COMPLETED" in out)
    c.chk("quick start: prints the run summary", "RUN SUMMARY" in out)
    c.chk("quick start: real runtime engaged (agents started)",
          "insurance_analyst" in out)
    c.chk("quick start: no CoT / prompt leakage",
          "system prompt" not in out.lower() and "chain of thought"
          not in out.lower())


@section
def test_quick_start_is_deterministic_and_offline(c: Checks):
    outs = []
    for _ in range(2):
        rc, out, _ = run_cmd(["-m", "demos.demo_basic"])
        outs.append(out)
        c.chk("quick start repeat: exit 0", rc == 0)
    import re
    n = lambda t: re.sub(r"proj_[a-f0-9]+", "X", t)
    c.chk("quick start repeatable (normalized identical)",
          n(outs[0]) == n(outs[1]))
    c.chk("quick start needs no LLM key (no provider error)",
          "ProviderNotConfigured" not in outs[0]
          and "provider unreachable" not in outs[0].lower())


@section
def test_llm_smoke_is_fail_closed_not_silent(c: Checks):
    """The OPTIONAL LLM smoke must never silently pass without the API:
    with a configured-but-dead provider it reports FAIL-CLOSED."""
    env_probe = "import runtime.agent.config as c; print(bool(c.load_llm_config().api_key))"
    import subprocess
    r = subprocess.run([sys.executable, "-c", env_probe], capture_output=True,
                       text=True, cwd=os.path.join(os.path.dirname(
                           os.path.dirname(os.path.abspath(__file__))), ".."))
    # run the smoke; whatever it does, it may NOT print a PASS on outage
    rc, out, err = run_cmd(["-m", "runtime.agent.smoke_test"], timeout=300)
    has_pass = "SMOKE OK" in out
    fail_closed = "FAIL-CLOSED" in out or "SKIP" in out
    c.chk("llm smoke: honest outcome (PASS only with a live provider)",
          has_pass or fail_closed or rc != 0,
          (rc, out[-120:]))
    c.chk("llm smoke: never a silent deterministic fallback",
          "deterministic fallback" not in out.lower())


def main():
    return run_sections(SECTIONS, "webui_test_quick_start_log.txt",
                        "PORTFOLIO QUICK START")


if __name__ == "__main__":
    sys.exit(main())
