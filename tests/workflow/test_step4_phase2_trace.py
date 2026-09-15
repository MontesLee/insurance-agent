"""Step 4 Phase 2 — Execution Trace verification (spec §4/§5/§6).

Asserts the unified trace is:
  * emitted on every agent action (state["trace"] + mirrored <case_dir>/trace.jsonl);
  * structurally complete — every record carries trace_id/case_id/task_id/skill/event/
    attempt/input_artifacts/output_artifact/eval_status/duration_ms/timestamp;
  * timed — SKILL_COMPLETED records carry a numeric duration_ms;
  * queryable — it can answer "why did the case end the way it did?"
    (e.g. a NEEDS_REVIEW case shows the repair trail + terminal CASE_NEEDS_REVIEW).

Seeding/mutations/gate-approval mirror `test-cases/e2e/full-agent/run_full_agent_e2e.py`
so the trace is produced by exactly the same execution the Full-Agent E2E exercises.

Exit 0 = all checks pass.
"""
from __future__ import annotations

import importlib.util
import copy
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))  # tests/workflow -> repo root
for p in (REPO,):
    if p not in sys.path:
        sys.path.insert(0, p)

from runtime import orchestrator as orch  # noqa: E402

FULL_AGENT_DIR = os.path.join(REPO, "test-cases", "e2e", "full-agent")
MANIFEST = os.path.join(FULL_AGENT_DIR, "manifest.json")
RUN_ROOT = os.path.join(REPO, "tmp", "p2-trace-test")


