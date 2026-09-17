"""Agent tool layer (Phase 2.6) — the Agent-facing interface to existing Skills.

> Tool 是 Skill 的 Agent-facing interface。（spec §55）

Every tool returns a STRUCTURED result {status, artifact_id?, eval_id?, summary,
data} — never free text as the only output (§9). Dialogue-skill tools
(record_client_profile / record_requirement_analysis / record_risk_assessment)
reuse the EXISTING adapters + CaseState + artifact registry + Eval engine.
Deterministic stage tools execute the EXISTING workflow stages through
`orchestrator._execute_stage`, which carries the existing Eval + Repair loop
(§20/§21 — the LLM can never override an eval verdict).
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Optional

from runtime import orchestrator as orch
from runtime import artifact_registry as reg
from runtime import eval_engine as ev
from runtime import tasks as tk
from runtime import trace as tr
from runtime.state import case_state as cs
from runtime.agent import schemas as S

import adapters.client_intake_adapter as cia
import adapters.requirement_analysis_adapter as raa
import adapters.risk_analysis_adapter as rka

STAGE_ID_OF = {
    "coverage_gap_analysis": "coverage-gap-analysis",
    "solution": "solution",
    "product_candidate_provider": "product-candidate-provider",
    "recommendation": "product-recommendation",
    "report_generation": "report-generation",
}
ARTIFACT_OF = {
    "coverage-gap-analysis": "coverage-gap-analysis",
    "solution": "solution-plan",
    "product-candidate-provider": "product-candidates",
    "product-recommendation": "product-recommendation",
    "report-generation": "insurance-report",
}
USER_SOURCE = "conversation:user_message"

# artifacts a dialogue record_* may still replace (nothing downstream consumed
# them yet); once any downstream artifact exists the freeze discipline applies
DOWNSTREAM_TYPES = ["coverage-gap-analysis", "solution-plan", "product-candidates",
                    "product-recommendation", "insurance-report"]


class ToolContext:
    """Run-scoped dependencies handed to every tool execution."""

    def __init__(self, state: dict, workflow: dict, run_id: str,
                 persist: Optional[Callable[[], None]] = None,
                 skip_eval: bool = False):
        self.state = state
        self.workflow = workflow
        self.run_id = run_id
        self.persist = persist or (lambda: None)
        # Phase 5.2: when True, dialogue tools store artifacts WITHOUT running
        # eval — the caller (Harness) owns the eval boundary
        self.skip_eval = skip_eval


class Tool:
    def __init__(self, name: str, description: str, parameters: dict,
                 execute: Callable[[dict, ToolContext], dict]):
        self.name = name
        self.description = description
        self.parameters = parameters
        self._execute = execute

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description,
                "parameters": self.parameters}

    def execute(self, args: dict, ctx: ToolContext) -> dict:
        try:
            return self._execute(args or {}, ctx)
        except Exception as e:  # noqa: BLE001 — tool errors fail closed, structured
            return {"status": "failed", "summary": "tool error: %r" % e,
                    "data": {"error_type": type(e).__name__}}


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def _ok(summary: str, **kw) -> dict:
    out = {"status": "completed", "summary": summary, "data": {}}
    out.update(kw)
    return out


def _fail(summary: str, **kw) -> dict:
    out = {"status": "failed", "summary": summary, "data": {}}
    out.update(kw)
    return out


def _validate_contract(artifact: dict, contract: str) -> Optional[str]:
    ok, errs = orch.validate_artifact(artifact, contract)
    return None if ok else "; ".join(errs[:3])


def _store_dialogue_artifact(ctx: ToolContext, art_type: str, native: dict,
                             adapter, skill: str, stage_id: str,
                             contract: str) -> dict:
    """Validate → store → register → EVAL a dialogue-provided artifact.

    Mirrors seed_case's discipline for provided artifacts, reusing the same
    cs/reg/ev components — the LLM only supplied candidate facts, the canonical
    machinery stays deterministic.
    """
    state = ctx.state
    # emit the START of the dialogue skill so the pipeline shows it RUNNING
    # (SKILL_STARTED maps to stage_started in the event stream)
    rec = state["stages"][stage_id]
    tk.begin_attempt(state, stage_id)
    tk.set_status(state, stage_id, "RUNNING")
    state["current_stage"] = stage_id
    tr.emit(state, "SKILL_STARTED", task_id=rec.get("task_id"), skill=skill,
            attempt=rec.get("attempts", 1), detail="stage=%s" % stage_id)

    canonical = adapter(copy.deepcopy(native))

    err = _validate_contract(canonical, contract)
    if err:
        return _fail("%s contract validation failed: %s" % (art_type, err))

    # freeze discipline: dialogue artifacts may be refined only while nothing
    # downstream has consumed them (CaseState immutability otherwise applies)
    if any(t in (state.get("artifacts") or {}) for t in DOWNSTREAM_TYPES) \
            and art_type in (state.get("artifacts") or {}):
        return _fail("downstream analysis already started — %s is frozen; "
                     "start a new analysis to change it" % art_type)

    ok, reasons = cs.put_artifact(state, art_type, canonical, stage_id)
    if not ok and art_type in (state.get("artifacts") or {}):
        # put_artifact refuses overwrites; dialogue refinement replaces the
        # still-upstream artifact explicitly (fingerprint re-stamped by registry)
        state["artifacts"][art_type] = copy.deepcopy(canonical)
        state["stages"][stage_id]["artifact_fingerprint"] = None
    elif not ok:
        return _fail("store failed: %s" % "; ".join(reasons))

    arec = reg.register(state, art_type, state["artifacts"][art_type],
                        {"id": stage_id, "skill": skill,
                         "produces": art_type, "consumes": []})
    tr.emit(state, "ARTIFACT_STORED", skill=skill, output_artifact=arec["artifact_id"],
            detail="artifact_type=%s stage=%s (agent)" % (art_type, stage_id))

    rec = state["stages"][stage_id]
    rec.setdefault("provided_by", "agent-conversation")
    rec["started_at"] = rec.get("started_at") or cs.now()
    tk.begin_attempt(state, stage_id)
    tk.set_output(state, stage_id, arec["artifact_id"])

    # ---- Phase 5.2: skip_eval → artifact-only (Harness owns the eval boundary).
    # The Tool stores the artifact; the caller runs eval + determines PASS/FAIL.
    if getattr(ctx, "skip_eval", False):
        ctx.persist()
        return _ok("%s stored (eval deferred to caller)" % art_type,
                   artifact_id=arec["artifact_id"], artifact_type=art_type,
                   eval_id=None, eval_status=None)

    tr.emit(state, "EVAL_STARTED", skill=skill, detail="artifact=%s" % art_type)
    rec_eval = ev.evaluate(state, art_type, state["artifacts"][art_type],
                           {"id": stage_id, "skill": skill, "contract": contract})
    tr.emit(state, "EVAL_COMPLETED", skill=skill, eval_status=rec_eval["status"],
            detail="artifact=%s eval=%s" % (art_type, rec_eval["eval_id"]))
    tk.attach_eval(state, stage_id, rec_eval["eval_id"])
    if rec_eval["status"] == "FAIL":
        tk.set_status(state, stage_id, "NEEDS_REVIEW",
                      failure_reason="EVAL_FAIL(%s)" % rec_eval["eval_id"])
        return _fail("%s eval FAIL: %s" % (art_type, rec_eval["eval_id"]),
                     eval_id=rec_eval["eval_id"], eval_status="FAIL")
    tk.set_status(state, stage_id, "COMPLETED")
    cs.record_event(state, "STAGE_COMPLETED", stage=stage_id,
                    detail="provided via agent conversation")
    tr.emit(state, "SKILL_COMPLETED", task_id=rec.get("task_id"), skill=skill,
            attempt=1, output_artifact=arec["artifact_id"],
            eval_status=rec_eval["status"], duration_ms=0.0,
            detail="stage=%s (provided via agent conversation)" % stage_id)
    ctx.persist()
    return _ok("%s stored and eval PASS" % art_type,
               artifact_id=arec["artifact_id"], artifact_type=art_type,
               eval_id=rec_eval["eval_id"], eval_status="PASS")


def _four_tuple(value) -> dict:
    """User-stated leaf → canonical four-tuple with provenance to the message."""
    return {"value": value, "status": "KNOWN", "source": USER_SOURCE,
            "confidence": 0.9}


def _normalize_profile(section: Optional[dict]) -> dict:
    out = {}
    for k, v in (section or {}).items():
        if isinstance(v, dict) and "value" in v:
            v = dict(v)
            v.setdefault("source", USER_SOURCE)
            v.setdefault("status", "KNOWN")
            out[k] = v
        else:
            out[k] = _four_tuple(v)
    return out


# --------------------------------------------------------------------------- #
# dialogue-skill tools
# --------------------------------------------------------------------------- #
def _record_client_profile(args: dict, ctx: ToolContext) -> dict:
    sections = {
        "family_profile": _normalize_profile(args.get("family_profile")),
        "financial_profile": _normalize_profile(args.get("financial_profile")),
        "existing_protection": _normalize_profile(args.get("existing_protection")),
        "employment_profile": {},
        "responsibility_profile": {},
    }
    missing = [{"profile": "client", "field": n, "reason": "用户尚未提供"}
               for n in (args.get("notes_for_unknown") or [])]
    native = {"client_state_version": "1.0",
              "missing_from_upstream": missing,
              "conflicts": []}
    native.update(sections)
    return _store_dialogue_artifact(
        ctx, "client-profile", native, cia.to_canonical, "client-intake",
        "client-intake", "contracts/client-profile.schema.json")


def _record_requirement_analysis(args: dict, ctx: ToolContext) -> dict:
    reqs = []
    for r in args.get("requirements") or []:
        reqs.append({
            "requirement_id": r["requirement_id"],
            "requirement_type": r["requirement_type"],
            "summary": r["summary"],
            "priority": r["priority"],
            "boundary": "requirement_only",
            "reason": r.get("reason") or "来自用户对话中的表述",
            "source": USER_SOURCE,
        })
    native = {"analysis_status": "FORMAL", "requirements": reqs}
    return _store_dialogue_artifact(
        ctx, "requirement-analysis", native, raa.to_canonical, "requirement_analysis",
        "requirement-analysis", "contracts/requirement-analysis.schema.json")


def _record_risk_assessment(args: dict, ctx: ToolContext) -> dict:
    risks = []
    for r in args.get("risks") or []:
        cat = r["risk_category"].split("_", 1)[-1]
        risks.append({
            "risk_id": r["risk_id"],
            "risk_category": cat,
            "risk_name": r["risk_name"],
            "priority": r["priority"],
            "severity": r.get("severity") or "HIGH",
            "likelihood": r.get("likelihood") or "MEDIUM",
            "residual_risk": r.get("residual_risk") or "HIGH",
            "existing_protection": r.get("existing_protection") or "无",
            "coverage_assessment": {"protected_amount": 0,
                                    "unprotected_amount": None,
                                    "confidence": 0.5},
            "conclusion": r.get("reason") or "",
            "reason": r.get("reason") or "来自用户对话中描述的情况",
            "reasoning_evidence_refs": [],
        })
    native = {"analysis_status": "FORMAL", "layer": "risk_analysis",
              "output_version": "1.0",
              "overall_confidence": args.get("overall_confidence") or 0.6,
              "risks": risks}
    return _store_dialogue_artifact(
        ctx, "risk-assessment", native, rka.to_canonical, "risk-analysis",
        "risk-analysis", "contracts/risk-assessment.schema.json")


# --------------------------------------------------------------------------- #
# deterministic stage tools (existing engines + existing eval/repair)
# --------------------------------------------------------------------------- #
def _make_stage_tool(tool_name: str):
    stage_id = STAGE_ID_OF[tool_name]

    def _run(args: dict, ctx: ToolContext) -> dict:
        state, wf = ctx.state, ctx.workflow
        stage = next((s for s in wf["stages"] if s["id"] == stage_id), None)
        if stage is None:  # pragma: no cover — workflow is internal
            return _fail("unknown stage %s" % stage_id)
        missing = [a for a in (stage.get("consumes") or [])
                   if a not in (state.get("artifacts") or {})]
        if missing:
            return _fail("missing prerequisite artifacts: %s — record the "
                         "dialogue facts first or run earlier stages" % ", ".join(missing))
        state["current_stage"] = stage_id
        result = orch._execute_stage(state, wf, stage)  # noqa: SLF001 — declared adapter
        outcome = result.get("outcome")
        if outcome == "GATE":
            # V0.1: auto-approve the human-review gate, mirroring the demo wrapper
            orch.approve(state, stage_id)
            outcome = "OK"
        if outcome == "OK":
            ctx.persist()
            art_type = ARTIFACT_OF[stage_id]
            arec = reg.by_type(state, art_type) or {}
            eval_id = (result.get("eval") or {}).get("eval_id")
            return _ok("%s completed (eval PASS)" % tool_name,
                       artifact_id=arec.get("artifact_id"), artifact_type=art_type,
                       eval_id=eval_id, eval_status="PASS")
        # NEEDS_REVIEW after existing eval + bounded repair: the agent must stop
        return {"status": "needs_review",
                "summary": "%s did not pass evaluation after repair — needs human "
                           "review" % tool_name,
                "eval_id": (result.get("eval") or {}).get("eval_id"),
                "failed_checks": result.get("failed_checks", [])[:5]}

    return _run


# --------------------------------------------------------------------------- #
# knowledge + catalog tools
# --------------------------------------------------------------------------- #
def _knowledge_search(args: dict, ctx: ToolContext) -> dict:
    from knowledge.evidence.provider import build_engine

    engine = build_engine()
    res = engine.search(args["query"])
    hits = getattr(res, "chunks", None) or getattr(res, "results", None) or []
    out = []
    for c in hits[:5]:
        out.append({
            "chunk_id": getattr(c, "chunk_id", None),
            "document_id": getattr(c, "document_id", None),
            "document_name": getattr(c, "document_name", None),
            "section": getattr(c, "section", None),
            "content": (getattr(c, "content", None) or "")[:400],
            "score": getattr(c, "final_score", None) or getattr(c, "score", None),
        })
    if not out:
        return _ok("knowledge search returned no evidence for this query",
                   data={"evidence": [],
                         "note": "知识库中没有找到相关证据，请如实告知用户"})
    return _ok("knowledge search returned %d evidence chunks" % len(out),
               data={"evidence": out})


def _check_catalog_product(args: dict, ctx: ToolContext) -> dict:
    import json as _json

    catalog = ev.load_catalog(ev.load_rules())
    q = (args["query"] or "").strip().lower()
    hits = [p for p in catalog
            if q in str(p.get("product_id", "")).lower()
            or q in str(p.get("product_name", "")).lower()
            or q in str(p.get("company", "")).lower()]
    if not hits:
        return _ok("not found in catalog",
                   data={"products": [],
                         "note": "当前演示产品目录中没有找到该产品。不得编造产品信息。"})
    slim = [{k: p.get(k) for k in ("product_id", "product_name", "company",
                                   "product_version", "catalog_version")}
            for p in hits[:5]]
    return _ok("found %d matching products in the demo catalog" % len(hits),
               data={"products": slim})


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
def build_registry() -> dict:
    tools = {}
    for spec, fn in [
        (S.RECORD_CLIENT_PROFILE, _record_client_profile),
        (S.RECORD_REQUIREMENT_ANALYSIS, _record_requirement_analysis),
        (S.RECORD_RISK_ASSESSMENT, _record_risk_assessment),
        (S.RUN_COVERAGE_GAP, _make_stage_tool("coverage_gap_analysis")),
        (S.RUN_SOLUTION, _make_stage_tool("solution")),
        (S.RUN_PRODUCT_CANDIDATES, _make_stage_tool("product_candidate_provider")),
        (S.RUN_RECOMMENDATION, _make_stage_tool("recommendation")),
        (S.RUN_REPORT, _make_stage_tool("report_generation")),
        (S.KNOWLEDGE_SEARCH, _knowledge_search),
        (S.CHECK_CATALOG_PRODUCT, _check_catalog_product),
    ]:
        tools[spec["name"]] = Tool(spec["name"], spec["description"],
                                   spec["parameters"], fn)
    return tools


def validate_arguments(tool: Tool, args: dict) -> Optional[str]:
    """JSON-Schema validation BEFORE execution (spec §33). None = valid."""
    from jsonschema import Draft7Validator

    v = Draft7Validator(tool.parameters)
    errs = sorted(v.iter_errors(args or {}), key=lambda e: list(e.path))
    if not errs:
        return None
    return "; ".join("%s: %s" % ("/".join(str(p) for p in e.path) or "<root>",
                                 e.message) for e in errs[:3])
