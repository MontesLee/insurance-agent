"""Phase 12 — Generalization demo acceptance: the SE domain must run on the
SAME runtime (no fork) and genuinely execute through it."""
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
def test_demo_generalization_real_run(c: Checks):
    rc, out, err = run_cmd(["-m", "demos.demo_generalization"])
    c.chk("generalization demo: exit 0", rc == 0, err[-160:])
    c.chk("SE domain: all 5 tasks PASSED",
          out.count("-> PASSED") == 5, out.count("-> PASSED"))
    c.chk("SE domain: 3 SE agents executed",
          all(a in out for a in ("se_analyst", "se_engineer", "se_qa")))
    c.chk("SE domain: 5 evaluations PASS", "5 evaluations" in out
          and "5 PASS" in out)
    c.chk("SE domain: SE artifacts produced",
          all(t in out for t in ("se-requirements", "se-solution",
                                 "se-implementation", "se-test-plan")))
    c.chk("SE domain: lineage verified", "LINEAGE    verified" in out)
    c.chk("SE domain: FINAL COMPLETED", "FINAL      COMPLETED" in out)
    c.chk("SE domain: deliverable from real artifacts (3 impl tasks)",
          "Implementation plan: 3 tasks" in out)


@section
def test_demo_generalization_no_runtime_fork(c: Checks):
    """The adapter must not copy/fork runtime modules: the demo file only
    REGISTERS domain config and runs the unchanged runtime."""
    repo = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    src = open(os.path.join(repo, "demos", "demo_generalization.py"),
               encoding="utf-8").read()
    for banned in ("from runtime.harness.harness import", "class .*Scheduler",
                   "def _run_parallel", "def _execute_stage",
                   "shutil.copytree", "copy.deepcopy(runtime"):
        c.chk("no-fork: demo never %r" % banned, banned not in src)
    c.chk("no-fork: uses the SAME harness class",
          "from runtime.harness import LongRunningHarness" in src)
    c.chk("no-fork: registers into the SAME trusted registries",
          "TASK_REGISTRY" in src and "AGENT_REGISTRY" in src)
    # and the real runtime is genuinely invoked (behavioral): instrument it
    import subprocess, json
    probe = (
        "import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'tests/runtime');"
        "import runtime.harness.harness as H;"
        "calls=[]; orig=H.LongRunningHarness._run_parallel;"
        "H.LongRunningHarness._run_parallel=lambda s,*a,**k:"
        "(calls.append(1), orig(s,*a,**k))[1];"
        "import demos.demo_generalization as G; rc=G.main();"
        "print('PARALLEL_ROUNDS', len(calls), 'RC', rc)")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                       cwd=repo, env=env, timeout=300)
    c.chk("no-fork: real scheduler executed the SE tasks",
          b"PARALLEL_ROUNDS" in r.stdout and
          int(r.stdout.split(b"PARALLEL_ROUNDS")[1].split()[0]) >= 1,
          r.stdout[-120:])


@section
def test_demo_generalization_repeatable(c: Checks):
    outs = [run_cmd(["-m", "demos.demo_generalization"])[1] for _ in range(3)]
    c.chk("generalization demo: 3/3 completed",
          all("FINAL      COMPLETED" in o for o in outs))


def main():
    return run_sections(SECTIONS, "webui_test_demo_gen_log.txt",
                        "PORTFOLIO GENERALIZATION DEMO")


if __name__ == "__main__":
    sys.exit(main())
