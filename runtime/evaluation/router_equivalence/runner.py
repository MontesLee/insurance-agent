"""B4 gate runner (Phase 28.B4).

Runs one golden case TWICE through the real server (in-process, fresh
RunManager/EventBus/run_root per side — isolated), captures the six
observation dimensions, and judges via the comparator.

    legacy side    ALL slice flags forced OFF (the pre-migration path)
    candidate side case.flags applied over the OFF base

Isolation: fresh server objects per side; environment scoped and
restored; default knowledge service reset; deterministic scripted
providers (FakeLLM). The runner NEVER flips a flag default, never
touches the artifact registry write path, and restores every piece of
global state it touches.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from runtime.evaluation.router_equivalence import comparator
from runtime.evaluation.router_equivalence.models import (
    CaseResult, GateReport, GoldenCase, SideCapture)
from runtime.evaluation.router_equivalence import normalizer as nm

BASE_OFF = {
    "INSURANCE_AGENT_QA_SLICE": "0",
    "INSURANCE_AGENT_PRODUCT_QA_SLICE": "0",
    "INSURANCE_AGENT_PLAN_SLICE": "0",
    "INSURANCE_AGENT_INTENT_LLM": "0",
    "INSURANCE_AGENT_ROUTER_AUTHORITY": "slices",
    # HERMETIC: never read the repo .env — a configured LLM_FAST_MODEL
    # would silently replace the scripted provider with a LIVE model and
    # make the gate nondeterministic (found the hard way: pytest sets
    # this via tests/_common, a bare CLI run does not)
    "INSURANCE_AGENT_NO_DOTENV": "1",
}


class _DeadKnowledgeProvider:
    name = "dead"

    def search(self, query, filters=None, top_k=None):
        from knowledge.provider.base import ProviderUnavailable
        raise ProviderUnavailable("golden-case: knowledge backend down")


def _fake_script(case: GoldenCase) -> list:
    """JSON script items -> FakeLLMProvider script protocol."""
    from runtime.agent.model import LLMResponse, ToolCall
    out = []
    for item in case.script:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and "error" in item:
            out.append(RuntimeError(str(item["error"])[:120]))
        elif isinstance(item, dict) and "tool" in item:
            out.append((item["tool"], dict(item.get("args") or {})))
        else:
            out.append(str(item))
    return out


def run_side(case: GoldenCase, side: str, root: str) -> SideCapture:
    from fastapi.testclient import TestClient
    from runtime.event_bus import EventBus
    from runtime.server import RunManager, create_app
    from runtime.agent import FakeLLMProvider

    env_backup = {k: os.environ.get(k) for k in BASE_OFF}
    service_injected = False
    try:
        for k, v in BASE_OFF.items():
            os.environ[k] = v
        if side == "candidate":
            for k, v in (case.flags or {}).items():
                os.environ[k] = str(v)
        if case.service == "dead":
            from knowledge.service import (KnowledgeService,
                                           set_default_service)
            set_default_service(KnowledgeService(
                provider=_DeadKnowledgeProvider()))
            service_injected = True

        bus = EventBus()
        mgr = RunManager(bus=bus, run_root=root)
        mgr.agent_provider = FakeLLMProvider(_fake_script(case))
        client = TestClient(create_app(mgr))

        chat_id = "chat_%s_%s" % (case.case_id, side)
        mgr.chats.get_or_create(chat_id)
        for m in case.context or []:
            mgr.chats.add_user_message(chat_id, str(m))

        resp = client.post("/api/chats/%s/messages" % chat_id,
                           json={"text": case.message})
        cap = SideCapture(side=side, run_id="")
        if resp.status_code != 200:
            cap.error = "create run -> %s %s" % (resp.status_code,
                                                 resp.text[:200])
            return cap
        cap.run_id = resp.json()["run_id"]

        deadline = time.time() + 120.0
        run = {}
        while time.time() < deadline:
            run = client.get("/api/runs/%s" % cap.run_id).json()
            if run.get("status") not in ("queued", "running", None):
                break
            time.sleep(0.05)
        cap.status = run.get("status", "")

        ev = client.get("/api/runs/%s/events" % cap.run_id).json()
        cap.events = ev.get("events", [])

        for summary in (mgr.artifacts_of(cap.run_id) or []):
            detail = mgr.artifact_detail(cap.run_id,
                                         summary["artifact_type"])
            if detail is not None:
                cap.artifacts.append(nm.normalize(detail))
        # deterministic comparison order: artifacts_of sorts by the RANDOM
        # artifact_id suffix — comparing that order is a coin flip. The
        # artifact_type is unique per run, so type-order is stable.
        cap.artifacts.sort(key=lambda a: str(a.get("artifact_type", "")))

        qa_path = os.path.join(mgr.run_root, cap.run_id,
                               "qa-answer-context.json")
        if os.path.isfile(qa_path):
            import json as _json
            with open(qa_path, encoding="utf-8") as fh:
                cap.qa_context = _json.load(fh)

        view = (mgr.chats.view(chat_id) or {}).get("messages", [])
        cap.chat_messages = [m for m in view
                             if m.get("run_id") in (None, cap.run_id)]

        from runtime.intent import shadow as shadow_mod
        for rec in shadow_mod.iter_records():
            if rec.get("run_id") == cap.run_id:
                cap.shadow_record = rec
                break
        return cap
    finally:
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if service_injected:
            from knowledge.service import reset_default_service
            reset_default_service()


def run_case(case: GoldenCase, base_root: str) -> CaseResult:
    legacy = run_side(case, "legacy",
                      os.path.join(base_root, case.case_id, "legacy"))
    candidate = run_side(case, "candidate",
                         os.path.join(base_root, case.case_id, "cand"))
    result = CaseResult(case_id=case.case_id, verdict="PASS")
    for cap in (legacy, candidate):
        if cap.error:
            result.mismatches.append(
                ("execution_difference", "%s side failed: %s"
                 % (cap.side, cap.error)))
    if not result.mismatches:
        result.mismatches = comparator.compare(case, legacy, candidate)
    # self-equivalence annotation: until M3 ships a plan slice, E1
    # candidates run the legacy path — recorded, never hidden
    if (case.equivalence_class == "E1"
            and (candidate.shadow_record or {}).get("actual_execution")
            == "existing-agent"):
        result.notes.append("no candidate path yet (plan slice = M3); "
                            "equivalence trivially held")
    result.verdict = "RED" if result.mismatches else "PASS"
    return result


def run_gate(cases=None, base_root: Optional[str] = None) -> GateReport:
    from datetime import datetime, timezone
    if cases is None:
        from runtime.evaluation.router_equivalence.models import load_cases
        cases = load_cases()
    base_root = base_root or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))), "tmp", "b4-gate")
    report = GateReport(generated_at=datetime.now(
        timezone.utc).isoformat())
    for case in cases:
        report.results.append(run_case(case, base_root))
    return report
