"""Script library for the deterministic benchmark (Phase 11).

Token → provider script expansion. All payloads are data (no code), so the
benchmark cases in cases/*.json stay small and declarative. Reuses the SAME
providers the Phase 7–10 acceptance tests use (TaskScriptProvider +
FakePlannerProvider): the benchmark drives the real runtime, never a mock
of it.

Tokens:
  "req"          record_requirement_analysis (valid fixture args)
  "risk"         record_risk_assessment (valid fixture args)
  "profile"      record_client_profile (valid fixture args)
  "coverage_gap" coverage_gap_analysis (deterministic engine)
  "solution"     solution (deterministic engine)
  "product"      product_candidate_provider (deterministic engine)
  "report"       report_generation (deterministic engine)
  "know"         knowledge_search (real local demo KB)
  "know:fail"    knowledge_search answers plain text → NO artifact
  "plain:<txt>"  a plain-text LLM reply (no tool call → no artifact)
"""
from __future__ import annotations

import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIXTURE = os.path.join(REPO, "tests", "e2e", "fixtures", "case-full-chain.json")

with open(FIXTURE, encoding="utf-8") as _f:
    _FIX = json.load(_f)

REQ_ARGS = {"requirements": [
    {"requirement_id": "R1", "requirement_type": "medical",
     "summary": "大额住院医疗费用保障", "priority": "P1_HIGH"}]}
RISK_ARGS = {"risks": [
    {"risk_id": "R1-001", "risk_category": "R1_medical",
     "risk_name": "住院费用风险", "priority": "P1_HIGH"}]}
PROFILE_ARGS = {
    "family_profile": {"age": {"value": 35}, "marital_status": {"value": "已婚"}},
    "financial_profile": {"annual_income": {"value": "30万"}},
    "existing_protection": {"existing_insurance": {"value": "无"}},
    "notes_for_unknown": ["health_status"]}

_TOKENS = {
    "req": [("record_requirement_analysis", REQ_ARGS), "done"],
    "risk": [("record_risk_assessment", RISK_ARGS), "done"],
    "profile": [("record_client_profile", PROFILE_ARGS), "done"],
    "coverage_gap": [("coverage_gap_analysis", {}), "done"],
    "solution": [("solution", {}), "done"],
    "product": [("product_candidate_provider", {}), "done"],
    "recommendation": [("recommendation", {}), "done"],
    "report": [("report_generation", {}), "done"],
    "know": [("knowledge_search", {"query": "百万医疗险 重疾险 区别"}), "done"],
}


def expand(token):
    """Token → a TaskScriptProvider script (list of provider replies)."""
    if token in _TOKENS:
        return copy.deepcopy(_TOKENS[token])
    if token.startswith("plain:"):
        return [token[len("plain:"):]]
    if token.startswith("know:fail"):
        return ["知识检索没有找到可用证据，无法生成证据工件。"]
    raise ValueError("unknown script token %r" % token)


def expand_scripts(scripts: dict) -> dict:
    """{"task_id": token | [token, ...]} → provider scripts dict."""
    out = {}
    for tid, tokens in (scripts or {}).items():
        tokens = tokens if isinstance(tokens, list) else [tokens]
        script = []
        for t in tokens:
            script.extend(expand(t))
        out[tid] = script
    return out


def fixture_artifact(kind: str):
    """Seeding artifacts straight from the shared e2e fixture."""
    return copy.deepcopy(_FIX["artifacts"][kind])


BAD_PRODUCT = {"candidates": [{
    "candidate_id": "C001", "product_id": "BAD_X",
    "product_name": "no-such-product", "company": "demo-company",
    "admissible": True}]}


def expand_artifact_scripts(scripts: dict) -> dict:
    """Artifact-injection mode (ScriptAgentExecutor): each task_type maps to
    a list of raw artifacts returned per successive execution. Used for
    eval-failure injection (e.g. BAD_PRODUCT x5 -> repair exhaustion)."""
    out = {}
    for tt, specs in (scripts or {}).items():
        arts = []
        for s in (specs if isinstance(specs, list) else [specs]):
            if s == "profile":
                import adapters.client_intake_adapter as _cia
                arts.append(_cia.to_canonical(fixture_artifact("client-profile")))
            elif s == "bad_product":
                arts.append(copy.deepcopy(BAD_PRODUCT))
            elif s == "good_product":
                arts.append({"candidates": [{
                    "candidate_id": "C001", "product_id": "P001",
                    "product_name": "demo-product", "company": "demo-company",
                    "admissible": True}]})
            else:
                raise ValueError("unknown artifact token %r" % s)
        out[tt] = arts
    return out
