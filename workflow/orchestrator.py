"""Orchestrator (V2 Phase 7).

Executes the `insurance-analysis` workflow against a CaseState:

    seed (provided stages)  ->  stage 3..6 (python engines)  ->  report

What it does
  * loads the workflow definition (workflow/insurance-analysis.yaml) — the single source of
    truth for stage order, inputs, outputs and gates;
  * seeds the dialogue-driven stages (client-intake / requirement-analysis / risk-analysis)
    from artifacts produced upstream, wrapping them into canonical envelopes via adapters;
  * runs each deterministic stage by importing the skill's DECLARED entrypoint and calling
    the declared function — it never re-implements a skill;
  * serviced non-linear needs (knowledge-search Evidence Provider) on behalf of a stage;
  * validates every produced artifact against its canonical contract;
  * enforces monotonicity / preconditions / artifact freeze through state/transitions.py;
  * stops at a human-review gate and resumes after explicit approval.

What it does NOT do
  * no insurance judgment of any kind: it moves artifacts and enforces order;
  * no artifact rewriting: it stores exactly what the skill produced.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from state import case_state as cs  # noqa: E402
from state import transitions  # noqa: E402

WORKFLOW_PATH = os.path.join(HERE, "insurance-analysis.yaml")

# adapters used to bring seeded upstream artifacts into canonical shape
_SEED_ADAPTERS = {
    "client-profile": ("adapters.client_intake_adapter", "to_canonical"),
    "requirement-analysis": ("adapters.requirement_analysis_adapter", "to_canonical"),
    "risk-assessment": ("adapters.risk_analysis_adapter", "to_canonical"),
}


# --------------------------------------------------------------------------- #
# workflow loading
# --------------------------------------------------------------------------- #
def load_workflow(path: Optional[str] = None) -> dict:
    import yaml

    with open(path or WORKFLOW_PATH, encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    # stage index is derived from list order — the list is the single source of truth.
    for i, st in enumerate(wf.get("stages", [])):
        st["index"] = i
    return wf


def _service_by_id(workflow: dict, sid: str) -> Optional[dict]:
    for s in workflow.get("services", []) or []:
        if s["id"] == sid:
            return s
    return None


# --------------------------------------------------------------------------- #
# module loading & invocation
# --------------------------------------------------------------------------- #
_MODULE_CACHE: dict = {}


def _load_module(rel_path: str, name: str):
    if name in _MODULE_CACHE:
        return _MODULE_CACHE[name]
    abs_path = os.path.join(REPO_ROOT, rel_path) if not os.path.isabs(rel_path) else rel_path
    spec = importlib.util.spec_from_file_location(name, abs_path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load entrypoint: %s" % abs_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODULE_CACHE[name] = mod
    return mod


def _payload_of(artifact: Any) -> Any:
    if isinstance(artifact, dict) and isinstance(artifact.get("payload"), dict):
        return artifact["payload"]
    return artifact


def build_stage_input(state: dict, stage: dict) -> dict:
    """Assemble a stage's input dict from CaseState.

    Key/shape come from the stage's `input_map`; defaults are key=artifact_type with hyphens
    replaced by underscores, shape='artifact' (the canonical envelope).
    """
    input_map = stage.get("input_map") or {}
    present = [a for a in (stage.get("consumes", []) + stage.get("optional_consumes", []))
               if a in (state.get("artifacts") or {})]
    out = {}
    for art_type in present:
        spec = input_map.get(art_type) or {}
        key = spec.get("key") or art_type.replace("-", "_")
        shape = spec.get("shape", "artifact")
        art = state["artifacts"][art_type]
        out[key] = _payload_of(art) if shape == "payload" else art
    return out


def _normalize_result(res, style: str) -> tuple:
    """Return (artifact, warnings, errors) from a skill's native return shape."""
    if style == "tuple3":            # (artifact, ok, errors)
        art, ok, errs = res
        return art, [], (list(errs) if not ok else [])
    if style == "tuple2":            # (artifact, warnings)
        art, warns = res
        return art, list(warns or []), []
    return res, [], []               # bare artifact


