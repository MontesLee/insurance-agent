"""Orchestrator (V2 Phase 7 + Step 3).

Executes the `insurance-analysis` workflow against a CaseState:

    seed (provided stages) -> deterministic engines -> eval -> (repair) -> next -> report

What it does
  * loads the workflow definition (runtime/insurance-analysis.yaml) — the single source of
    truth for stage order, inputs, outputs, gates, eval policy and repair policy;
  * seeds the dialogue-driven stages from artifacts produced upstream (never invents them);
  * runs each deterministic stage by importing the skill's DECLARED entrypoint;
  * serviced non-linear needs (knowledge-search Evidence Provider) on behalf of a stage;
  * **evaluates** every produced artifact (Step 3) — execution success is not correctness;
  * **repairs** locally and within budget (max 2) when an eval fails, injecting the failed
    checks as feedback;
  * enforces monotonicity / preconditions / artifact freeze through runtime/state/transitions.py;
  * stops at a human-review gate, and parks the case in WAITING_FOR_USER when the client's own
    facts are missing or conflicting instead of pushing UNKNOWN downstream.

What it does NOT do
  * no insurance judgment of any kind: it moves artifacts and enforces order;
  * no artifact rewriting: it stores exactly what the skill produced;
  * no repair that edits a produced artifact — repair changes the STAGE INPUT and re-runs.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import time
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from .state import case_state as cs  # noqa: E402
from .state import transitions  # noqa: E402
from . import tasks as tk  # noqa: E402
from . import artifact_registry as reg  # noqa: E402
from . import eval_engine as ev  # noqa: E402
from . import repair  # noqa: E402
from . import trace as tr  # noqa: E402

WORKFLOW_PATH = os.path.join(HERE, "insurance-analysis.yaml")
ORCH_RULES = os.path.join(HERE, "resources", "config", "orchestrator.rules.json")

_SEED_ADAPTERS = {
    "client-profile": ("adapters.client_intake_adapter", "to_canonical"),
    "requirement-analysis": ("adapters.requirement_analysis_adapter", "to_canonical"),
    "risk-assessment": ("adapters.risk_analysis_adapter", "to_canonical"),
}


# --------------------------------------------------------------------------- #
# workflow / rules loading
# --------------------------------------------------------------------------- #
def load_workflow(path: Optional[str] = None) -> dict:
    import yaml

    with open(path or WORKFLOW_PATH, encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    # stage index is derived from list order — the list is the single source of truth.
    for i, st in enumerate(wf.get("stages", [])):
        st["index"] = i
    return wf


def load_orch_rules(path: Optional[str] = None) -> dict:
    with open(path or ORCH_RULES, encoding="utf-8") as f:
        return json.load(f)


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
    """Assemble a stage's input dict from CaseState (key/shape from `input_map`)."""
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
    mod_name, fn_name = dotted.rsplit(".", 1)
    mod = importlib.import_module(mod_name)
    return getattr(mod, fn_name)(artifact)


def _invoke_python_stage(state: dict, stage: dict, input_override: Optional[dict] = None) -> tuple:
    mod = _load_module(stage["entrypoint"], "_stage_%s" % stage["id"].replace("-", "_"))
    call = stage.get("call") or {}
    fn = getattr(mod, call["fn"])
    payload = input_override if input_override is not None else build_stage_input(state, stage)
    args = [payload]
    if call.get("rules_from"):
        args.append(getattr(mod, call["rules_from"])())
    res = fn(*args)
    return _normalize_result(res, call.get("result", "artifact"))


