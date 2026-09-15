"""Step 3 — Orchestrator self-evaluations (spec §39).

These are the properties the orchestrator MUST hold about ITSELF, independent of any insurance
judgement:

  SE-1 dependency  -- a stage whose producer is missing/blocked cannot run; the pipeline stops.
  SE-2 ordering    -- stages execute in the declared workflow order (topological, not arbitrary).
  SE-3 retry       -- a failed stage is locally re-run up to the repair budget, then escalates.
  SE-4 resume      -- after a checkpointed pause, resuming does NOT re-execute PASSed tasks.
  SE-5 review      -- a human-review gate is a real stop: it cannot be bypassed without approve().

All deterministic; no model calls. Exit 0 = every self-eval holds.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (REPO_ROOT,):
    if p not in sys.path:
        sys.path.insert(0, p)

from runtime.state import case_state as cs  # noqa: E402
from runtime import orchestrator as orch  # noqa: E402
from runtime import checkpoint as cp  # noqa: E402

FIXTURE = os.path.join(REPO_ROOT, "tests", "e2e", "fixtures", "case-full-chain.json")
KB_EMPTY = os.path.join(REPO_ROOT, "test-cases", "e2e", "full-agent", "kb-empty")
LOG = os.path.join(HERE, "_step3_orchestrator_self_eval_log.txt")

_results = []


def check(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                         ("  -- " + str(detail)) if detail and not ok else ""))


def _fixture_artifacts():
    return json.load(io.open(FIXTURE, encoding="utf-8"))["artifacts"]


def main():
    wf = orch.load_workflow()

    # ===== SE-1 dependency ==========================================================
    seeds = _fixture_artifacts()
    del seeds["risk-assessment"]  # remove a provided upstream seed on purpose
    st = orch.seed_case(wf, "CASE-SE1", seeds)
    rep = orch.run(st, wf, gate_policy="stop")
    check("SE-1 a missing provided upstream blocks the pipeline",
          rep["status"] == "BLOCKED" and rep["stopped_at"] == "risk-analysis",
          (rep["status"], rep["stopped_at"]))
    downstream = ("coverage-gap-analysis", "solution", "product-candidate-provider",
                  "product-recommendation", "report-generation")
    check("SE-1 no downstream stage ran past the blocked stage",
          all(st["stages"][x]["status"] == "PENDING" for x in downstream),
          {x: st["stages"][x]["status"] for x in downstream})

    # ===== SE-2 ordering ===========================================================
    st = orch.seed_case(wf, "CASE-SE2", _fixture_artifacts())
    rep = orch.run(st, wf, gate_policy="auto")
    check("SE-2 full run completes", rep["status"] == "COMPLETED", rep.get("reasons"))
    expected = [s["id"] for s in wf["stages"] if s.get("executor") != "provided"]
    got = [e["stage"] for e in rep.get("executed", [])]
    check("SE-2 execution order follows the declared workflow order",
          got == expected, (got, expected))

    # ===== SE-3 retry ==============================================================
    case4 = json.load(io.open(
        os.path.join(REPO_ROOT, "test-cases", "e2e", "full-agent",
                     "case-004-evidence-failure.json"), encoding="utf-8"))
    seeds = _fixture_artifacts()
    st = orch.seed_case(wf, "CASE-SE3", seeds)
    rep = orch.run(st, wf, gate_policy="stop", kb_dir=KB_EMPTY)
    check("SE-3 evidence failure escalates to NEEDS_REVIEW at the producer stage",
          rep["status"] == "NEEDS_REVIEW" and rep["stopped_at"] == "product-candidate-provider",
          (rep["status"], rep["stopped_at"]))
    st3 = st["stages"]["product-candidate-provider"]
    check("SE-3 repair budget not exceeded (<=3 attempts)", st3["attempts"] <= 3, st3["attempts"])
    check("SE-3 exactly two local repairs attempted before escalation",
          len(st3.get("repairs", [])) == 2, len(st3.get("repairs", [])))

    # ===== SE-4 resume =============================================================
    tmpd = tempfile.mkdtemp(prefix="step3-resume-")
    try:
        st = orch.seed_case(wf, "CASE-SE4", _fixture_artifacts())
        rep = orch.run(st, wf, gate_policy="stop", checkpoint_root=tmpd)
        check("SE-4 a human-review gate pauses the case",
              rep["status"] == "PAUSED_NEEDS_REVIEW"
              and rep["stopped_at"] == "product-recommendation",
              (rep["status"], rep["stopped_at"]))
        before = {t["task_id"]: (t["status"], t["attempt"]) for t in st["tasks"]}
        loaded, errs = cp.load(tmpd, "CASE-SE4")
        check("SE-4 a valid checkpoint is available for resume", loaded is not None, errs)
        orch.approve(loaded, "product-recommendation")
        rep2 = orch.run(loaded, wf, gate_policy="stop", checkpoint_root=tmpd)
        check("SE-4 resume completes after human approval",
              rep2["status"] == "COMPLETED", rep2.get("stopped_at"))
        after = {t["task_id"]: (t["status"], t["attempt"]) for t in loaded["tasks"]}
        rerun = [tid for tid, (stt, at) in before.items()
                 if stt == "PASS" and after.get(tid, (None, 0))[1] > at]
        check("SE-4 resume does not re-execute PASSed tasks", not rerun, rerun)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)

    # ===== SE-5 review (gate is a real stop) =======================================
    st = orch.seed_case(wf, "CASE-SE5", _fixture_artifacts())
    rep1 = orch.run(st, wf, gate_policy="stop")
    check("SE-5 the case pauses for human review",
          rep1["status"] == "PAUSED_NEEDS_REVIEW"
          and rep1["stopped_at"] == "product-recommendation",
          (rep1["status"], rep1["stopped_at"]))
    # Re-running without approval must NOT bypass the gate.
    rep2 = orch.run(st, wf, gate_policy="stop")
    check("SE-5 without human approval the case cannot advance past the gate",
          rep2["status"] == "PAUSED_NEEDS_REVIEW"
          and rep2["stopped_at"] == "product-recommendation",
          (rep2["status"], rep2["stopped_at"]))
    # Only an explicit approve() releases it.
    orch.approve(st, "product-recommendation")
    rep3 = orch.run(st, wf, gate_policy="stop")
    check("SE-5 an explicit approve() releases the gate and completes",
          rep3["status"] == "COMPLETED", rep3.get("stopped_at"))

    passed = sum(1 for _, ok in _results if ok)
    lines = ["STEP3 ORCHESTRATOR SELF-EVAL: %d/%d passed" % (passed, len(_results)),
             "RESULT: %s" % ("ALL GREEN" if passed == len(_results) else "FAILURES PRESENT")]
    print("\n".join(lines))
    io.open(LOG, "w", encoding="utf-8").write(
        "\n".join(["%s %s" % ("PASS" if ok else "FAIL", n) for n, ok in _results] + [""] + lines))
    sys.exit(0 if passed == len(_results) else 1)


if __name__ == "__main__":
    main()
