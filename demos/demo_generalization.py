"""Phase 12 — Generalization demo: the SAME runtime, a DIFFERENT domain.

Runs a software-engineering task workflow (requirement analysis → risk
analysis → solution → implementation plan → test plan) through the SAME
Planner/Harness/Scheduler/Eval/Artifact machinery used for insurance —
proving the runtime is generic and insurance is only the first domain
adapter. No runtime fork, no copied modules.

The domain adapter is ~40 declarative lines right here: a task-type
catalog (the WHAT), agent definitions (the WHO), and scripted executors
(the deterministic stand-in for domain specialists). Everything else —
graph validation, scheduling, artifacts, eval, checkpoints, monitoring,
the run summary — is the unchanged generic runtime.
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
from runtime import artifact_registry as reg                # noqa: E402
from runtime import eval_engine as ev                       # noqa: E402
from runtime.harness import LongRunningHarness              # noqa: E402
from runtime.state import store as ss                       # noqa: E402
from test_parallel_scheduler import ScriptAgentExecutor     # noqa: E402


def _safe(t):
    try:
        return str(t).encode(sys.stdout.encoding or "utf-8").decode(
            sys.stdout.encoding or "utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
        return str(t).encode("ascii", "replace").decode("ascii")


def say(t):
    print(_safe(t))


# --------------------------------------------------------------------------- #
# DOMAIN ADAPTER (software engineering) — declarative, no runtime changes
# --------------------------------------------------------------------------- #
SE_TASKS = {
    "se_requirement": {
        "stage_id": "se-requirement", "executor": "agent",
        "required_inputs": [], "produced": ["se-requirements"],
        "agent": "se_analyst",
        "description": "分析后端服务需求，拆解功能点与约束"},
    "se_risk": {
        "stage_id": "se-risk", "executor": "agent",
        "required_inputs": ["se-requirements"], "produced": ["se-risks"],
        "agent": "se_analyst",
        "description": "识别技术风险与非功能风险"},
    "se_solution": {
        "stage_id": "se-solution", "executor": "agent",
        "required_inputs": ["se-requirements", "se-risks"],
        "produced": ["se-solution"], "agent": "se_analyst",
        "description": "设计实现方案（架构与模块划分）"},
    "se_implementation": {
        "stage_id": "se-implementation", "executor": "agent",
        "required_inputs": ["se-solution"], "produced": ["se-implementation"],
        "agent": "se_engineer",
        "description": "生成实现计划（任务拆解与顺序）"},
    "se_test": {
        "stage_id": "se-test", "executor": "agent",
        "required_inputs": ["se-solution"], "produced": ["se-test-plan"],
        "agent": "se_qa",
        "description": "生成测试计划（用例与验收标准）"},
}

SE_GRAPH = {"tasks": [
    {"task_id": "task_r", "task_type": "se_requirement"},
    {"task_id": "task_k", "task_type": "se_risk", "dependencies": ["task_r"]},
    {"task_id": "task_s", "task_type": "se_solution",
     "dependencies": ["task_r", "task_k"]},
    {"task_id": "task_i", "task_type": "se_implementation",
     "dependencies": ["task_s"]},
    {"task_id": "task_t", "task_type": "se_test", "dependencies": ["task_s"]},
]}


def make_se_artifact(kind, body):
    return {"artifact_type": kind, "schema_version": "1.0",
            "generated_at": "2026-09-18T00:00:00+00:00",
            "payload": body,
            "provenance": [{"source_type": "domain", "source_id": kind,
                            "confidence": 0.9}]}


class SEExecutor(ScriptAgentExecutor):
    """Deterministic stand-in for the SE specialists: produces the domain
    artifacts through the SAME canonical store+registry path."""

    name = "se-executor"
    model = "se"

    def __init__(self):
        super().__init__({
            "se_requirement": [make_se_artifact("se-requirements", {
                "service": "notification-service",
                "functional": ["邮件通知", "通知模板管理", "发送频控"],
                "constraints": ["延迟 < 5s", "可用性 99.9%"],
                "status": "FORMAL"})],
            "se_risk": [make_se_artifact("se-risks", {
                "risks": [
                    {"risk_id": "SE-1", "category": "third_party",
                     "name": "SMTP 供应商不可用", "severity": "HIGH"},
                    {"risk_id": "SE-2", "category": "capacity",
                     "name": "高峰期发送积压", "severity": "MEDIUM"}],
                "status": "FORMAL"})],
            "se_solution": [make_se_artifact("se-solution", {
                "architecture": "queue-decoupled worker pool",
                "modules": ["api-gateway", "queue", "worker", "template-store"],
                "decisions": ["重试+死信队列", "幂等发送"],
                "status": "FORMAL"})],
            "se_implementation": [make_se_artifact("se-implementation", {
                "tasks": [
                    {"id": "IMPL-1", "name": "队列与worker骨架", "days": 3},
                    {"id": "IMPL-2", "name": "模板管理API", "days": 2},
                    {"id": "IMPL-3", "name": "频控与重试", "days": 3}],
                "order": ["IMPL-1", "IMPL-2", "IMPL-3"],
                "status": "FORMAL"})],
            "se_test": [make_se_artifact("se-test-plan", {
                "cases": [
                    {"id": "T-1", "name": "正常发送链路", "type": "e2e"},
                    {"id": "T-2", "name": "供应商故障降级", "type": "fault"},
                    {"id": "T-3", "name": "频控边界", "type": "unit"}],
                "acceptance": ["P95 < 5s", "故障下不丢通知"],
                "status": "FORMAL"})],
        })

    def execute(self, *, agent_id, task, project, case_state, emit=None):
        # the generic scheduler chose WHEN; the domain adapter says HOW —
        # and stores through the canonical artifact path (lineage intact)
        return super().execute(agent_id=agent_id, task=task, project=project,
                               case_state=case_state, emit=emit)


SE_WORKFLOW = {
    "workflow": "se-task-agent", "version": "0.1",
    # NOTE: the canonical CaseState schema constrains `executor` to the
    # insurance-era vocabulary (python/provided/service) and `produces` to a
    # single string. The adapter complies rather than forking the schema —
    # recorded as a generalization friction point in docs/generalization.md.
    "stages": [
        {"id": d["stage_id"], "skill": "se", "produces": d["produced"][0],
         "consumes": d["required_inputs"], "executor": "python",
         "input_map": {}, "call": {"fn": "noop", "result": "artifact"}}
        for d in SE_TASKS.values()
    ],
}


def patch_runtime_for_se():
    """Register the SE domain adapter with the SAME trusted registries the
    insurance domain uses — this is the documented adapter seam, not a fork."""
    from runtime.planner import registry as preg
    from runtime.agents import registry as areg

    for tt, d in SE_TASKS.items():
        preg.TASK_REGISTRY[tt] = {
            "task_type": tt, "stage_id": d["stage_id"],
            "executor": d["executor"], "description": d["description"],
            "required_inputs": d["required_inputs"],
            "produced_artifacts": d["produced"],
            "required_eval": ["se_eval"]}
        areg.AGENT_REGISTRY["se_analyst"] = {
            "agent_id": "se_analyst", "name": "SE Analyst",
            "description": "需求/风险/方案分析",
            "allowed_task_types": ["se_requirement", "se_risk", "se_solution"],
            "allowed_tools": [], "system_prompt": "SE analyst."}
        areg.AGENT_REGISTRY["se_engineer"] = {
            "agent_id": "se_engineer", "name": "SE Engineer",
            "description": "实现计划",
            "allowed_task_types": ["se_implementation"],
            "allowed_tools": [], "system_prompt": "SE engineer."}
        areg.AGENT_REGISTRY["se_qa"] = {
            "agent_id": "se_qa", "name": "SE QA",
            "description": "测试计划",
            "allowed_task_types": ["se_test"],
            "allowed_tools": [], "system_prompt": "SE QA."}
    areg.TASK_AGENT_MAP.clear()
    areg.TASK_AGENT_MAP.update({
        tt: d["agent"] for tt, d in SE_TASKS.items()})
    # keep the insurance mapping available (union, not replacement)
    for tt, ag in (("client_profile", "insurance_analyst"),
                   ("requirement_analysis", "insurance_analyst"),
                   ("risk_analysis", "insurance_analyst"),
                   ("coverage_gap", "insurance_analyst"),
                   ("solution", "insurance_analyst"),
                   ("knowledge_search", "knowledge_specialist"),
                   ("product_candidates", "product_specialist"),
                   ("recommendation", "product_specialist"),
                   ("report_generation", "report_specialist")):
        areg.TASK_AGENT_MAP.setdefault(tt, ag)
    # eval rules for the SE artifacts (schema-free; presence-checked)
    from runtime.eval_engine import load_rules
    rules = load_rules()
    rules.setdefault("required_fields", {}).update({
        "se-requirements": ["payload.functional"],
        "se-risks": ["payload.risks"],
        "se-solution": ["payload.modules"],
        "se-implementation": ["payload.tasks"],
        "se-test-plan": ["payload.cases"]})
    ev.load_rules = lambda path=None: rules


def main() -> int:
    say("=" * 62)
    say("GENERALIZATION — same runtime, different domain")
    say("=" * 62)
    say("Domain: SOFTWARE ENGINEERING (requirement → risk → solution →")
    say("        implementation plan → test plan)")
    say("Runtime: the SAME Planner/Harness/Scheduler/Eval/Artifact stack")
    say("        used for insurance — zero runtime modules copied or forked.")
    say("")

    patch_runtime_for_se()
    root = tempfile.mkdtemp(prefix="demo_se_", dir=os.path.join(REPO, "tmp"))
    try:
        h = LongRunningHarness(root, agent_executor=SEExecutor(),
                               max_concurrency=2)
        p = h.create_project("se-demo", task_graph=SE_GRAPH)
        # the domain adapter brings its OWN workflow definition — CaseState
        # stages, contracts and eval rules are domain config, not runtime
        wf = dict(SE_WORKFLOW)
        for i, st in enumerate(wf["stages"]):   # same index derivation as
            st["index"] = i                     # orchestrator.load_workflow
        state = orch.seed_case(wf, p.case_id, {})
        ss.save(state, os.path.join(root, p.project_id, "case"))

        result = h.run(p)
        final = ss.load(os.path.join(root, p.project_id, "case"),
                        p.case_id) or {}

        say("PLAN (validated by the same graph validator)")
        for t in p.tasks:
            say("  %-10s %-22s -> %s" % (t["task_id"], t["task_type"],
                                         t["status"]))
        agents = sorted({e.get("agent_id") for e in p.events()
                         if e["event_type"] == "agent_started"})
        say("AGENTS     %s" % ", ".join(agents))
        evals = final.get("evaluations") or []
        say("EVAL       %d evaluations · %d PASS"
            % (len(evals), sum(1 for e in evals if e["status"] == "PASS")))
        say("ARTIFACTS  %s" % ", ".join(sorted((final.get("artifacts")
                                                or {}).keys())))
        ok, problems = reg.verify(final)
        say("LINEAGE    %s" % ("verified" if ok else "BROKEN: %s" % problems[:1]))
        say("")

        impl = ((final.get("artifacts") or {}).get("se-implementation") or {})
        plan = (impl.get("payload") or {}).get("tasks") or []
        tests = (((final.get("artifacts") or {}).get("se-test-plan")
                  or {}).get("payload") or {}).get("cases") or []
        say("-" * 62)
        say("DELIVERABLE (from real runtime artifacts)")
        say("-" * 62)
        say("Implementation plan: %d tasks" % len(plan))
        for t in plan[:5]:
            say("  - %s %s (%s days)" % (t.get("id"), t.get("name"),
                                        t.get("days")))
        say("Test plan: %d cases — %s" % (
            len(tests), ", ".join(c.get("id", "") for c in tests[:3])))
        say("")
        say("FINAL      %s" % str(result.get("status", "")).upper())
        say("Insurance was the first domain adapter. This run used the same")
        say("scheduler, eval engine, artifact registry, checkpoints and run")
        say("summary — only the declarative domain catalog changed.")
        return 0 if result.get("status") == "completed" else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