# --------------------------------------------------------------------------- #
# services (non-linear shared providers)
# --------------------------------------------------------------------------- #
def _run_stage_services(state: dict, workflow: dict, stage: dict,
                        kb_dir: Optional[str] = None) -> list:
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
            tr.emit(state, "TOOL_STARTED", skill=sdef["skill"],
                    detail="tool=%s purpose=%s stage=%s" % (spec["id"], spec["purpose"], stage["id"]))
            tr.emit(state, "TOOL_FAILED", skill=sdef["skill"],
                    detail="tool=%s purpose=%s missing_source=%s"
                           % (spec["id"], spec["purpose"], spec["source"]))
            cs.record_event(state, "SERVICE_CALLED", stage=stage["id"],
                            detail="%s: missing source %s" % (spec["id"], spec["source"]))
            out.append({"id": spec["id"], "ok": False,
                        "reason": "MISSING_SOURCE_ARTIFACT: %s" % spec["source"]})
            continue
        from knowledge.evidence import loop as ev_loop

        tr.emit(state, "TOOL_STARTED", skill=sdef["skill"],
                detail="tool=%s purpose=%s stage=%s" % (spec["id"], spec["purpose"], stage["id"]))
        rnd = ev_loop.request_evidence(src, source_kind=spec["source_kind"],
                                       purpose=spec["purpose"], kb_dir=kb_dir)
        rec["calls"] += 1
        rec["last_requester"] = stage["id"]
        rec["last_at"] = cs._now()
        rec["source_unchanged"] = rnd.get("source_unchanged")
        if rnd.get("ok"):
            tr.emit(state, "TOOL_COMPLETED", skill=sdef["skill"],
                    detail="tool=%s purpose=%s source_unchanged=%s"
                           % (spec["id"], spec["purpose"], rnd.get("source_unchanged")))
        else:
            tr.emit(state, "TOOL_FAILED", skill=sdef["skill"],
                    detail="tool=%s purpose=%s errors=%s"
                           % (spec["id"], spec["purpose"], rnd.get("errors", [])))
        cs.record_event(state, "SERVICE_CALLED", stage=stage["id"],
                        detail="%s purpose=%s source_unchanged=%s"
                               % (spec["id"], spec["purpose"], rnd.get("source_unchanged")))
        evidence = rnd.get("evidence")
        store_as = spec.get("store_as") or sdef.get("provides")
        if evidence is not None:
            if store_as in state.get("artifacts", {}):
                # The evidence loop is read-only: re-requesting evidence for the same source
                # must not rewrite the artifact. A fresh one would carry a new generated_at and
                # trip the freeze guard as a bogus ARTIFACT_MUTATION on every repair attempt.
                art = state["artifacts"][store_as]
            else:
                ok, reasons = cs.put_artifact(state, store_as, evidence, stage["id"])
                if not ok:
                    out.append({"id": spec["id"], "ok": False, "reason": "; ".join(reasons)})
                    continue
                art = state["artifacts"][store_as]
                arec = reg.register(state, store_as, art,
                                    {"id": spec["id"], "skill": sdef["skill"], "consumes": []})
                tr.emit(state, "ARTIFACT_STORED", skill=sdef["skill"],
                        output_artifact=arec["artifact_id"],
                        detail="artifact_type=%s stage=%s" % (store_as, stage["id"]))
            tr.emit(state, "EVAL_STARTED", skill=sdef["skill"],
                    detail="artifact=%s" % store_as)
            rec_ = ev.evaluate(state, store_as, art,
                               {"id": spec["id"], "skill": sdef["skill"], "contract": None},
                               rules=EV_RULES, registry=reg)
            tr.emit(state, "EVAL_COMPLETED", skill=sdef["skill"],
                    eval_status=rec_["status"],
                    detail="artifact=%s eval=%s" % (store_as, rec_["eval_id"]))
            if rec_["status"] == "FAIL":
                # Spec §32: an Evidence Provider that returns nothing must stop the stage —
                # it must never be allowed to flow downstream as if it were knowledge.
                bad = "; ".join("%s(%s)" % (c["check_id"], c.get("message", ""))
                                for c in ev.failed_checks(rec_))
                cs.record_event(state, "EVAL_FAIL", stage=stage["id"],
                                detail="%s %s: %s" % (rec_["eval_id"], store_as, bad))
                out.append({"id": spec["id"], "ok": False,
                            "reason": "EVIDENCE_EVAL_FAIL[%s]: %s" % (rec_["eval_id"], bad)})
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
    state = cs.new_case_state(case_id, workflow)
    tr.emit(state, "CASE_STARTED", detail="workflow=%s" % workflow.get("workflow"))
    tk.init_tasks(state, workflow)
    for st in workflow["stages"]:
        if st.get("executor") != "provided":
            continue
        art_type = st.get("produces")
        if art_type is None or art_type not in seeds:
            continue
        raw = seeds[art_type]
        artifact = raw if (isinstance(raw, dict) and "artifact_type" in raw) else _adapt_seed(art_type, raw)
        rec = state["stages"][st["id"]]
        rec["provided_by"] = provided_by
        rec["started_at"] = cs.now()
        ok, reasons = cs.put_artifact(state, art_type, artifact, st["id"])
        if not ok:  # pragma: no cover - first write cannot violate immutability
            raise RuntimeError("seed failed for %s: %s" % (art_type, reasons))
        arec = reg.register(state, art_type, state["artifacts"][art_type], st)
        tr.emit(state, "ARTIFACT_STORED", task_id=rec.get("task_id"), skill=st.get("skill"),
                output_artifact=arec["artifact_id"],
                detail="artifact_type=%s stage=%s (seeded)" % (art_type, st["id"]))
        tk.begin_attempt(state, st["id"])
        tk.set_output(state, st["id"], reg.by_type(state, art_type)["artifact_id"])

        # Eval gates seeded artifacts too (spec §16): an artifact that entered the case from
        # outside is still an artifact, and a contaminated one must not flow downstream.
        eval_rules, _ = _rules()
        tr.emit(state, "EVAL_STARTED", task_id=rec.get("task_id"), skill=st.get("skill"),
                detail="artifact=%s" % art_type)
        rec_eval = ev.evaluate(state, art_type, state["artifacts"][art_type], st,
                               rules=eval_rules, registry=reg)
        tr.emit(state, "EVAL_COMPLETED", task_id=rec.get("task_id"), skill=st.get("skill"),
                eval_status=rec_eval["status"],
                detail="artifact=%s eval=%s" % (art_type, rec_eval["eval_id"]))
        tk.attach_eval(state, st["id"], rec_eval["eval_id"])
        if rec_eval["status"] == "FAIL":
            reason = "EVAL_FAIL(%s): %s" % (
                rec_eval["eval_id"],
                "; ".join("%s(%s)" % (c["check_id"], c.get("message", ""))
                          for c in ev.failed_checks(rec_eval)))
            cs.needs_review(state, st["id"], reason,
                            failed_checks=ev.failed_checks(rec_eval), repair_attempts=0)
            tk.set_status(state, st["id"], "NEEDS_REVIEW", failure_reason=reason)
            continue

        rec["completed_at"] = cs.now()
        note = "seeded via %s" % provided_by
        if st.get("gate") == "human_review":
            note += " (gate=human_review satisfied upstream)"
        tk.set_status(state, st["id"], "COMPLETED")
        cs.record_event(state, "STAGE_COMPLETED", stage=st["id"], detail=note)
        tr.emit(state, "SKILL_COMPLETED", task_id=rec.get("task_id"), skill=st.get("skill"),
                attempt=1, output_artifact=reg.by_type(state, art_type)["artifact_id"],
                eval_status=rec_eval["status"], duration_ms=0.0,
                detail=note + " (provided upstream, not executed locally)")
    return state