def validate_artifact(artifact: dict, contract_path: str) -> tuple:
    from jsonschema import Draft7Validator

    p = os.path.join(REPO_ROOT, contract_path) if not os.path.isabs(contract_path) else contract_path
    with open(p, encoding="utf-8") as f:
        schema = json.load(f)
    Draft7Validator.check_schema(schema)
    errs = sorted(Draft7Validator(schema).iter_errors(artifact), key=lambda e: list(e.path))
    return (len(errs) == 0,
            ["%s: %s" % ("/".join(str(x) for x in e.path) or "<root>", e.message) for e in errs])


def _apply_post_adapter(dotted: str, artifact: Any) -> Any:
    """Apply a declared adapter (module.function) to a skill's native output."""
    import importlib

    mod_name, fn_name = dotted.rsplit(".", 1)
    mod = importlib.import_module(mod_name)
    return getattr(mod, fn_name)(artifact)


def _invoke_python_stage(state: dict, stage: dict) -> tuple:
    """Import the stage's entrypoint, call its declared function. Returns (artifact, warnings, errors)."""
    mod = _load_module(stage["entrypoint"], "_stage_%s" % stage["id"].replace("-", "_"))
    call = stage.get("call") or {}
    fn = getattr(mod, call["fn"])
    payload = build_stage_input(state, stage)
    args = [payload]
    if call.get("rules_from"):
        args.append(getattr(mod, call["rules_from"])())
    res = fn(*args)
    return _normalize_result(res, call.get("result", "artifact"))


# --------------------------------------------------------------------------- #
# services (non-linear shared providers)
# --------------------------------------------------------------------------- #
def _run_stage_services(state: dict, workflow: dict, stage: dict) -> list:
    """Service any shared provider a stage declares (e.g. knowledge-search evidence)."""
    out = []
    for spec in stage.get("services", []) or []:
        sdef = _service_by_id(workflow, spec["id"])
        rec = state.setdefault("services", {}).setdefault(
            spec["id"], {"skill": sdef["skill"], "provides": sdef.get("provides"),
                         "calls": 0, "last_requester": None, "last_at": None,
                         "source_unchanged": None})
        src = state.get("artifacts", {}).get(spec["source"])
        if src is None:
            rec["calls"] += 1
            cs.record_event(state, "SERVICE_CALLED", stage=stage["id"],
                            detail="%s: missing source %s" % (spec["id"], spec["source"]))
            out.append({"id": spec["id"], "ok": False,
                        "reason": "MISSING_SOURCE_ARTIFACT: %s" % spec["source"]})
            continue
        from evidence import loop as ev_loop

        rnd = ev_loop.request_evidence(src, source_kind=spec["source_kind"], purpose=spec["purpose"])
        rec["calls"] += 1
        rec["last_requester"] = stage["id"]
        rec["last_at"] = cs._now()
        rec["source_unchanged"] = rnd.get("source_unchanged")
        cs.record_event(state, "SERVICE_CALLED", stage=stage["id"],
                        detail="%s purpose=%s source_unchanged=%s"
                               % (spec["id"], spec["purpose"], rnd.get("source_unchanged")))
        evidence = rnd.get("evidence")
        if evidence is not None:
            store_as = spec.get("store_as") or sdef.get("provides")
            # The service output is an artifact of the shared provider, not of `stage`.
            ok, reasons = cs.put_artifact(state, store_as, evidence, stage["id"])
            if not ok:
                out.append({"id": spec["id"], "ok": False, "reason": "; ".join(reasons)})
                continue
        out.append({"id": spec["id"], "ok": bool(rnd.get("ok")),
                    "source_unchanged": rnd.get("source_unchanged"),
                    "errors": rnd.get("errors", [])})
    return out


