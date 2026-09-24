"""Phase 27 controlled-internal-pilot runner (machine side).

Runs each pilot case through the PRODUCTIONIZED path on the frozen
phase26c baseline: RunControl (lifecycle+deadline) + RunBudget +
AgentTaskWorker + the real 9-skill pipeline, with mechanical
operator approvals to carry each case past its human gate.

IMPORTANT (honesty contract):
- The approvals issued here are MECHANICAL CONTINUATIONS by the
  pilot operator tooling (audited to queue_ops_events with actor
  'pilot-operator'). They are NOT business human review. Every
  case's business review_status stays PENDING_HUMAN_REVIEW until
  the Owner completes the review protocol (pilot-review-template).
- Metrics captured are machine-observable facts only. LLM usage on
  this path is a REAL zero (deterministic skills); cost stays
  UNKNOWN (no LLM metering, per PA-26C5-P1-03 nothing sensitive is
  sent to any provider anyway).
- Baseline discipline: this tool changes NO runtime/test code. It
  reads the frozen baseline and writes pilot evidence only.

Usage:  python docs/production/pilot/tools/run_pilot.py [--case C01]
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                    "..", "..", "..", ".."))
sys.path.insert(0, REPO)

BENCH = os.path.join(REPO, "evals", "agent-benchmark")
OUT = os.path.join(REPO, "docs", "production", "pilot", "data")
RUNS = os.path.join(REPO, "tmp", "pilot27")

PG_PASSWORD = ""
try:
    PG_PASSWORD = open(
        r"C:\Users\aubor\AppData\Local\Temp\pg_cred.txt"
    ).read().strip().split("=", 1)[1]
except (FileNotFoundError, IndexError):
    pass

RUNTIME_VERSION = "phase26c-productionization-v1.0 (c7ed9c6)"

# ---- case matrix (C01..C12, all SYNTHETIC) ------------------------------ #
CASES = [
    {"id": "C01", "case_type": "child_protection",
     "desc": "已婚二孩,儿童+家庭责任聚焦",
     "mutations": [
         {"op": "set_value", "profile": "family_profile",
          "field": "children", "value": "2孩(3岁/8岁)"},
         {"op": "keep_requirements",
          "requirement_ids": ["REQ-LIFE", "REQ-CI", "REQ-MED"]}]},
    {"id": "C02", "case_type": "single_adult",
     "desc": "单身成年人,基础保障",
     "mutations": [
         {"op": "set_value", "profile": "family_profile",
          "field": "marital_status", "value": "未婚"},
         {"op": "set_value", "profile": "family_profile",
          "field": "children", "value": "无"},
         {"op": "set_value", "profile": "financial_profile",
          "field": "annual_income", "value": "25万"},
         {"op": "set_value", "profile": "financial_profile",
          "field": "mortgage", "value": "无"},
         {"op": "keep_requirements",
          "requirement_ids": ["REQ-CI", "REQ-MED"]}]},
    {"id": "C03", "case_type": "married_no_child",
     "desc": "已婚无子,储蓄+医疗",
     "mutations": [
         {"op": "set_value", "profile": "family_profile",
          "field": "children", "value": "无"},
         {"op": "keep_requirements",
          "requirement_ids": ["REQ-MED", "REQ-CI", "REQ-SAV"]}]},
    {"id": "C04", "case_type": "dual_income",
     "desc": "双收入家庭(高收入)",
     "mutations": [
         {"op": "set_value", "profile": "financial_profile",
          "field": "annual_income", "value": "120万(双收入)"}]},
    {"id": "C05", "case_type": "mortgage_family",
     "desc": "高额房贷家庭",
     "mutations": [
         {"op": "set_value", "profile": "financial_profile",
          "field": "mortgage", "value": "350万"},
         {"op": "set_value", "profile": "financial_profile",
          "field": "annual_income", "value": "60万"},
         {"op": "keep_requirements",
          "requirement_ids": ["REQ-LIFE", "REQ-ACC"]}]},
    {"id": "C06", "case_type": "existing_insurance",
     "desc": "已有较全保险(观察缺口收敛)",
     "mutations": [
         {"op": "set_value", "profile": "existing_protection",
          "field": "existing_insurance",
          "value": "重疾险50万+百万医疗+定期寿险100万"}]},
    {"id": "C07", "case_type": "underinsured",
     "desc": "配置明显不足(仅意外险10万)",
     "mutations": [
         {"op": "set_value", "profile": "existing_protection",
          "field": "existing_insurance", "value": "仅意外险10万"}]},
    {"id": "C08", "case_type": "incomplete_info",
     "desc": "信息不完整:收入/预算/已有保险 UNKNOWN",
     "mutations": [
         {"op": "set_unknown", "profile": "financial_profile",
          "field": "annual_income", "reason": "客户未提供"},
         {"op": "set_unknown", "profile": "financial_profile",
          "field": "insurance_budget", "reason": "客户未提供"},
         {"op": "set_unknown", "profile": "existing_protection",
          "field": "existing_insurance", "reason": "客户未提供"}]},
    {"id": "C09", "case_type": "evidence_sensitive_gap0",
     "desc": "R4 缺口≈0(已有覆盖足额)——观察下游行为",
     "mutations": [
         {"op": "set_risk", "risk_id": "R4-001",
          "field": "coverage_assessment.protected_amount",
          "value": 3000000},
         {"op": "keep_requirements",
          "requirement_ids": ["REQ-LIFE"]}]},
    {"id": "C10", "case_type": "complex_family",
     "desc": "三代同堂+3孩复杂责任",
     "mutations": [
         {"op": "set_value", "profile": "family_profile",
          "field": "children", "value": "3孩(2岁/7岁/12岁)"},
         {"op": "set_value", "profile": "responsibility_profile",
          "field": "economic_responsibility",
          "value": "三代同堂,唯一经济来源+赡养4位老人"}]},
    {"id": "C11", "case_type": "knowledge_unavailable",
     "desc": "Knowledge 不可用(kb-empty)——期望 fail closed",
     "kb": "empty",
     "mutations": [
         {"op": "keep_requirements",
          "requirement_ids": ["REQ-CI"]}]},
    {"id": "C12", "case_type": "no_requirements",
     "desc": "需求为空(keep [])——观察空需求行为",
     "mutations": [
         {"op": "keep_requirements", "requirement_ids": []}]},
]


def _load_benchmark():
    spec = importlib.util.spec_from_file_location(
        "run_agent_benchmark",
        os.path.join(BENCH, "run_agent_benchmark.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(only=None):
    if not PG_PASSWORD:
        print("RESULT: FAIL (no PG credential)")
        return 1
    os.environ["AGENT_PG_PASSWORD"] = PG_PASSWORD
    bm = _load_benchmark()
    from runtime.state.pg import PostgresStore
    from runtime.queue import (AgentTaskWorker, QueueOps, RunBudget,
                               RunControl, TaskQueueStore,
                               make_agent_executor)
    from runtime import orchestrator as orch

    manifest = json.load(open(os.path.join(BENCH, "manifest.json"),
                              encoding="utf-8"))
    base = json.load(open(os.path.join(REPO, manifest["seeds_file"]),
                          encoding="utf-8"))
    wf = orch.load_workflow()
    kb_empty = os.path.join(REPO, manifest["empty_kb"])

    store = TaskQueueStore(PostgresStore().connect)
    store.init_schema()
    budget = RunBudget(PostgresStore().connect)
    rc = RunControl(store, PostgresStore().connect, budget=budget)
    os.makedirs(OUT, exist_ok=True)
    shutil.rmtree(RUNS, ignore_errors=True)
    os.makedirs(RUNS, exist_ok=True)

    # pilot workspace cleanup (pilot-scoped prefixes only)
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM queue_tasks WHERE task_type "
                        "LIKE 'pilot27%'")
            cur.execute("DELETE FROM agent_runs WHERE run_id LIKE "
                        "'%pilot27%'")
            cur.execute("DELETE FROM agent_run_budgets WHERE run_id "
                        "LIKE '%pilot27%'")
            cur.execute("DELETE FROM agent_run_budget_events WHERE "
                        "run_id LIKE '%pilot27%'")
            cur.execute("DELETE FROM queue_ops_events WHERE task_id "
                        "LIKE 'pilot27-%'")

    results = []
    for case in CASES:
        if only and case["id"] != only:
            continue
        cid = "pilot27-%s" % case["id"]
        run_root = os.path.join(RUNS, case["id"])
        os.makedirs(run_root, exist_ok=True)
        ops = QueueOps(store, PostgresStore().connect,
                       run_root=run_root, run_control=rc)
        seeds = bm.apply_mutations(
            copy.deepcopy(base["artifacts"]), case.get("mutations", []))
        kb_dir = kb_empty if case.get("kb") == "empty" else None
        t0 = time.time()
        rc.submit_run(task_id=cid, run_id="run-" + cid,
                      deadline_seconds=600,
                      task_type="pilot27t", case_id=case["id"],
                      trace_id="trc-pilot27-" + case["id"])
        budget.configure("run-" + cid, max_task_attempts=8,
                         max_repair_attempts=12, max_llm_calls=0)
        exec_ = make_agent_executor(workflow=wf, case_id=case["id"],
                                    seeds=seeds, run_root=run_root,
                                    kb_dir=kb_dir)
        w = AgentTaskWorker(store, "pilot-worker", exec_,
                            run_control=rc, lease_seconds=120,
                            heartbeat_every_s=30,
                            task_types=["pilot27t"])

        seq, approvals, outcome = [], [], None
        for step in range(12):
            out = w.run_once()
            if out is None:
                seq.append("IDLE")
                break
            outcome = out.get("outcome")
            seq.append(outcome)
            if outcome == "DEFERRED_WAITING":
                row = store.get(cid)
                stage = (row.get("retry_reason")
                         or "@?").split("@", 1)[-1]
                # mechanical continuation (NOT business review)
                ops.approve_and_resume(
                    ("pilot-operator", "OPERATOR"), cid)
                approvals.append({"step": step, "stage": stage,
                                  "actor": "pilot-operator",
                                  "kind": "MECHANICAL"})
                continue
            if outcome in ("FAILED", "FAILED_REQUEUED",
                           "STALE_REJECTED", "RUN_TIMED_OUT",
                           "RUN_BUDGET_EXCEEDED",
                           "RUN_TERMINAL_REJECTED"):
                break
            if outcome == "SUCCEEDED":
                break
        elapsed = round(time.time() - t0, 2)
        trow, rrow = store.get(cid), rc.get_run("run-" + cid)
        brow = budget.snapshot("run-" + cid) or {}
        result = {
            "pilot_case_id": case["id"],
            "case_type": case["case_type"],
            "data_type": "SYNTHETIC",
            "desc": case["desc"],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime()),
            "runtime_version": RUNTIME_VERSION,
            "kb": case.get("kb"),
            "outcomes": seq,
            "final_task_status": trow["status"] if trow else None,
            "final_run_state": rrow["state"] if rrow else None,
            "terminal_reason": (rrow or {}).get("terminal_reason"),
            "attempt": (trow or {}).get("attempt"),
            "result_status": ((trow or {}).get("result") or {})
                             .get("status"),
            "budget": {k: brow.get(k) for k in
                       ("task_attempts_used", "repair_attempts_used",
                        "llm_calls_used")},
            "mechanical_approvals": approvals,
            "elapsed_s": elapsed,
            "review_status": "PENDING_HUMAN_REVIEW",
        }
        results.append(result)
        print("[%s] %s task=%s run=%s attempts=%s repairs=%s %.1fs"
              % (case["id"], "->".join(seq[:4]),
                 result["final_task_status"],
                 result["final_run_state"], result["attempt"],
                 result["budget"]["repair_attempts_used"], elapsed))
        with store._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM queue_tasks WHERE task_id=%s",
                            (cid,))
                cur.execute("DELETE FROM agent_runs WHERE run_id=%s",
                            ("run-" + cid,))
                cur.execute("DELETE FROM agent_run_budgets WHERE "
                            "run_id=%s", ("run-" + cid,))
                cur.execute("DELETE FROM agent_run_budget_events "
                            "WHERE run_id=%s", ("run-" + cid,))

    json.dump({"runtime_version": RUNTIME_VERSION,
               "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime()),
               "cases": results},
              open(os.path.join(OUT, "pilot-machine-results.json"),
                   "w", encoding="utf-8"), ensure_ascii=False,
              indent=1)
    print("wrote", os.path.join(OUT, "pilot-machine-results.json"))
    return 0


if __name__ == "__main__":
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--case="):
            only = a.split("=", 1)[1]
    sys.exit(main(only))