def _adapt_seed(art_type: str, raw: Any) -> dict:
    mod_name, fn_name = _SEED_ADAPTERS[art_type]
    mod = importlib.import_module(mod_name)
    return getattr(mod, fn_name)(raw)


# --------------------------------------------------------------------------- #
# approval / gates
# --------------------------------------------------------------------------- #
def approve(state: dict, stage_id: str) -> None:
    if state["stages"][stage_id]["status"] != "NEEDS_REVIEW":
        raise ValueError("stage %s is not awaiting review (status=%s)"
                         % (stage_id, state["stages"][stage_id]["status"]))
    tk.set_status(state, stage_id, "COMPLETED")
    cs.record_event(state, "APPROVED", stage=stage_id, detail="human review cleared")
    state["review"] = None


def _needs_review(stage: dict, artifact: Any) -> bool:
    if stage.get("gate") == "human_review":
        return True
    if isinstance(artifact, dict):
        p = _payload_of(artifact)
        if isinstance(p, dict) and p.get("human_review_required") is True:
            return True
    return False


# --------------------------------------------------------------------------- #
# client information gate (Step 3 §14 / §30 / §31)
# --------------------------------------------------------------------------- #
def check_client_information(state: dict, rules: Optional[dict] = None) -> Optional[dict]:
    """Inspect the client facts. Returns a hand-off dict when the case must ask the client.

    Never resolves a conflict by picking a value, and never upgrades UNKNOWN to a guess.
    """
    rules = rules or load_orch_rules()
    art = state.get("artifacts", {}).get("client-profile")
    if art is None:
        return None
    payload = _payload_of(art)
    if not isinstance(payload, dict):
        return None

    conflicts = payload.get("conflicts") or []
    if conflicts and (rules.get("conflict", {}) or {}).get("enabled", True):
        questions = []
        tpl = rules.get("conflict_question", "")
        for c in conflicts:
            field = c.get("field") if isinstance(c, dict) else str(c)
            cands = c.get("candidates") if isinstance(c, dict) else None
            questions.append(tpl.format(field=field, candidates=cands or "多个取值"))
        return {"reason": "CONFLICTING_INFORMATION", "blocking_fields": [],
                "conflicts": conflicts, "next_questions": questions}

    ins = (rules.get("insufficient", {}) or {})
    if not ins.get("enabled", True):
        return None
    blocking_specs = ins.get("blocking_fields", [])
    missing = payload.get("missing_from_upstream") or []
    missing_keys = {(m.get("profile"), m.get("field")) for m in missing if isinstance(m, dict)}

    blocking = []
    for spec in blocking_specs:
        key = (spec.get("profile"), spec.get("field"))
        if key in missing_keys:
            blocking.append(spec)
            continue
        if ins.get("also_block_when_status_unknown", True):
            prof = payload.get(spec.get("profile")) or {}
            fv = prof.get(spec.get("field"))
            if isinstance(fv, dict) and fv.get("status") in ("UNKNOWN", None):
                blocking.append(spec)

    if not blocking:
        return None
    templates = rules.get("next_question_templates", {})
    questions = []
    for spec in blocking:
        k = "%s.%s" % (spec.get("profile"), spec.get("field"))
        questions.append(templates.get(k) or rules.get("default_question", "请补充：{profile}.{field}")
                         .format(profile=spec.get("profile"), field=spec.get("field")))
    return {"reason": "INSUFFICIENT_INFORMATION", "blocking_fields": blocking,
            "conflicts": [], "next_questions": questions}


