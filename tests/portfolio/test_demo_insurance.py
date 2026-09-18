"""Phase 12 — Insurance demo acceptance: the realistic family case must run
the FULL pipeline on the REAL runtime, produce a real report with
provenance — and the demo must not fake anything."""
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
def test_demo_insurance_real_run(c: Checks):
    rc, out, err = run_cmd(["-m", "demos.demo_insurance"])
    c.chk("insurance demo: exit 0", rc == 0, err[-160:])
    c.chk("insurance demo: full 8-task pipeline PASSED",
          out.count("-> PASSED") == 8, out.count("-> PASSED"))
    c.chk("insurance demo: 4 specialists executed",
          all(a in out for a in ("insurance_analyst", "knowledge_specialist",
                                 "product_specialist", "report_specialist")))
    c.chk("insurance demo: evaluations all PASS", "0 FAIL" in out)
    c.chk("insurance demo: final COMPLETED", "FINAL" in out
          and "COMPLETED" in out)
    c.chk("insurance demo: reads the real case file",
          "demo-family-001" in out)
    c.chk("insurance demo: demo-catalog disclaimer present",
          "不构成保险产品推荐" in out or "runtime 演示" in out)


@section
def test_demo_insurance_anti_cheat(c: Checks):
    """The demo must not embed its own answers — every deliverable number
    must come from runtime artifacts. Structural + behavioral checks."""
    src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "demos", "demo_insurance.py")
    src = open(src_path, encoding="utf-8").read()
    c.chk("anti-cheat: no pre-generated report baked in",
          "insurance-report artifact" not in src.replace(
              "insurance-report artifact)", "")  # only the label, no payload
          and "预生成" not in src)
    c.chk("anti-cheat: reads deliverable from the runtime artifact",
          "final.get(\"artifacts\")" in src)
    c.chk("anti-cheat: no event-log replay",
          "events.jsonl read" not in src and "json.load(open" not in src
          or "demo-family-001.json" in src)
    c.chk("anti-cheat: does not bypass the Harness",
          "LongRunningHarness(" in src)
    c.chk("anti-cheat: does not bypass Eval (harness-owned by default)",
          "_run_eval_and_repair" not in src and "skip_eval=True" not in src)


@section
def test_demo_insurance_repeatable(c: Checks):
    outs = [run_cmd(["-m", "demos.demo_insurance"])[1] for _ in range(3)]
    import re
    n = lambda t: re.sub(r"proj_[a-f0-9]+", "X", t)
    c.chk("insurance demo: 3/3 runs exit cleanly",
          all("FINAL   COMPLETED" in o for o in outs))
    c.chk("insurance demo: semantically identical across 3 runs",
          all(n(o) == n(outs[0]) for o in outs))


def main():
    return run_sections(SECTIONS, "webui_test_demo_ins_log.txt",
                        "PORTFOLIO INSURANCE DEMO")


if __name__ == "__main__":
    sys.exit(main())
