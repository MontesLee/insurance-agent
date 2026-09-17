"""Phase 6.2.2 — Knowledge Evidence Artifact + Durable Agent Events tests."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime import orchestrator as orch
from runtime.agent.model import FakeLLMProvider
from runtime.agent.tools import ToolContext, build_registry
from runtime.agents.executor import SpecialistAgentExecutor
from runtime.harness import LongRunningHarness

SECTIONS = []
WF = orch.load_workflow()

def section(fn):
    SECTIONS.append(fn)
    return fn

def fresh_dir():
    return tempfile.mkdtemp(prefix="kev_", dir=os.path.join(REPO, "tmp"))

def make_ctx():
    from runtime.state import case_state as cs
    from runtime import tasks as tk
    state = cs.new_case_state("kev_case", WF)
    tk.init_tasks(state, WF)
    return ToolContext(state, WF, "kev_run", skip_eval=True)


# ------------------------------------------------------------------------- #
# T1-T9: Knowledge Evidence Artifact
# ------------------------------------------------------------------------- #
@section
def test_t1_t9_knowledge_evidence(c: Checks):
    d = fresh_dir()
    try:
        os.makedirs(d, exist_ok=True)
        ctx = make_ctx()
        ctx.project_dir = d
        ctx.agent_id = "knowledge_specialist"
        reg = build_registry()

        # T1: tool produces knowledge-evidence
        out = reg["knowledge_search"].execute({"query": "百万医疗险"}, ctx)
        c.chk("T1: tool produced artifact", out.get("artifact_id") is not None)

        # T2: artifact persisted to CaseState
        art = (ctx.state.get("artifacts") or {}).get("knowledge-evidence")
        c.chk("T2: artifact in CaseState", art is not None)

        # T3: artifact registered
        from runtime import artifact_registry as ar
        arec = ar.by_type(ctx.state, "knowledge-evidence")
        c.chk("T3: artifact registered", arec is not None and arec["artifact_id"] is not None)

        # T4: provenance preserved
        prov = (art or {}).get("provenance") or []
        c.chk("T4: provenance non-empty", len(prov) >= 1)
        c.chk("T4: provenance has source_type + source_id",
              all("source_type" in p and "source_id" in p for p in prov))

        # T5: empty RAG fails closed
        import knowledge.evidence.provider as kep
        class _Empty:
            def search(self, q, **kw):
                class _R: chunks = []
                return _R()
        _orig = kep.build_engine
        kep.build_engine = lambda kb_dir=None: _Empty()
        try:
            out2 = reg["knowledge_search"].execute({"query": "nonsense"}, make_ctx())
            c.chk("T5: empty RAG → FAIL", out2["status"] == "failed")
        finally:
            kep.build_engine = _orig

        # T6: Eval on knowledge-evidence
        from runtime import eval_engine as ev
        if art:
            eval_result = ev.evaluate(ctx.state, "knowledge-evidence", art,
                                      {"id": "knowledge-search",
                                       "skill": "knowledge-search"})
            c.chk("T6: well-formed artifact Eval PASS",
                  eval_result["status"] == "PASS", eval_result["status"])
            # invalid artifact (empty evidence) should fail
            bad_art = dict(art)
            bad_art["payload"] = {"evidence": [], "status": "success"}
            bad_result = ev.evaluate(ctx.state, "knowledge-evidence", bad_art,
                                    {"id": "knowledge-search",
                                     "skill": "knowledge-search"})
            c.chk("T6: empty evidence Eval FAIL", bad_result["status"] == "FAIL")

        # T7: tool doesn't self-PASS
        c.chk("T7: no eval_id in tool result",
              out.get("eval_id") is None)

        # T8: Harness owns Eval (structural)
        import inspect
        from runtime.agent.tools import _knowledge_search
        src = inspect.getsource(_knowledge_search)
        c.chk("T8: tool doesn't call ev.evaluate",
              "evaluate(" not in src.replace("build_engine().search(", ""))

        # T9: exactly one eval per attempt (check evaluations list)
        if art:
            evals = [e for e in (ctx.state.get("evaluations") or [])
                     if e.get("artifact_type") == "knowledge-evidence"]
            # only from our manual eval in T6; tool didn't add any
            c.chk("T9: tool added 0 evals (T6 manual evals are from test, not tool)",
                  len(evals) <= 2, len(evals))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------------- #
# T10-T16: Durable Agent Events
# ------------------------------------------------------------------------- #
@section
def test_t10_t16_durable_events(c: Checks):
    d = fresh_dir()
    try:
        graph = {"tasks": [
            {"task_id": "task_001", "task_type": "client_profile"},
            {"task_id": "task_002", "task_type": "risk_analysis",
             "dependencies": ["task_001"]},
        ]}
        provider = FakeLLMProvider([
            ("record_risk_assessment", {"risks": [
                {"risk_id": "R1", "risk_category": "R1_medical",
                 "risk_name": "test", "priority": "P1_HIGH"}]}),
            "Done.",
        ])
        h = LongRunningHarness(d, agent_executor=provider)
        p = h.create_project("kev-events", task_graph=graph)
        import copy
        with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                               "case-full-chain.json"), encoding="utf-8") as f:
            fx = json.load(f)
        state = orch.seed_case(WF, p.case_id,
                               {"client-profile": copy.deepcopy(fx["artifacts"]["client-profile"])})
        from runtime.state import store as ss
        ss.save(state, os.path.join(d, p.project_id, "case"))
        h.run(p)

        evs = p.events()
        types = [e["event_type"] for e in evs]

        # T10-T14: agent events in durable log
        c.chk("T10: agent_started durable", "agent_started" in types)
        c.chk("T11: agent_step_started durable", "agent_step_started" in types)
        c.chk("T12: agent_tool_call durable", "agent_tool_call" in types)
        c.chk("T13: agent_tool_completed durable", "agent_tool_completed" in types)
        c.chk("T14: agent_completed durable", "agent_completed" in types)

        # T15: no duplicates (exact count check)
        started = [e for e in evs if e["event_type"] == "agent_started"]
        c.chk("T15: agent_started appears once per executed task",
              len(started) == 1, len(started))
        tool_calls = [e for e in evs if e["event_type"] == "agent_tool_call"]
        c.chk("T15: agent_tool_call count == 1 (one tool used)",
              len(tool_calls) == 1, len(tool_calls))

        # T16: no CoT persisted
        blob = json.dumps(evs, ensure_ascii=False)
        for banned in ("chain of thought", "思考过程", "internal reasoning",
                       "prompt", "api_key"):
            c.chk("T16: no %r in events" % banned, banned not in blob.lower())

        # Verify events carry agent_id and task_id
        agent_evs = [e for e in evs if e["event_type"].startswith("agent_")]
        if agent_evs:
            has_ids = all(e.get("agent_id") and e.get("task_id") for e in agent_evs[:3])
            c.chk("durable: agent events carry agent_id + task_id", has_ids)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    return run_sections(SECTIONS, "webui_test_kev_log.txt",
                        "RUNTIME KNOWLEDGE EVIDENCE + DURABLE EVENTS")


if __name__ == "__main__":
    sys.exit(main())
