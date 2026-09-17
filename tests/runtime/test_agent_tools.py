"""Phase 2.6 — Agent tool layer tests (runtime/agent/tools.py).

Real machinery, FakeLLM-free: dialogue tools store+eval through the EXISTING
adapters/CaseState/registry/eval engine; stage tools execute the EXISTING
deterministic engines (with their eval+repair); knowledge/catalog tools hit the
real KB and catalog.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_agent_tools.py`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime import orchestrator as orch  # noqa: E402
from runtime.state import case_state as cs  # noqa: E402
from runtime import tasks as tk  # noqa: E402
from runtime.agent.tools import (ToolContext, build_registry,  # noqa: E402
                                 validate_arguments)

SECTIONS = []

def section(fn):
    SECTIONS.append(fn)
    return fn
WF = orch.load_workflow()


def fresh_ctx():
    state = cs.new_case_state("agentcase-tools", WF)
    tk.init_tasks(state, WF)
    return ToolContext(state, WF, "run_tools", persist=lambda: None)


PROFILE_ARGS = {
    "family_profile": {"age": {"value": 4}, "marital_status": {"value": "已婚"}},
    "financial_profile": {"annual_income": {"value": "30万"}},
    "existing_protection": {"existing_insurance": {"value": "无"}},
    "notes_for_unknown": ["health_status"],
}


def seed_dialogue_artifacts(ctx):
    reg = build_registry()
    reg["record_client_profile"].execute(PROFILE_ARGS, ctx)
    reg["record_requirement_analysis"].execute({"requirements": [
        {"requirement_id": "REQ-MED", "requirement_type": "medical",
         "summary": "大额住院医疗", "priority": "P1_HIGH"}]}, ctx)
    reg["record_risk_assessment"].execute({"risks": [
        {"risk_id": "R1-001", "risk_category": "R1_medical",
         "risk_name": "住院费用风险", "priority": "P1_HIGH"}]}, ctx)


@section
def test_registry_and_validation(c: Checks):
    reg = build_registry()
    expected = {"record_client_profile", "record_requirement_analysis",
                "record_risk_assessment", "coverage_gap_analysis", "solution",
                "product_candidate_provider", "recommendation", "report_generation",
                "knowledge_search", "check_catalog_product"}
    c.chk("registry: all §8 tools present", expected <= set(reg), sorted(expected - set(reg)))
    c.chk("registry: every tool has schema+executor",
          all(t.parameters.get("type") == "object" and t._execute for t in reg.values()))

    bad = validate_arguments(reg["record_requirement_analysis"], {"requirements": []})
    c.chk("validation: empty requirements rejected (minItems)", bad is not None, bad)
    bad2 = validate_arguments(reg["record_risk_assessment"],
                              {"risks": [{"risk_id": "x"}]})
    c.chk("validation: missing required risk fields rejected", bad2 is not None)
    ok = validate_arguments(reg["record_requirement_analysis"], {"requirements": [
        {"requirement_id": "R", "requirement_type": "medical", "summary": "s",
         "priority": "P1_HIGH"}]})
    c.chk("validation: well-formed args pass", ok is None)


@section
def test_record_client_profile_stores_and_evals(c: Checks):
    ctx = fresh_ctx()
    out = build_registry()["record_client_profile"].execute(PROFILE_ARGS, ctx)
    state = ctx.state
    c.chk("profile: stored + eval PASS", out["status"] == "completed", out)
    c.chk("profile: canonical envelope in CaseState",
          "client-profile" in state["artifacts"]
          and "artifact_type" in state["artifacts"]["client-profile"])
    leaf = state["artifacts"]["client-profile"]["payload"]["family_profile"]["age"]
    c.chk("profile: user-stated leaf carries conversation provenance",
          leaf["source"] == "conversation:user_message" and leaf["status"] == "KNOWN", leaf)
    c.chk("profile: unknowns recorded for follow-up",
          any(m.get("field") == "health_status"
              for m in state["artifacts"]["client-profile"]["payload"]["missing_from_upstream"]))
    c.chk("profile: eval appended by the EXISTING engine",
          any(e["artifact_type"] == "client-profile" for e in state["evaluations"]))
    c.chk("profile: registry has lineage record",
          state["artifact_registry"]["client-profile"]["artifact_id"].startswith("ART-"))

    # refinement while nothing downstream consumed it is allowed
    out2 = build_registry()["record_client_profile"].execute(
        {**PROFILE_ARGS, "financial_profile": {"annual_income": {"value": "35万"}}}, ctx)
    c.chk("profile: dialogue refinement allowed pre-downstream",
          out2["status"] == "completed", out2)


@section
def test_stage_tool_preconditions_and_execution(c: Checks):
    reg = build_registry()
    ctx = fresh_ctx()

    out = reg["coverage_gap_analysis"].execute({}, ctx)
    c.chk("stage tool: refuses to run without prerequisites",
          out["status"] == "failed" and "client-profile" in out["summary"], out)

    seed_dialogue_artifacts(ctx)
    out = reg["coverage_gap_analysis"].execute({}, ctx)
    c.chk("stage tool: existing engine runs after facts recorded",
          out["status"] == "completed" and out.get("artifact_type") == "coverage-gap-analysis",
          out)
    c.chk("stage tool: existing eval gate applied",
          any(e["artifact_type"] == "coverage-gap-analysis"
              and e["status"] == "PASS" for e in ctx.state["evaluations"]))

    # freeze discipline: once downstream started, dialogue facts are frozen
    frozen = reg["record_client_profile"].execute(PROFILE_ARGS, ctx)
    c.chk("freeze: dialogue facts locked after downstream starts",
          frozen["status"] == "failed" and "frozen" in frozen["summary"], frozen)


@section
def test_knowledge_and_catalog_tools(c: Checks):
    reg = build_registry()
    ctx = fresh_ctx()

    out = reg["knowledge_search"].execute({"query": "百万医疗险 免赔额"}, ctx)
    c.chk("knowledge: real KB query returns structured evidence",
          out["status"] == "completed"
          and isinstance(out["data"].get("evidence"), list), out.get("summary"))
    if out["data"].get("evidence"):
        c.chk("knowledge: evidence carries document provenance",
              all("document_id" in e for e in out["data"]["evidence"]))

    # the demo KB is tiny and lenient — prove the honest-empty contract against
    # an EMPTY KB (the same one the benchmark uses for the no-evidence case)
    import knowledge.evidence.provider as kep

    class _EmptyEngine:
        def search(self, query, **kw):
            class _R:
                chunks = []
            return _R()

    _orig_build = kep.build_engine
    kep.build_engine = lambda kb_dir=None: _EmptyEngine()
    try:
        out = reg["knowledge_search"].execute({"query": "任意查询"}, ctx)
    finally:
        kep.build_engine = _orig_build
    c.chk("knowledge: empty KB → honest not-found note (no fabrication)",
          out["status"] == "completed" and out["data"].get("evidence") == []
          and "没有找到" in out["data"].get("note", ""), out["data"].get("note"))

    hit = reg["check_catalog_product"].execute({"query": "P001"}, ctx)
    c.chk("catalog: existing demo product found",
          hit["status"] == "completed" and len(hit["data"]["products"]) >= 1, hit["data"])
    miss = reg["check_catalog_product"].execute({"query": "ABC不存在的产品"}, ctx)
    c.chk("catalog: unknown product → explicit not-found wording",
          miss["data"]["products"] == []
          and "没有找到该产品" in miss["data"].get("note", ""), miss["data"])



def main():
    return run_sections(SECTIONS, "webui_test_agent_tools_log.txt", "RUNTIME AGENT TOOLS")


if __name__ == "__main__":
    sys.exit(main())