# --------------------------------------------------------------------------- #
# one stage: run -> eval -> bounded repair
# --------------------------------------------------------------------------- #
EV_RULES: Optional[dict] = None
REPAIR_RULES: Optional[dict] = None


def _rules(eval_rules=None, repair_rules=None):
    global EV_RULES, REPAIR_RULES
    EV_RULES = eval_rules or EV_RULES or ev.load_rules()
    REPAIR_RULES = repair_rules or REPAIR_RULES or repair.load_rules()
    return EV_RULES, REPAIR_RULES


def _fail_stage(state, stage_id, reason):
    tk.set_status(state, stage_id, "FAILED", failure_reason=reason)
    tr.emit(state, "TASK_FAILED", task_id=state["stages"][stage_id].get("task_id"),
            skill=state["stages"][stage_id].get("skill"), detail=reason)
    cs.record_event(state, "STAGE_FAILED", stage=stage_id, detail=reason)


def _execute_stage(state: dict, workflow: dict, stage: dict, kb_dir=None,
                   eval_rules=None, repair_rules=None, enable_repair=True) -> dict:
    """Run one stage with Eval + bounded local Repair.

    Returns {"outcome": OK|GATE|NEEDS_REVIEW, ...}. Never rolls back upstream.
    """
    eval_rules, repair_rules = _rules(eval_rules, repair_rules)
    sid = stage["id"]
    max_attempts = int(stage.get("max_attempts", state["stages"][sid].get("max_attempts", 3)))

    while True:
        attempt = tk.begin_attempt(state, sid)
        tk.set_status(state, sid, "RUNNING")
        state["current_stage"] = sid
        cs.record_event(state, "STAGE_START", stage=sid, detail=stage.get("skill"))
        tid = state["stages"][sid].get("task_id")
        tr.emit(state, "TASK_STARTED", task_id=tid, skill=stage.get("skill"),
                attempt=attempt, detail="stage=%s" % sid)
        input_art_ids = [reg.by_type(state, a)["artifact_id"]
                         for a in (stage.get("consumes") or [])
                         if reg.by_type(state, a)]
        tr.emit(state, "SKILL_STARTED", task_id=tid, skill=stage.get("skill"),
                attempt=attempt, input_artifacts=input_art_ids, detail="stage=%s" % sid)
        tm = tr.timer()

        override = state.get("_repair_override", {}).get(sid)
        svc_err = None
        artifact = None
        errs: list = []

        svc = _run_stage_services(state, workflow, stage, kb_dir=kb_dir)
        if any(not s["ok"] for s in svc):
            svc_err = "; ".join("%s: %s" % (s["id"], s.get("reason") or s.get("errors"))
                                for s in svc if not s["ok"])
            errs = [svc_err]
        else:
            try:
                artifact, _warns, errs = _invoke_python_stage(state, stage, input_override=override)
            except Exception as e:  # noqa: BLE001
                artifact, errs = None, ["STAGE_EXCEPTION: %r" % e]

        if not errs and stage.get("post_adapter") and artifact is not None:
            artifact = _apply_post_adapter(stage["post_adapter"], artifact)

        if not errs and stage.get("contract") and artifact is not None:
            vok, verrs = validate_artifact(artifact, stage["contract"])
            if not vok:
                errs = ["CONTRACT_VIOLATION: " + "; ".join(verrs)]

        if not errs and artifact is not None:
            tr.emit(state, "EVAL_STARTED", task_id=tid, skill=stage.get("skill"),
                    attempt=attempt, detail="artifact=%s" % stage["produces"])
            rec_ = ev.evaluate(state, stage["produces"], artifact, stage,
                               rules=eval_rules, registry=reg)
            tk.attach_eval(state, sid, rec_["eval_id"])
            tr.emit(state, "EVAL_COMPLETED", task_id=tid, skill=stage.get("skill"),
                    attempt=attempt, eval_status=rec_["status"],
                    detail="artifact=%s eval=%s" % (stage["produces"], rec_["eval_id"]))
            if rec_["status"] == "PASS":
                ok, rs = cs.put_artifact(state, stage["produces"], artifact, sid)
                if not ok:
                    _fail_stage(state, sid, "; ".join(rs))
                    return {"outcome": "NEEDS_REVIEW", "stage": sid, "reasons": rs}
                arec = reg.register(state, stage["produces"], artifact, stage)
                tk.set_output(state, sid, arec["artifact_id"])
                tr.emit(state, "ARTIFACT_STORED", task_id=tid, skill=stage.get("skill"),
                        attempt=attempt, output_artifact=arec["artifact_id"],
                        detail="artifact_type=%s stage=%s" % (stage["produces"], sid))
                tr.emit(state, "SKILL_COMPLETED", task_id=tid, skill=stage.get("skill"),
                        attempt=attempt, output_artifact=arec["artifact_id"],
                        eval_status="PASS", duration_ms=tm.ms(), detail="stage=%s" % sid)
                if _needs_review(stage, artifact):
                    tk.set_status(state, sid, "NEEDS_REVIEW")
                    cs.record_event(state, "STAGE_NEEDS_REVIEW", stage=sid)
                    return {"outcome": "GATE", "stage": sid, "eval": rec_}
                tk.set_status(state, sid, "COMPLETED")
                cs.record_event(state, "STAGE_COMPLETED", stage=sid)
                return {"outcome": "OK", "stage": sid, "eval": rec_, "services": svc}
            failed = ev.failed_checks(rec_)
            reason = "EVAL_FAIL: " + "; ".join("%s(%s)" % (f["check_id"], f["message"])
                                               for f in failed)
        else:
            rec_ = None
            failed = [{"check_id": "execution", "message": "; ".join(map(str, errs))}]
            reason = "; ".join(map(str, errs)) or "execution produced no artifact"

        # ---- failure: repair or escalate ------------------------------------
        cs.record_event(state, "STAGE_FAILED", stage=sid, detail=reason)
        # spec §6: the trace must make the ROOT CAUSE visible, not just "ERROR".
        # A failed evaluation carries its check messages; an execution/service failure
        # carries the service error verbatim.
        tr.emit(state, "TASK_FAILED", task_id=tid, skill=stage.get("skill"),
                attempt=attempt, eval_status=("FAIL" if rec_ is not None else "ERROR"),
                detail=reason)
        if not enable_repair or attempt >= max_attempts:
            tr.emit(state, "REPAIR_EXHAUSTED", task_id=tid, skill=stage.get("skill"),
                    attempt=attempt,
                    detail="stage=%s budget=%s reason=%s"
                           % (sid, "exhausted" if enable_repair else "disabled", reason[:240]))
            cs.needs_review(state, sid, reason, failed_checks=failed,
                            repair_attempts=max(0, attempt - 1))
            tk.set_status(state, sid, "NEEDS_REVIEW", failure_reason=reason)
            return {"outcome": "NEEDS_REVIEW", "stage": sid, "reasons": [reason],
                    "failed_checks": failed}

        action = repair.plan(failed, eval_rules) if rec_ is not None else "RERUN_FROM_UPSTREAM"
        if action is None:
            tr.emit(state, "REPAIR_EXHAUSTED", task_id=tid, skill=stage.get("skill"),
                    attempt=attempt,
                    detail="stage=%s not_repairable reason=%s" % (sid, reason[:240]))
            cs.needs_review(state, sid, reason, failed_checks=failed,
                            repair_attempts=max(0, attempt - 1))
            tk.set_status(state, sid, "NEEDS_REVIEW", failure_reason=reason)
            return {"outcome": "NEEDS_REVIEW", "stage": sid, "reasons": [reason],
                    "failed_checks": failed}

        tr.emit(state, "REPAIR_STARTED", task_id=tid, skill=stage.get("skill"),
                attempt=attempt, detail="action=%s; failed=%s; reason=%s"
                % (action, ", ".join(f["check_id"] for f in failed), reason[:240]))
        inp = build_stage_input(state, stage)
        changed, detail = repair.apply(state, inp, action, eval_rules)
        tr.emit(state, "REPAIR_COMPLETED", task_id=tid, skill=stage.get("skill"),
                attempt=attempt, detail="action=%s changed=%s" % (action, changed))
        if not changed:
            tr.emit(state, "REPAIR_EXHAUSTED", task_id=tid, skill=stage.get("skill"),
                    attempt=attempt,
                    detail="stage=%s repair_ineffective reason=%s" % (sid, reason[:240]))
            cs.needs_review(state, sid, reason, failed_checks=failed,
                            repair_attempts=max(0, attempt - 1))
            tk.set_status(state, sid, "NEEDS_REVIEW", failure_reason=reason)
            return {"outcome": "NEEDS_REVIEW", "stage": sid, "reasons": [reason],
                    "failed_checks": failed}
        override = inp
        tk.set_task_status(state, sid, "REPAIRING")
        tk.record_repair(state, sid, failed, action, detail)