# --------------------------------------------------------------------------- #
# seeding
# --------------------------------------------------------------------------- #
def seed_case(workflow: dict, case_id: str, seeds: dict,
              provided_by: str = "upstream-dialogue") -> dict:
    """Create a CaseState and fill the `executor: provided` stages from `seeds`.

    `seeds` maps artifact_type -> artifact (canonical envelope or raw legacy output).
    Raw seeds are wrapped into canonical envelopes via the Phase 1 adapters, so CaseState
    always holds canonical artifacts.
    """
    state = cs.new_case_state(case_id, workflow)
    for st in workflow["stages"]:
        if st.get("executor") != "provided":
            continue
        art_type = st.get("produces")
        if art_type is None or art_type not in seeds:
            continue
        raw = seeds[art_type]
        artifact = raw if (isinstance(raw, dict) and "artifact_type" in raw) else _adapt_seed(art_type, raw)
        rec = state["stages"][st["id"]]
        rec["attempts"] = 1
        rec["provided_by"] = provided_by
        rec["started_at"] = cs.now()
        ok, reasons = cs.put_artifact(state, art_type, artifact, st["id"])
        if not ok:  # pragma: no cover - first write cannot violate immutability
            raise RuntimeError("seed failed for %s: %s" % (art_type, reasons))
        rec["completed_at"] = cs.now()
        note = "seeded via %s" % provided_by
        if st.get("gate") == "human_review":
            note += " (gate=human_review satisfied upstream)"
        cs.set_status(state, st["id"], "COMPLETED", note)
        cs.record_event(state, "STAGE_COMPLETED", stage=st["id"], detail=note)
    return state


def _adapt_seed(art_type: str, raw: Any) -> dict:
    mod_name, fn_name = _SEED_ADAPTERS[art_type]
    import importlib

    mod = importlib.import_module(mod_name)
    return getattr(mod, fn_name)(raw)


# --------------------------------------------------------------------------- #
# approval / gates
# --------------------------------------------------------------------------- #
def approve(state: dict, stage_id: str) -> None:
    """Clear a human-review gate: mark the stage COMPLETED so downstream may consume it."""
    if state["stages"][stage_id]["status"] != "NEEDS_REVIEW":
        raise ValueError("stage %s is not awaiting review (status=%s)"
                         % (stage_id, state["stages"][stage_id]["status"]))
    cs.set_status(state, stage_id, "COMPLETED", "approved by human reviewer")
    cs.record_event(state, "APPROVED", stage=stage_id, detail="human review cleared")


def _needs_review(stage: dict, artifact: Any) -> bool:
    if stage.get("gate") == "human_review":
        return True
    if isinstance(artifact, dict):
        p = _payload_of(artifact)
        if isinstance(p, dict) and p.get("human_review_required") is True:
            return True
    return False