def _load_harness():
    """Load run_full_agent_e2e.py (hyphenated dir -> import by path) for seed helpers."""
    path = os.path.join(FULL_AGENT_DIR, "run_full_agent_e2e.py")
    spec = importlib.util.spec_from_file_location("full_agent_e2e", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HARNESS = _load_harness()

REQUIRED_FIELDS = ["trace_id", "case_id", "event", "timestamp"]
# the spec §4 fields every record should at least be able to carry
SPEC_FIELDS = ["trace_id", "case_id", "task_id", "skill", "event", "attempt",
               "input_artifacts", "output_artifact", "eval_status", "duration_ms",
               "timestamp", "detail"]

# event types we expect to see in a fully-completed happy-path case
HAPPY_EVENTS = {"CASE_STARTED", "TASK_CREATED", "TASK_STARTED", "SKILL_STARTED",
                "SKILL_COMPLETED", "EVAL_STARTED", "EVAL_COMPLETED",
                "CHECKPOINT_SAVED", "CASE_COMPLETED"}
# events we expect in a repair-exhausted case
REPAIR_EVENTS = {"REPAIR_STARTED", "REPAIR_COMPLETED", "CASE_NEEDS_REVIEW"}


def _run_case(case_file, cid, wf, base):
    """Run one full-agent case exactly like the Full-Agent E2E harness does."""
    with open(os.path.join(FULL_AGENT_DIR, case_file), encoding="utf-8") as f:
        case = json.load(f)
    seeds = HARNESS.apply_mutations(copy.deepcopy(base["artifacts"]),
                                    case.get("mutations", []))
    kb_dir = (os.path.join(REPO, manifest["empty_kb"]) if case.get("kb") == "empty" else None)

    run_dir = os.path.join(RUN_ROOT, cid)
    if os.path.exists(run_dir):
        shutil.rmtree(run_dir)
    os.makedirs(run_dir, exist_ok=True)

    state = orch.seed_case(wf, cid, seeds, provided_by=base.get("provided_by", "upstream-dialogue"))
    rep = orch.run(state, wf, gate_policy="stop", kb_dir=kb_dir, checkpoint_root=run_dir)
    # a human-review gate is a planned pause: approve and continue
    approvals = 0
    while rep["status"] == "PAUSED_NEEDS_REVIEW" and approvals < 3:
        orch.approve(state, rep["stopped_at"])
        approvals += 1
        rep = orch.run(state, wf, gate_policy="stop", kb_dir=kb_dir, checkpoint_root=run_dir)
    return state, rep, run_dir, kb_dir


manifest = {}
passed = failed = 0
lines = []


def chk(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    lines.append("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                                ("  -- " + str(detail)) if (detail and not ok) else ""))


def main():
    global manifest
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    wf = orch.load_workflow()
    base = HARNESS.load_base_seeds(manifest["seeds_file"])

    # ---- happy path: case-001-complete ----------------------------------------
    state, rep, run_dir, _ = _run_case("case-001-complete.json", "case-001-trace", wf, base)
    trace = state.get("trace") or []

    chk("case-001: trace non-empty", len(trace) > 0, len(trace))
    seen = {r["event"] for r in trace}
    missing_happy = HAPPY_EVENTS - seen
    chk("case-001: all happy-path event types emitted", not missing_happy, missing_happy)

    # structural completeness
    bad = [r.get("trace_id") for r in trace
           if not all(k in r for k in REQUIRED_FIELDS)]
    chk("case-001: every record has required fields", not bad, bad[:3])
    all_keys_ok = all(all(k in r for k in SPEC_FIELDS) for r in trace)
    chk("case-001: every record carries all spec §4 fields", all_keys_ok)

    # timing
    sc = [r for r in trace if r["event"] == "SKILL_COMPLETED"]
    chk("case-001: SKILL_COMPLETED emitted", len(sc) > 0, len(sc))
    dur_ok = all(isinstance(r.get("duration_ms"), (int, float)) for r in sc)
    chk("case-001: SKILL_COMPLETED.duration_ms is numeric", dur_ok)
    out_ok = all(r.get("output_artifact") for r in sc)
    chk("case-001: SKILL_COMPLETED.output_artifact set", out_ok)

    # jsonl mirror — lives next to case_state.json: <checkpoint_root>/<case_id>/trace.jsonl
    jsonl = os.path.join(run_dir, "case-001-trace", "trace.jsonl")
    chk("case-001: trace.jsonl exists", os.path.exists(jsonl), jsonl)
    if os.path.exists(jsonl):
        with open(jsonl, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        chk("case-001: trace.jsonl is valid JSONL and non-empty", len(rows) > 0, len(rows))
        chk("case-001: jsonl count >= state trace count", len(rows) >= len(trace),
            "%d jsonl vs %d state" % (len(rows), len(trace)))

    # CASE_COMPLETED present and last-ish
    chk("case-001: CASE_COMPLETED emitted", "CASE_COMPLETED" in seen)
    chk("case-001: case actually COMPLETED", rep["status"] == "COMPLETED", rep["status"])

    # ---- repair-exhausted: case-004-evidence-failure --------------------------
    state2, rep2, _, _ = _run_case("case-004-evidence-failure.json", "case-004-trace", wf, base)
    seen2 = {r["event"] for r in (state2.get("trace") or [])}
    miss_repair = REPAIR_EVENTS - seen2
    chk("case-004: repair trail + CASE_NEEDS_REVIEW emitted", not miss_repair, miss_repair)
    chk("case-004: case actually NEEDS_REVIEW", rep2["status"] == "NEEDS_REVIEW", rep2["status"])
    # queryable (spec §6): the trace must NAME the root cause, not just print "ERROR".
    t2 = state2.get("trace") or []
    fail_sig = [r for r in t2 if r["event"] == "TASK_FAILED" and (r.get("detail") or "").strip()]
    chk("case-004: trace shows a TASK_FAILED naming the root cause", len(fail_sig) > 0,
        [r.get("detail") for r in t2 if r["event"] == "TASK_FAILED"][:3])
    cause_visible = any(
        (("knowledge" in (r.get("detail") or "").lower())
         or ("evidence" in (r.get("detail") or "").lower())
         or (r.get("event") == "EVAL_COMPLETED" and r.get("eval_status") == "FAIL"))
        for r in t2)
    chk("case-004: root cause attributable (evidence / knowledge-search)", cause_visible)
    chk("case-004: terminal event is CASE_NEEDS_REVIEW",
        bool(t2) and t2[-1]["event"] == "CASE_NEEDS_REVIEW", t2[-1]["event"] if t2 else None)

    out = lines + ["", "STEP4-P2 TRACE: %d/%d checks passed" % (passed, passed + failed),
                   "RESULT: %s" % ("ALL GREEN" if failed == 0 else "FAILURES PRESENT")]
    text = "\n".join(out)
    print(text)
    with open(os.path.join(REPO, "tmp", "p2_trace_log.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