def _report(status, stopped_at, reasons, executed, state, **extra) -> dict:
    out = {
        "status": status,
        "stopped_at": stopped_at,
        "reasons": list(reasons),
        "executed": executed,
        "stages": cs.statuses(state),
        "state": state,
    }
    out.update(extra)
    return out


# --------------------------------------------------------------------------- #
# main run loop
# --------------------------------------------------------------------------- #
def run(state: dict, workflow: Optional[dict] = None, gate_policy: str = "stop",
        max_stages: int = 50, kb_dir: Optional[str] = None, enable_repair: bool = True,
        checkpoint_root: Optional[str] = None, orch_rules: Optional[dict] = None) -> dict:
    """Advance the case as far as the invariants, evals and gates allow."""
    workflow = workflow or load_workflow()
    eval_rules, repair_rules = _rules()
    orch_rules = orch_rules or load_orch_rules()
    if not state.get("tasks"):
        tk.init_tasks(state, workflow)
    if state.get("status") in (None, "PENDING"):
        cs.set_case_status(state, "RUNNING")

    executed, reasons = [], []

    # Step 4 P2: register a case directory so the trace mirrors to <case_dir>/trace.jsonl.
    if checkpoint_root:
        _cd = os.path.join(checkpoint_root, state["case_id"])
        tr.register_case(state["case_id"], _cd)
        tr.dump_jsonl(state, _cd)

    # Step 3: do not advance past the client facts if they are missing or conflicting.
    if state.get("waiting_for_user"):
        tr.emit(state, "CASE_WAITING", detail=state["waiting_for_user"].get("reason", "WAITING_FOR_USER"))
        return _report("WAITING_FOR_USER", state["waiting_for_user"].get("trigger_stage"),
                       [state["waiting_for_user"].get("reason", "WAITING_FOR_USER")],
                       executed, state)
    handoff = check_client_information(state, orch_rules)
    if handoff:
        cs.wait_for_user(state, handoff["reason"], trigger_stage="client-intake",
                         blocking_fields=[("%s.%s" % (b.get("profile"), b.get("field")))
                                          for b in handoff["blocking_fields"]],
                         conflicts=handoff["conflicts"],
                         next_questions=handoff["next_questions"])
        return _report("WAITING_FOR_USER", "client-intake", [handoff["reason"]],
                       executed, state)

    steps = 0
    while True:
        steps += 1
        if steps > max_stages:
            cs.set_case_status(state, "FAILED")
            return _report("FAILED", None, ["MAX_STAGES_EXCEEDED"], executed, state)

        sid = transitions.next_runnable(state, workflow)
        if sid is None:
            cs.set_case_status(state, "COMPLETED")
            tr.emit(state, "CASE_COMPLETED", detail="stages=%d" % len(executed))
            if checkpoint_root:
                from . import checkpoint as cp
                cp.save(state, checkpoint_root, None)
            return _report("COMPLETED", None, [], executed, state)

        stage = transitions.stage_by_id(workflow, sid)
        rec = state["stages"][sid]

        if rec["status"] == "NEEDS_REVIEW":
            if checkpoint_root:
                from . import checkpoint as cp
                cp.save(state, checkpoint_root, sid)
            if gate_policy == "auto":
                approve(state, sid)
                continue
            cs.set_case_status(state, "PAUSED_NEEDS_REVIEW")
            tr.emit(state, "CASE_NEEDS_REVIEW", task_id=state["stages"][sid].get("task_id"),
                    skill=stage.get("skill"), detail="gate: %s" % sid)
            return _report("PAUSED_NEEDS_REVIEW", sid,
                           ["AWAITING_HUMAN_REVIEW: %s" % sid], executed, state)

        if rec["status"] == "FAILED":
            cs.set_case_status(state, "FAILED")
            return _report("FAILED", sid, rec.get("notes", []), executed, state)

        ok, rs = transitions.can_run(state, stage)
        if not ok:
            cs.record_event(state, "GUARD_REJECTED", stage=sid, detail="; ".join(rs))
            cs.set_case_status(state, "BLOCKED")
            return _report("BLOCKED", sid, rs, executed, state)

        if stage.get("executor") == "provided":
            cs.set_case_status(state, "BLOCKED")
            return _report("BLOCKED", sid,
                           ["MISSING_PROVIDED_ARTIFACT: %s (executor=provided, no seed)"
                            % (stage.get("produces"))], executed, state)

        result = _execute_stage(state, workflow, stage, kb_dir=kb_dir,
                                eval_rules=eval_rules, repair_rules=repair_rules,
                                enable_repair=enable_repair)

        if result["outcome"] == "OK":
            executed.append({"stage": sid, "eval": result.get("eval", {}).get("eval_id")})
            if checkpoint_root:
                from . import checkpoint as cp
                cp.save(state, checkpoint_root, sid)
            continue

        if result["outcome"] == "GATE":
            executed.append({"stage": sid, "gate": True})
            if checkpoint_root:
                from . import checkpoint as cp
                cp.save(state, checkpoint_root, sid)
            if gate_policy == "auto":
                approve(state, sid)
                continue
            cs.set_case_status(state, "PAUSED_NEEDS_REVIEW")
            tr.emit(state, "CASE_NEEDS_REVIEW", task_id=state["stages"][sid].get("task_id"),
                    skill=stage.get("skill"), detail="gate: %s" % sid)
            return _report("PAUSED_NEEDS_REVIEW", sid,
                           ["AWAITING_HUMAN_REVIEW: %s" % sid], executed, state)

        # NEEDS_REVIEW after exhausted repairs
        if checkpoint_root:
            from . import checkpoint as cp
            cp.save(state, checkpoint_root, sid)
        cs.set_case_status(state, "NEEDS_REVIEW")
        tr.emit(state, "CASE_NEEDS_REVIEW", task_id=state["stages"][sid].get("task_id"),
                skill=stage.get("skill"), detail="repair_exhausted: %s" % sid)
        return _report("NEEDS_REVIEW", sid, result.get("reasons", []), executed, state,
                       review=state.get("review"))