# --------------------------------------------------------------------------- #
# main run loop
# --------------------------------------------------------------------------- #
def run(state: dict, workflow: Optional[dict] = None, gate_policy: str = "stop",
        max_stages: int = 50) -> dict:
    """Advance the case as far as the invariants and gates allow.

    gate_policy:
      * "stop" -- park at a human-review gate (status NEEDS_REVIEW) and return PAUSED
      * "auto" -- treat unfinished human-review gates as auto-approved for this run

    Returns a report: {status, stopped_at, reasons, executed, state}.
    """
    workflow = workflow or load_workflow()
    executed, reasons = [], []
    steps = 0

    while True:
        steps += 1
        if steps > max_stages:
            return _report("FAILED", None, ["MAX_STAGES_EXCEEDED"], executed, state)

        sid = transitions.next_runnable(state, workflow)
        if sid is None:
            return _report("COMPLETED", None, [], executed, state)

        stage = transitions.stage_by_id(workflow, sid)
        rec = state["stages"][sid]

        # A stage parked at NEEDS_REVIEW is not re-run; it waits for approval.
        if rec["status"] == "NEEDS_REVIEW":
            if gate_policy == "auto":
                approve(state, sid)
                continue
            return _report("PAUSED_NEEDS_REVIEW", sid,
                           ["AWAITING_HUMAN_REVIEW: %s" % sid], executed, state)

        if rec["status"] == "FAILED":
            return _report("FAILED", sid, rec.get("notes", []), executed, state)

        ok, rs = transitions.can_run(state, stage)
        if not ok:
            cs.record_event(state, "GUARD_REJECTED", stage=sid, detail="; ".join(rs))
            return _report("BLOCKED", sid, rs, executed, state)

        if stage.get("executor") == "provided":
            # No seed for this stage -> the orchestrator cannot invent it.
            return _report("BLOCKED", sid,
                           ["MISSING_PROVIDED_ARTIFACT: %s (executor=provided, no seed)"
                            % (stage.get("produces"))], executed, state)

        cs.set_status(state, sid, "RUNNING")
        rec["attempts"] += 1
        rec["started_at"] = cs._now()
        cs.record_event(state, "STAGE_START", stage=sid, detail=stage.get("skill"))
        state["current_stage"] = sid

        svc = _run_stage_services(state, workflow, stage)
        if any(not s["ok"] for s in svc):
            bad = "; ".join("%s: %s" % (s["id"], s.get("reason") or s.get("errors")) for s in svc if not s["ok"])
            cs.set_status(state, sid, "FAILED", "service failure: " + bad)
            cs.record_event(state, "STAGE_FAILED", stage=sid, detail=bad)
            return _report("FAILED", sid, ["SERVICE_FAILED: " + bad], executed, state)

        try:
            artifact, warns, errs = _invoke_python_stage(state, stage)
        except Exception as e:  # noqa: BLE001
            cs.set_status(state, sid, "FAILED", "exception: %r" % e)
            cs.record_event(state, "STAGE_FAILED", stage=sid, detail=repr(e))
            return _report("FAILED", sid, ["STAGE_EXCEPTION: %r" % e], executed, state)

        if errs:
            cs.set_status(state, sid, "FAILED", "invalid output: " + "; ".join(errs))
            cs.record_event(state, "STAGE_FAILED", stage=sid, detail="; ".join(errs))
            return _report("FAILED", sid, ["INVALID_OUTPUT: " + "; ".join(errs)], executed, state)

        # Declared adapter boundary: a skill's native result -> canonical artifact.
        if stage.get("post_adapter"):
            artifact = _apply_post_adapter(stage["post_adapter"], artifact)

        contract = stage.get("contract")
        if contract:
            vok, verrs = validate_artifact(artifact, contract)
            if not vok:
                cs.set_status(state, sid, "FAILED", "contract violation: " + "; ".join(verrs))
                cs.record_event(state, "STAGE_FAILED", stage=sid,
                                detail="CONTRACT_VIOLATION: " + "; ".join(verrs))
                return _report("FAILED", sid, ["CONTRACT_VIOLATION: " + "; ".join(verrs)], executed, state)

        ok, rs = cs.put_artifact(state, stage["produces"], artifact, sid)
        if not ok:
            cs.set_status(state, sid, "FAILED", "; ".join(rs))
            return _report("FAILED", sid, rs, executed, state)

        rec["completed_at"] = cs._now()
        executed.append({"stage": sid, "warnings": warns, "services": svc})

        if _needs_review(stage, artifact):
            cs.set_status(state, sid, "NEEDS_REVIEW", "awaiting human review")
            cs.record_event(state, "STAGE_NEEDS_REVIEW", stage=sid)
            if gate_policy == "auto":
                approve(state, sid)
                continue
            return _report("PAUSED_NEEDS_REVIEW", sid,
                           ["AWAITING_HUMAN_REVIEW: %s" % sid], executed, state)

        cs.set_status(state, sid, "COMPLETED")
        cs.record_event(state, "STAGE_COMPLETED", stage=sid)


def _report(status: str, stopped_at, reasons, executed, state: dict) -> dict:
    return {
        "status": status,
        "stopped_at": stopped_at,
        "reasons": list(reasons),
        "executed": executed,
        "stages": cs.statuses(state),
        "state": state,
    }
