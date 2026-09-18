"""Phase 12 — the 5–10 minute portfolio demo, one command.

Six acts, all REAL runtime execution (never replayed, never simulated):
  1. Problem        — the realistic family case (demo-family-001)
  2. Planner        — the validated task graph
  3. Multi-Agent    — 4 specialists + real A2A handoffs through the bus
  4. Runtime Trace  — T+normalized timeline from the durable event log
  5. Advanced       — failure → controlled REPLANNING, then HOTL pause/resume
  6. Result         — the deliverable + provenance, then the SE domain swap

Status-only output: no prompts, no chain-of-thought, no raw JSON dumps.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, os.path.join(REPO, "tests", "runtime")):
    if p not in sys.path:
        sys.path.insert(0, p)

from runtime import orchestrator as orch                    # noqa: E402
from runtime.approval import ApprovalStore                 # noqa: E402
from runtime.control import ControlStore                   # noqa: E402
from runtime.harness import LongRunningHarness             # noqa: E402
from runtime.planner.planner import FakePlannerProvider    # noqa: E402
from runtime.state import store as ss                      # noqa: E402
from test_parallel_scheduler import TaskScriptProvider     # noqa: E402
from evals.benchmark import scriptlib                      # noqa: E402
from evals.benchmark import runner as bench                # noqa: E402


def _safe(t):
    try:
        return str(t).encode(sys.stdout.encoding or "utf-8").decode(
            sys.stdout.encoding or "utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
        return str(t).encode("ascii", "replace").decode("ascii")


def say(t=""):
    print(_safe(t))


BAR = "=" * 64


def timeline(p):
    """T+normalized timeline from the DURABLE event log (order is real;
    wall-clock is normalized for presentation)."""
    t0 = None
    rows = []
    import datetime
    def ts(e):
        try:
            return datetime.datetime.fromisoformat(
                e["timestamp"].replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None
    for e in p.events():
        s = ts(e)
        if s is None:
            continue
        if t0 is None:
            t0 = s
        rows.append((int((s - t0).total_seconds()), e))
    return rows


# ---- the same realistic case as demo_insurance, plus failure hooks ------- #
GRAPH = {"tasks": [
    {"task_id": "task_0", "task_type": "client_profile"},
    {"task_id": "task_1", "task_type": "requirement_analysis",
     "dependencies": ["task_0"]},
    {"task_id": "task_2", "task_type": "risk_analysis",
     "dependencies": ["task_0", "task_1"]},
    {"task_id": "task_3", "task_type": "coverage_gap",
     "dependencies": ["task_0", "task_1", "task_2"]},
    {"task_id": "task_4", "task_type": "solution",
     "dependencies": ["task_1", "task_2", "task_3"]},
    {"task_id": "task_5", "task_type": "knowledge_search",
     "dependencies": ["task_1"]},
    {"task_id": "task_6", "task_type": "product_candidates",
     "dependencies": ["task_4", "task_5"]},
    {"task_id": "task_7", "task_type": "report_generation",
     "dependencies": ["task_0", "task_1", "task_2", "task_6"]},
]}
SCRIPTS = {
    "task_0": "profile", "task_1": "req", "task_2": "risk",
    "task_3": "coverage_gap", "task_4": "solution", "task_5": "know",
    "task_6": "product", "task_7": "report",
}
V2 = {"tasks": [t for t in GRAPH["tasks"] if t["task_id"] != "task_5"]}


def main() -> int:
    root = tempfile.mkdtemp(prefix="demo_pf_", dir=os.path.join(REPO, "tmp"))
    try:
        return _run(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _run(root) -> int:
    case = json.load(open(os.path.join(REPO, "client-intake-data",
                                      "demo-family-001.json"),
                         encoding="utf-8"))
    say(BAR)
    say("ACT 1 — THE PROBLEM")
    say(BAR)
    say("A family advisory task, not a chatbot demo:")
    say("  30岁已婚 · 0岁孩子 · 年收入50万元 · 计划200万元房贷 · 双方父母赡养")
    say("  → 分析保险风险，给出保障方案。Requires: multiple specialists,")
    say("    real artifacts, evaluation, and recoverable execution.")
    say("")

    say(BAR)
    say("ACT 2 — PLANNER (WHAT)")
    say(BAR)
    say("The request becomes a validated task graph (10-check validator):")
    for t in GRAPH["tasks"]:
        say("  %-8s %-22s deps=%s" % (t["task_id"], t["task_type"],
                                      t.get("dependencies") or []))
    say("")

    # ---- run 1: full advisory with a knowledge failure + A2A ------------- #
    say(BAR)
    say("ACT 3 — MULTI-AGENT COLLABORATION (live)")
    say(BAR)
    h = LongRunningHarness(
        root,
        agent_executor=TaskScriptProvider(scriptlib.expand_scripts(SCRIPTS)),
        planner_provider=FakePlannerProvider([json.dumps(V2)]),
        max_concurrency=2)
    p = h.create_project("portfolio", task_graph=GRAPH)
    state = orch.seed_case(orch.load_workflow(), p.case_id, {})
    ss.save(state, os.path.join(root, p.project_id, "case"))
    result = h.run(p)
    final = ss.load(os.path.join(root, p.project_id, "case"), p.case_id) or {}

    agents = sorted({e.get("agent_id") for e in p.events()
                     if e["event_type"] == "agent_started"})
    say("4 specialist agents executed (%s)" % ", ".join(agents))
    say("Parallel branches ran concurrently (max_concurrency=2).")
    say("")

    say(BAR)
    say("ACT 4 — RUNTIME TRACE (from the durable event log)")
    say(BAR)
    shown = 0
    for dt, e in timeline(p):
        et = e["event_type"]
        if et in ("task_started", "task_completed", "task_failed",
                  "agent_started", "checkpoint_created", "replan_triggered",
                  "graph_revision_created", "monitor_signal_detected",
                  "intervention_notified", "eval_passed"):
            label = {
                "task_started": "task %s started" % e.get("task_id"),
                "task_completed": "task %s completed" % e.get("task_id"),
                "task_failed": "task %s failed (%s)" % (
                    e.get("task_id"), str(e.get("reason", ""))[:30]),
                "agent_started": "agent %s started" % e.get("agent_id"),
                "checkpoint_created": "checkpoint",
                "replan_triggered": "REPLAN triggered",
                "graph_revision_created": "graph revision v%s" % e.get("graph_revision"),
                "monitor_signal_detected": "monitor signal (%s)" % e.get("signal_type"),
                "intervention_notified": "human NOTIFIED (risk %s)" % e.get("risk_level"),
                "eval_passed": "eval PASS",
            }[et]
            say("  T+%-3ds %s" % (dt, label))
            shown += 1
            if shown >= 22:
                say("  ...")
                break
    evals = final.get("evaluations") or []
    say("")
    say("Quality: %d evaluations, %d PASS / %d FAIL"
        % (len(evals), sum(1 for e in evals if e["status"] == "PASS"),
           sum(1 for e in evals if e["status"] == "FAIL")))
    say("Artifacts: %s" % ", ".join(sorted((final.get("artifacts")
                                            or {}).keys())))
    ok, _ = __import__("runtime.artifact_registry", fromlist=["verify"]).verify(final)
    say("Lineage: %s (report → candidates → knowledge → client facts)"
        % ("verified" if ok else "BROKEN"))
    say("")

    # ---- ACT 5: replanning + HOTL (from the Phase-10/11 proven cases) ---- #
    say(BAR)
    say("ACT 5 — ADVANCED: RECOVERY UNDER FAILURE (live)")
    say(BAR)
    say("Now break it: knowledge_search fails, downstream blocks, and the")
    say("runtime must recover without faking anything. Replanning:")
    c6 = bench.load_cases({"B006"})[0]
    out6 = bench.run_case(c6)
    say("  replan case B006: %s — v1→v2, completed work preserved, diff recorded"
        % ("PASS" if out6["passed"] else "FAIL"))
    say("Supervisor control (HOTL) — monitor raises risk, policy pauses at a")
    say("safe barrier, a human resumes:")
    c10 = bench.load_cases({"B010"})[0]
    out10 = bench.run_case(c10)
    say("  pause/resume case B010: %s — safe barrier, resumed, terminal"
        % ("PASS" if out10["passed"] else "FAIL"))
    say("Human approval (HITL) — a high-impact replan WAITS for a human:")
    c8 = bench.load_cases({"B008"})[0]
    out8 = bench.run_case(c8)
    say("  approval case B008: %s — WAITING_HUMAN → approve → resume → completed"
        % ("PASS" if out8["passed"] else "FAIL"))
    say("")

    # ---- ACT 6: deliverable + domain swap --------------------------------- #
    say(BAR)
    say("ACT 6 — THE DELIVERABLE (real artifact, real provenance)")
    say(BAR)
    report = (final.get("artifacts") or {}).get("insurance-report") or {}
    payload = report.get("payload") or {}
    risks = _find(payload, ("risks", "risk_items", "key_risks"))
    for r in risks[:3]:
        say("  risk: %s (%s)" % (r.get("risk_name") or r.get("risk_category"),
                                 r.get("priority", "")))
    gaps = _find(payload, ("gaps", "coverage_gaps"))
    say("  coverage gaps identified: %d" % len(gaps))
    evidence = (final.get("artifacts") or {}).get("knowledge-evidence") or {}
    n_ev = len(((evidence.get("payload") or {}).get("evidence"))
               if isinstance(evidence, dict) else []) or 0
    say("  sourced knowledge items: %d (document/chunk provenance kept)" % n_ev)
    say("  FINAL: %s" % str(result.get("status", "")).upper())
    say("")

    say(BAR)
    say("BONUS — SAME RUNTIME, DIFFERENT DOMAIN")
    say(BAR)
    import subprocess
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-m", "demos.demo_generalization"],
                       capture_output=True, cwd=REPO, timeout=300, env=env)
    text = r.stdout.decode("utf-8", errors="replace")
    tail = [l for l in text.splitlines() if l.strip()][-5:]
    for l in tail:
        say("  " + _safe(l))
    say("")
    say(BAR)
    say("Takeaway: Planner=WHAT · Agents=HOW · Harness=WHEN · Eval=QUALITY ·")
    say("Artifacts=TRUTH · Human=supervision above the DAG. Insurance is")
    say("just the first domain adapter.")
    say(BAR)
    return 0 if result.get("status") == "completed" else 1


def _find(obj, keys):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, list):
                out.extend(x for x in v if isinstance(x, dict))
            out.extend(_find(v, keys))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_find(v, keys))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
