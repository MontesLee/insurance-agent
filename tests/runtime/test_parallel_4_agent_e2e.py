"""Phase 7 — True Parallel 4-Agent Runtime E2E (§25 / T22).

DAG (max_concurrency=2):

    requirement_analysis (insurance_analyst)
                │
        ┌───────┴───────┐
        ▼               ▼
  risk_analysis   knowledge_search      ← MUST truly overlap
  (insurance_     (knowledge_
   analyst)        specialist)
        │               │
        ▼               │
   coverage_gap         │
        │               │
        ▼               │
     solution           │
        │               │
        └───────┬───────┘
                ▼
      product_candidates (product_specialist)   ← waits for BOTH branches
                │
                ▼
      report_generation (report_specialist)

All four specialist agents execute through the REAL SpecialistAgentExecutor
with a per-task scripted provider; overlap is PROVED by a blocking probe
inside the LLM loop (not inferred from event order).

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_parallel_4_agent_e2e.py`.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from test_parallel_scheduler import (OverlapProbe, TaskScriptProvider,  # noqa: E402
                                     make_project, load_state, cleanup)
from runtime import artifact_registry as reg
from runtime import checkpoint as cp
from runtime.state import case_state as cs

SECTIONS = []

RISK_ARGS = {"risks": [
    {"risk_id": "R1-001", "risk_category": "R1_medical",
     "risk_name": "住院费用风险", "priority": "P1_HIGH"},
    {"risk_id": "R2-001", "risk_category": "R2_critical_illness",
     "risk_name": "重疾风险", "priority": "P1_HIGH"}]}
REQ_ARGS = {"requirements": [
    {"requirement_id": "R1", "requirement_type": "medical",
     "summary": "大额住院医疗费用保障", "priority": "P1_HIGH"},
    {"requirement_id": "R2", "requirement_type": "critical_illness",
     "summary": "重大疾病保障", "priority": "P1_HIGH"}]}

GRAPH = {"tasks": [
    {"task_id": "task_1", "task_type": "requirement_analysis"},
    {"task_id": "task_2", "task_type": "risk_analysis",
     "dependencies": ["task_1"]},
    {"task_id": "task_3", "task_type": "knowledge_search",
     "dependencies": ["task_1"]},
    {"task_id": "task_4", "task_type": "coverage_gap",
     "dependencies": ["task_2"]},
    {"task_id": "task_5", "task_type": "solution",
     "dependencies": ["task_4"]},
    {"task_id": "task_6", "task_type": "product_candidates",
     "dependencies": ["task_2", "task_3", "task_5"]},
    {"task_id": "task_7", "task_type": "report_generation",
     "dependencies": ["task_6"]},
]}

SCRIPTS = {
    "task_1": [("record_requirement_analysis", REQ_ARGS), "Requirements recorded."],
    "task_2": [("record_risk_assessment", RISK_ARGS), "Risks recorded."],
    "task_3": [("knowledge_search", {"query": "百万医疗险 重疾险 区别"}),
               "Evidence retrieved."],
    "task_4": [("coverage_gap_analysis", {}), "Coverage gap analyzed."],
    "task_5": [("solution", {}), "Solution designed."],
    "task_6": [("product_candidate_provider", {}), "Candidates selected."],
    "task_7": [("report_generation", {}), "Report generated."],
}

EXPECTED_ARTIFACTS = [
    "client-profile",               # seeded
    "requirement-analysis",         # task_1
    "risk-assessment",              # task_2
    "knowledge-evidence",           # task_3
    "coverage-gap-analysis",        # task_4
    "solution-plan",                # task_5
    "product-candidates",           # task_6
    "insurance-report",             # task_7
]


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="par4_", dir=os.path.join(REPO, "tmp"))


@section
def test_t22_parallel_4_agent_e2e(c: Checks):
    """THE Phase 7 acceptance E2E: bounded parallel DAG, 4 real agents,
    overlap proven, barrier enforced, project COMPLETED."""
    d = fresh_dir()
    try:
        with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                               "case-full-chain.json"), encoding="utf-8") as f:
            fx = json.load(f)
        probe = OverlapProbe(need=2, watch={"task_2", "task_3"})
        provider = TaskScriptProvider(copy.deepcopy(SCRIPTS), probe=probe)
        h, p = make_project(d, GRAPH, seeds={"client-profile": fx["artifacts"]["client-profile"]},
                            agent_executor=provider, max_concurrency=2)
        result = h.run(p)

        # ---- project outcome ------------------------------------------------ #
        c.chk("E2E: project COMPLETED", result["status"] == "completed",
              result["status"])
        statuses = {t["task_id"]: t["status"] for t in p.tasks}
        c.chk("E2E: all 7 tasks PASSED",
              all(v == "PASSED" for v in statuses.values()), statuses)

        # ---- true parallelism: risk_analysis ∥ knowledge_search ------------- #
        c.chk("E2E: risk_analysis and knowledge_search truly overlapped "
              "(inside the LLM loop)", probe.overlapped, probe.log)
        c.chk("E2E: scheduler never exceeded max_concurrency=2",
              probe.max_active <= 2, probe.max_active)

        # ---- dependency barrier: product waited for BOTH branches ----------- #
        c.chk("E2E: product_candidates started after risk branch finished",
              probe.index_of("enter", "task_6") > probe.index_of("exit", "task_2"),
              probe.log)
        c.chk("E2E: product_candidates started after knowledge branch finished",
              probe.index_of("enter", "task_6") > probe.index_of("exit", "task_3"),
              probe.log)

        # ---- all 4 specialist agents really executed ------------------------- #
        evs = p.events()
        started_agents = {e.get("agent_id") for e in evs
                          if e["event_type"] == "agent_started"}
        c.chk("E2E: 4 specialist agents started",
              started_agents == {"insurance_analyst", "knowledge_specialist",
                                 "product_specialist", "report_specialist"},
              started_agents)
        tool_calls = [e for e in evs if e["event_type"] == "agent_tool_call"]
        c.chk("E2E: ≥7 agent tool calls replayed into project events",
              len(tool_calls) >= 7, len(tool_calls))

        # ---- artifact chain from real execution ------------------------------ #
        final = load_state(d, p) or {}
        art_types = sorted((final.get("artifacts") or {}).keys())
        c.chk("E2E: full artifact chain produced",
              art_types == sorted(EXPECTED_ARTIFACTS), art_types)
        ids = [rec["artifact_id"] for rec in
               (final.get("artifact_registry") or {}).values()]
        c.chk("E2E: artifact_ids unique", len(ids) == len(set(ids)), ids)

        # ---- eval chain (Harness-owned, one per agent artifact) -------------- #
        evals = final.get("evaluations") or []
        passed = [e for e in evals if e["status"] == "PASS"]
        c.chk("E2E: ≥8 PASS evals (seed + 7 agent artifacts)",
              len(passed) >= 8, [(e["eval_id"], e["artifact_type"], e["status"])
                                 for e in evals])
        ok, problems = reg.verify(final)
        c.chk("E2E: artifact registry verifies", ok, problems[:3])
        ok, errs = cs.validate(final)
        c.chk("E2E: CaseState schema valid", ok, errs[:3])
        ok, problems = cp.validate(final, p.case_id)
        c.chk("E2E: final state checkpoint-validates", ok, problems[:3])

        # ---- checkpoints per terminal task ----------------------------------- #
        ck = [e for e in evs if e["event_type"] == "checkpoint_created"]
        c.chk("E2E: checkpoint per terminal task (7+)", len(ck) >= 7, len(ck))
    finally:
        cleanup(d)


@section
def test_t22_sequential_equivalence(c: Checks):
    """The SAME graph/script under max_concurrency=1 (Phase 6 path) reaches
    the same terminal state — parallelism changes scheduling, not outcomes."""
    d = fresh_dir()
    try:
        with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                               "case-full-chain.json"), encoding="utf-8") as f:
            fx = json.load(f)
        provider = TaskScriptProvider(copy.deepcopy(SCRIPTS))
        h, p = make_project(d, GRAPH, seeds={"client-profile": fx["artifacts"]["client-profile"]},
                            agent_executor=provider, max_concurrency=1)
        result = h.run(p)
        c.chk("SEQ: sequential run of the same DAG COMPLETED",
              result["status"] == "completed", result["status"])
        statuses = {t["task_id"]: t["status"] for t in p.tasks}
        c.chk("SEQ: all tasks PASSED",
              all(v == "PASSED" for v in statuses.values()), statuses)
        final = load_state(d, p) or {}
        art_types = sorted((final.get("artifacts") or {}).keys())
        c.chk("SEQ: same artifact chain as the parallel run",
              art_types == sorted(EXPECTED_ARTIFACTS), art_types)
    finally:
        cleanup(d)


def main():
    return run_sections(SECTIONS, "webui_test_parallel_e2e_log.txt",
                        "RUNTIME PARALLEL 4-AGENT E2E")


if __name__ == "__main__":
    sys.exit(main())
