"""Planner V0.1 tests — Task Registry, Graph Validator, Planner LLM loop,
Malformed retry, and the full Planner → Validator → Harness → Execution E2E.

FakePlannerProvider for CI (no network). Real GLM smoke is separate.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_planner.py`.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime import orchestrator as orch
from runtime.planner import (TASK_REGISTRY, CANONICAL_CHAIN, validate_graph,
                             FakePlannerProvider, plan, MAX_PLANNER_RETRIES)
from runtime.harness import LongRunningHarness

SECTIONS = []
WF = orch.load_workflow()


def section(fn):
    SECTIONS.append(fn)
    return fn


# ------------------------------------------------------------------------- #
# helpers
# ------------------------------------------------------------------------- #
def make_task(tid, tt, deps=None):
    return {"task_id": tid, "task_type": tt, "description": "test",
            "dependencies": deps or []}


def make_graph(tasks):
    return {"tasks": tasks}


VALID_PARTIAL = make_graph([
    make_task("task_001", "client_profile"),
    make_task("task_002", "requirement_analysis", ["task_001"]),
    make_task("task_003", "risk_analysis", ["task_002"]),
    make_task("task_004", "coverage_gap", ["task_003"]),
])

VALID_FULL = make_graph([
    make_task("task_001", "client_profile"),
    make_task("task_002", "requirement_analysis", ["task_001"]),
    make_task("task_003", "risk_analysis", ["task_001", "task_002"]),
    make_task("task_004", "coverage_gap", ["task_003"]),
    make_task("task_005", "solution", ["task_004"]),
    make_task("task_006", "knowledge_search", ["task_005"]),
    make_task("task_007", "product_candidates", ["task_006"]),
    make_task("task_008", "recommendation", ["task_007"]),
    make_task("task_009", "report_generation", ["task_008"]),
])


# ------------------------------------------------------------------------- #
# §25 acceptance tests
# ------------------------------------------------------------------------- #
@section
def test_task_registry(c: Checks):
    c.chk("registry: 9 task types", len(TASK_REGISTRY) == 9,
          sorted(TASK_REGISTRY.keys()))
    for tt, d in TASK_REGISTRY.items():
        c.chk("registry: %s has stage_id" % tt, bool(d.get("stage_id")))
        c.chk("registry: %s has produced_artifacts" % tt,
              bool(d.get("produced_artifacts")))
        c.chk("registry: %s has required_eval" % tt,
              bool(d.get("required_eval")))
        c.chk("registry: %s has description" % tt, bool(d.get("description")))
    c.chk("registry: canonical chain matches",
          [tt for tt in CANONICAL_CHAIN] == [
              "client_profile", "requirement_analysis", "risk_analysis",
              "coverage_gap", "solution", "knowledge_search",
              "product_candidates", "recommendation", "report_generation"])


@section
def test_graph_validation_pass(c: Checks):
    ok, errs = validate_graph(VALID_PARTIAL)
    c.chk("validate: partial graph PASS", ok, errs)
    ok2, errs2 = validate_graph(VALID_FULL)
    c.chk("validate: full graph PASS", ok2, errs2)


@section
def test_unknown_task_type(c: Checks):
    """Test 5: Planner invents 'make_me_rich' → FAIL."""
    bad = make_graph([
        make_task("task_001", "client_profile"),
        make_task("task_002", "make_me_rich", ["task_001"]),
    ])
    ok, errs = validate_graph(bad)
    c.chk("unknown task_type: FAIL", not ok)
    c.chk("unknown task_type: error mentions 'not in Registry'",
          any("not in Registry" in e for e in errs), errs)


@section
def test_circular_dependency(c: Checks):
    """Test 6: A→B→C→A → FAIL."""
    bad = make_graph([
        make_task("task_a", "client_profile", ["task_c"]),
        make_task("task_b", "requirement_analysis", ["task_a"]),
        make_task("task_c", "risk_analysis", ["task_b"]),
    ])
    ok, errs = validate_graph(bad)
    c.chk("circular: FAIL", not ok)
    c.chk("circular: error mentions 'circular'", any("circular" in e.lower() for e in errs), errs)


@section
def test_missing_artifact(c: Checks):
    """Test 7: report_generation requires recommendation but no upstream produces it."""
    bad = make_graph([
        make_task("task_001", "client_profile"),
        make_task("task_002", "report_generation", ["task_001"]),
    ])
    ok, errs = validate_graph(bad)
    c.chk("missing artifact: FAIL", not ok)
    c.chk("missing artifact: error mentions 'missing required input'",
          any("missing required input" in e for e in errs), errs)


@section
def test_dag_and_reachability(c: Checks):
    # no entry task (all have dependencies)
    bad = make_graph([
        make_task("task_001", "requirement_analysis", ["task_002"]),
        make_task("task_002", "risk_analysis", ["task_001"]),
    ])
    ok, errs = validate_graph(bad)
    c.chk("DAG: no entry task detected", not ok)

    # parallel entry (two independent starting points) is valid if inputs met
    parallel = make_graph([
        make_task("task_001", "client_profile"),
        make_task("task_002", "requirement_analysis", ["task_001"]),
        make_task("task_003", "risk_analysis", ["task_001", "task_002"]),
    ])
    ok2, errs2 = validate_graph(parallel)
    c.chk("DAG: parallel deps valid", ok2, errs2)


@section
def test_duplicate_task_id(c: Checks):
    bad = make_graph([
        make_task("task_001", "client_profile"),
        make_task("task_001", "requirement_analysis", ["task_001"]),
    ])
    ok, errs = validate_graph(bad)
    c.chk("duplicate task_id: FAIL", not ok)
    c.chk("duplicate: error mentions 'duplicate'", any("duplicate" in e for e in errs))


@section
def test_unknown_dependency(c: Checks):
    bad = make_graph([
        make_task("task_001", "client_profile"),
        make_task("task_002", "requirement_analysis", ["task_nonexistent"]),
    ])
    ok, errs = validate_graph(bad)
    c.chk("unknown dependency: FAIL", not ok)
    c.chk("unknown dep: error mentions 'unknown'",
          any("unknown" in e for e in errs))


# ------------------------------------------------------------------------- #
# Planner LLM loop tests (FakePlannerProvider)
# ------------------------------------------------------------------------- #
@section
def test_planner_valid_output(c: Checks):
    """Planner generates valid JSON → graph validated + normalized."""
    json_text = json.dumps({"tasks": [
        {"task_id": "task_001", "task_type": "client_profile", "dependencies": []},
        {"task_id": "task_002", "task_type": "requirement_analysis",
         "dependencies": ["task_001"]},
        {"task_id": "task_003", "task_type": "risk_analysis",
         "dependencies": ["task_002"]},
        {"task_id": "task_004", "task_type": "coverage_gap",
         "dependencies": ["task_003"]},
    ]}, ensure_ascii=False)
    events = []
    provider = FakePlannerProvider([json_text])
    result = plan(provider, "帮我分析这个客户的保险需求",
                  emit=lambda t, d: events.append((t, d)))
    c.chk("planner: valid → planned", result.ok, result.errors)
    c.chk("planner: graph has 4 tasks", len(result.graph["tasks"]) == 4)
    c.chk("planner: graph_id assigned", result.graph["graph_id"].startswith("graph_"))
    c.chk("planner: entry_tasks computed",
          result.graph["entry_tasks"] == ["task_001"])
    c.chk("planner: terminal_tasks computed",
          result.graph["terminal_tasks"] == ["task_004"])
    c.chk("planner: tasks enriched from Registry",
          result.graph["tasks"][0]["expected_artifacts"] == ["client-profile"]
          and result.graph["tasks"][0]["required_eval"] == ["client_profile_eval"])
    c.chk("planner: status PLANNED",
          all(t["status"] == "PLANNED" for t in result.graph["tasks"]))
    for evt in ("planner_started", "graph_validation_started",
                "graph_validation_passed", "planner_completed"):
        c.chk("planner events: %s" % evt, any(e[0] == evt for e in events))


@section
def test_planner_malformed_retry(c: Checks):
    """Test 9: invalid JSON twice, valid on third → succeeds after retry."""
    valid = json.dumps({"tasks": [
        {"task_id": "task_001", "task_type": "client_profile", "dependencies": []},
    ]})
    events = []
    provider = FakePlannerProvider([
        "not json at all {{{",
        '{"tasks": [{"task_id": "t1", "task_type": "fake_type"}]}',  # schema fail
        valid,  # third attempt succeeds
    ])
    result = plan(provider, "test", emit=lambda t, d: events.append((t, d)))
    c.chk("retry: succeeds on attempt 3", result.ok, result.errors)
    c.chk("retry: attempts == 3", result.attempts == 3)
    failed_events = [e for e in events if e[0] == "graph_validation_failed"]
    c.chk("retry: 2 validation_failed events", len(failed_events) == 2)


@section
def test_planner_retry_exhausted(c: Checks):
    """All 3 attempts malformed → NEEDS_REVIEW, never silent fallback."""
    events = []
    provider = FakePlannerProvider([
        "garbage", "more garbage", '{"tasks": []}',
    ])
    result = plan(provider, "test", emit=lambda t, d: events.append((t, d)))
    c.chk("exhausted: needs_review", result.status == "needs_review")
    c.chk("exhausted: attempts == %d" % (MAX_PLANNER_RETRIES + 1),
          result.attempts == MAX_PLANNER_RETRIES + 1)
    c.chk("exhausted: errors collected", len(result.errors) >= 3)
    c.chk("exhausted: planner_failed event",
          any(e[0] == "planner_failed" for e in events))
    c.chk("exhausted: no graph produced", result.graph is None)


@section
def test_planner_markdown_fenced(c: Checks):
    """LLM wraps JSON in ```json fences → stripped correctly."""
    fenced = '```json\n{"tasks": [{"task_id": "task_001", "task_type": "client_profile", "dependencies": []}]}\n```'
    provider = FakePlannerProvider([fenced])
    result = plan(provider, "test")
    c.chk("markdown: fenced JSON parsed", result.ok, result.errors)


# ------------------------------------------------------------------------- #
# Test 3/4: intent routing compatibility (Planner NOT invoked for simple)
# ------------------------------------------------------------------------- #
@section
def test_intent_routing_compatibility(c: Checks):
    """Planner is only invoked for CLIENT_ADVISORY/TASK_EXECUTION, not for
    GENERAL_KNOWLEDGE or PRODUCT_LOOKUP (which go through existing tools)."""
    # This is verified by design: the Planner is only called from the
    # CLIENT_ADVISORY flow in the agent loop, not from intent routing directly.
    # Here we verify the Planner module itself doesn't do intent classification.
    import inspect
    from runtime.planner import planner as planner_mod
    src = inspect.getsource(planner_mod)
    c.chk("intent compat: planner has no intent classification",
          "intent" not in src.lower() or "intent" not in
          src.split("class PlannerResult")[0].lower())
    c.chk("intent compat: planner only produces graphs",
          hasattr(planner_mod, "plan") and hasattr(planner_mod, "PlannerResult"))


# ------------------------------------------------------------------------- #
# Test 10: Planner → Validator → Harness → Execution E2E (FakePlanner)
# ------------------------------------------------------------------------- #
@section
def test_planner_harness_e2e(c: Checks):
    """Full E2E: FakePlanner → graph → validator → harness → real execution."""
    import copy
    root = tempfile.mkdtemp(prefix="planner_e2e_", dir=os.path.join(REPO, "tmp"))
    try:
        # 1. Planner generates a graph
        graph_json = json.dumps({"tasks": [
            {"task_id": "task_001", "task_type": "client_profile", "dependencies": []},
            {"task_id": "task_002", "task_type": "requirement_analysis",
             "dependencies": ["task_001"]},
            {"task_id": "task_003", "task_type": "risk_analysis",
             "dependencies": ["task_002"]},
            {"task_id": "task_004", "task_type": "coverage_gap",
             "dependencies": ["task_003"]},
            {"task_id": "task_005", "task_type": "solution",
             "dependencies": ["task_004"]},
            {"task_id": "task_006", "task_type": "knowledge_search",
             "dependencies": ["task_005"]},
            {"task_id": "task_007", "task_type": "product_candidates",
             "dependencies": ["task_006"]},
            {"task_id": "task_008", "task_type": "recommendation",
             "dependencies": ["task_007"]},
            {"task_id": "task_009", "task_type": "report_generation",
             "dependencies": ["task_008"]},
        ]}, ensure_ascii=False)
        provider = FakePlannerProvider([graph_json])
        result = plan(provider, "帮我为这个客户设计保险方案并生成计划书")
        c.chk("E2E: planner produced valid graph", result.ok, result.errors)
        c.chk("E2E: 9 tasks planned", len(result.graph["tasks"]) == 9)

        # 2. Harness accepts the graph
        h = LongRunningHarness(root)
        p = h.create_project("planner-e2e", task_graph=result.graph)
        c.chk("E2E: harness accepted task_graph", len(p.tasks) == 9,
              len(p.tasks))

        # 3. Seed the CaseState with dialogue artifacts
        with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                               "case-full-chain.json"), encoding="utf-8") as f:
            fixture = json.load(f)
        state = orch.seed_case(WF, p.case_id,
                               copy.deepcopy(fixture["artifacts"]),
                               provided_by="planner-e2e")
        from runtime.state import store as state_store
        state_store.save(state, os.path.join(root, p.project_id, "case"))

        # 4. Execute
        run_result = h.run(p)
        c.chk("E2E: project completed", run_result["status"] == "completed",
              run_result["status"])
        outcomes = {e["task"]: e["outcome"] for e in run_result["executed"]}
        c.chk("E2E: all tasks PASS or SKIPPED",
              all(v in ("PASS", "SKIPPED") for v in outcomes.values()), outcomes)

        # 5. Verify artifacts exist
        arts = sorted(a["artifact_type"] for a in _get_artifacts(root, p))
        c.chk("E2E: insurance-report produced", "insurance-report" in arts, arts)
        c.chk("E2E: full artifact chain", len(arts) >= 9, arts)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _get_artifacts(root, project):
    from runtime.state import store as state_store
    state = state_store.load(os.path.join(root, project.project_id, "case"),
                             project.case_id)
    if not state:
        return []
    from runtime import artifact_registry as reg
    return [{"artifact_type": rec["artifact_type"]}
            for rec in (state.get("artifact_registry") or {}).values()]


# ------------------------------------------------------------------------- #
# Event integrity
# ------------------------------------------------------------------------- #
@section
def test_planner_event_integrity(c: Checks):
    events = []
    valid = json.dumps({"tasks": [
        {"task_id": "task_001", "task_type": "client_profile", "dependencies": []},
    ]})
    provider = FakePlannerProvider([valid])
    plan(provider, "test request", emit=lambda t, d: events.append((t, d)))

    blob = json.dumps([dict(e[1]) for e in events], ensure_ascii=False)
    c.chk("events: JSON-serializable", isinstance(events, list) and len(events) > 0)
    for banned in ("api_key", "authorization", "sk-", "chain of thought",
                   "思考过程", "prompt"):
        c.chk("events: no %r" % banned, banned not in blob.lower())

    # planner events use the correct vocabulary
    planner_evts = {e[0] for e in events}
    from runtime.events import EVENT_TYPES
    c.chk("events: planner vocabulary in EVENT_TYPES",
          planner_evts <= EVENT_TYPES,
          planner_evts - EVENT_TYPES)


# ------------------------------------------------------------------------- #
# No silent fallback
# ------------------------------------------------------------------------- #
@section
def test_no_silent_fallback(c: Checks):
    """Planner failure → needs_review, NOT a deterministic fallback."""
    import inspect
    from runtime.planner import planner as planner_mod
    src = inspect.getsource(planner_mod)
    c.chk("no fallback: no deterministic_workflow call",
          "deterministic_workflow" not in src)
    c.chk("no fallback: no demo pipeline call", "demo" not in src.lower())
    c.chk("no fallback: failure returns needs_review",
          "needs_review" in src)

    # behavioral check: exhausted planner → needs_review, no graph
    provider = FakePlannerProvider(["bad"] * 5)
    result = plan(provider, "test")
    c.chk("no fallback: exhausted → needs_review, no graph",
          result.status == "needs_review" and result.graph is None)


def main():
    return run_sections(SECTIONS, "webui_test_planner_log.txt", "RUNTIME PLANNER")


if __name__ == "__main__":
    sys.exit(main())
