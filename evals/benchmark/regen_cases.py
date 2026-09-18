# One-shot: regenerate all benchmark case JSONs (kept for reproducibility).
import json, os

CDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases")

T0 = {"task_id": "task_0", "task_type": "client_profile"}

def chain(with_product=True):
    t = [T0,
      {"task_id": "task_1", "task_type": "requirement_analysis", "dependencies": ["task_0"]},
      {"task_id": "task_2", "task_type": "risk_analysis", "dependencies": ["task_0", "task_1"]},
      {"task_id": "task_3", "task_type": "coverage_gap", "dependencies": ["task_0", "task_1", "task_2"]},
      {"task_id": "task_4", "task_type": "solution", "dependencies": ["task_1", "task_2", "task_3"]}]
    if with_product:
        t.append({"task_id": "task_5", "task_type": "product_candidates",
                  "dependencies": ["task_0", "task_3", "task_4"]})
    t.append({"task_id": "task_6", "task_type": "report_generation",
              "dependencies": ["task_0", "task_1", "task_2"] + (["task_5"] if with_product else [])})
    return t

def v2_drop(mid, report_extra=None):
    """v2: full chain minus the failing task; report rerouted. Dropping the
    solution task also drops product_candidates — the validator's artifact
    contract (product requires solution-plan) would reject anything else."""
    tasks = [dict(T0),
      {"task_id": "task_1", "task_type": "requirement_analysis", "dependencies": ["task_0"]},
      {"task_id": "task_2", "task_type": "risk_analysis", "dependencies": ["task_0", "task_1"]},
      {"task_id": "task_3", "task_type": "coverage_gap", "dependencies": ["task_0", "task_1", "task_2"]}]
    deps = ["task_0", "task_1", "task_2"]
    if mid == "task_5":
        tasks.append({"task_id": "task_4", "task_type": "solution",
                      "dependencies": ["task_1", "task_2", "task_3"]})
        deps = ["task_0", "task_1", "task_2", "task_4"]
    # mid == task_4 (solution failed): drop solution AND product — the
    # report still satisfies its contract from task_0/1/2
    tasks.append({"task_id": "task_6", "task_type": "report_generation",
                  "dependencies": deps})
    return tasks

FULL_SCRIPTS = {"task_0": "profile", "task_1": "req", "task_2": "risk",
                "task_3": "coverage_gap", "task_4": "solution",
                "task_5": "product", "task_6": "report"}

cases = [
 {"case_id": "B001", "name": "basic_advisory", "category": "happy_path",
  "description": "Full advisory happy path through four specialist agents; artifacts, lineage, evals and checkpoints verified.",
  "input": {"graph": chain(), "scripts": FULL_SCRIPTS},
  "expected": {"terminal_status": "completed",
    "required_agents": ["insurance_analyst", "product_specialist", "report_specialist"],
    "required_artifacts": ["client-profile", "requirement-analysis", "risk-assessment",
                           "coverage-gap-analysis", "solution-plan", "product-candidates",
                           "insurance-report"],
    "required_events": ["task_completed", "checkpoint_created"],
    "forbidden_events": ["replan_triggered", "approval_waiting"],
    "max_repairs": 0, "graph_revision": 1}},

 {"case_id": "B002", "name": "missing_information", "category": "missing_information",
  "description": "Client facts are insufficient: the intake agent refuses to fabricate a profile — the case fails closed and downstream never runs on invented facts.",
  "input": {"graph": [T0,
      {"task_id": "task_1", "task_type": "requirement_analysis", "dependencies": ["task_0"]},
      {"task_id": "task_2", "task_type": "report_generation",
       "dependencies": ["task_0", "task_1"]}],
    "scripts": {
      "task_0": "plain:客户提供的信息不足，我无法在不编造事实的情况下建立客户档案。",
      "task_1": "req", "task_2": "report"}},
  "expected": {"terminal_status": "needs_review",
    "forbidden_artifacts": ["client-profile", "requirement-analysis", "insurance-report"],
    "required_events": ["agent_failed"],
    "forbidden_events": ["task_completed"], "max_repairs": 0}},

 {"case_id": "B003", "name": "knowledge_failure", "category": "knowledge_failure",
  "description": "knowledge_search returns no usable evidence: NO knowledge-evidence artifact is produced (fail closed) and the dependent report path blocks instead of consuming fabricated knowledge.",
  "input": {"graph": chain(with_product=False)[:-1] + [
      {"task_id": "task_5", "task_type": "knowledge_search",
       "dependencies": ["task_4"]},
      {"task_id": "task_6", "task_type": "report_generation",
       "dependencies": ["task_0", "task_1", "task_2", "task_5"]}],
    "scripts": dict(FULL_SCRIPTS, task_5="know:fail", task_6="report")},
  "expected": {"terminal_status": "needs_review",
    "forbidden_artifacts": ["knowledge-evidence", "insurance-report"],
    "required_events": ["agent_failed"],
    "forbidden_events": ["task_completed"], "max_repairs": 0}},

 {"case_id": "B004", "name": "product_failure_degrades_via_replan",
  "category": "product_failure",
  "description": "product_candidates fails (no valid candidates); a replan drops the product task and reroutes the report — honest degradation to COMPLETED without fabricating products.",
  "input": {"graph": chain(),
    "planner_graphs": [v2_drop("task_5")],
    "scripts": dict(FULL_SCRIPTS,
                    task_5="plain:目录中没有任何满足条件的候选产品，我不会编造产品。")},
  "expected": {"terminal_status": "completed",
    "required_artifacts": ["client-profile", "requirement-analysis", "risk-assessment",
                           "coverage-gap-analysis", "solution-plan", "insurance-report"],
    "forbidden_artifacts": ["product-candidates", "product-recommendation"],
    "required_events": ["replan_triggered", "replan_completed"],
    "graph_revision": 2, "previous_revision_immutable": True}},

 {"case_id": "B005", "name": "repair_exhaustion", "category": "repair_exhaustion",
  "description": "A persistently failing eval (invalid product_id) exhausts the bounded repair budget: exactly 2 repairs then NEEDS_REVIEW — no infinite loop, no fabricated PASS.",
  "input": {"executor": "script_agent",
    "graph": [T0,
      {"task_id": "task_5", "task_type": "product_candidates",
       "dependencies": ["task_0"]}],
    "artifact_scripts": {"product_candidates": ["bad_product"] * 5}},
  "expected": {"terminal_status": "needs_review",
    "required_events": ["task_failed"],
    "forbidden_events": ["replan_triggered"],
    "exact_failed_evals": 3, "max_repairs": 2}},

 {"case_id": "B006", "name": "dynamic_replanning", "category": "replanning",
  "description": "Blocked path triggers a controlled replan: v1->v2 accepted, diff recorded, terminal-ok work preserved, failed task removed without faking success.",
  "input": {"graph": chain(),
    "planner_graphs": [v2_drop("task_4")],
    "scripts": dict(FULL_SCRIPTS,
                    task_4="plain:保障缺口分析所需的输入不完整，无法产出方案。")},
  "expected": {"terminal_status": "completed",
    "required_events": ["replan_triggered", "graph_revision_created"],
    "graph_revision": 2, "previous_revision_immutable": True, "max_replans": 1}},

 {"case_id": "B007", "name": "parallel_equivalence", "category": "parallel",
  "description": "A genuinely parallel DAG (independent branches joining at the report) at max_concurrency=1 vs =2: semantically equivalent outcomes, no duplicate execution in either mode.",
  "input": {"graph": [T0,
      {"task_id": "task_1", "task_type": "requirement_analysis", "dependencies": ["task_0"]},
      {"task_id": "task_2", "task_type": "risk_analysis", "dependencies": ["task_0", "task_1"]},
      {"task_id": "task_3", "task_type": "knowledge_search", "dependencies": ["task_1"]},
      {"task_id": "task_4", "task_type": "coverage_gap", "dependencies": ["task_0", "task_1", "task_2"]},
      {"task_id": "task_5", "task_type": "solution", "dependencies": ["task_1", "task_2", "task_4"]},
      {"task_id": "task_6", "task_type": "product_candidates",
       "dependencies": ["task_5", "task_3"]},
      {"task_id": "task_7", "task_type": "report_generation",
       "dependencies": ["task_0", "task_1", "task_2", "task_6"]}],
    "scripts": {"task_0": "profile", "task_1": "req", "task_2": "risk",
                "task_3": "know", "task_4": "coverage_gap", "task_5": "solution",
                "task_6": "product", "task_7": "report"},
    "max_concurrency": 2},
  "expected": {"terminal_status": "completed",
    "required_artifacts": ["client-profile", "requirement-analysis", "risk-assessment",
                           "knowledge-evidence", "coverage-gap-analysis", "solution-plan",
                           "product-candidates", "insurance-report"],
    "required_events": ["task_scheduled"],
    "forbidden_events": ["replan_triggered"], "graph_revision": 1}},

 {"case_id": "B008", "name": "human_approval", "category": "hitl",
  "description": "High-impact replan pauses in WAITING_HUMAN; a human APPROVES and the Harness resumes to COMPLETED (Phase 9 gateway intact under Phase 10).",
  "input": {"graph": chain(),
    "approval_policy": True,
    "planner_graphs": [v2_drop("task_4")],
    "scripts": dict(FULL_SCRIPTS,
                    task_4="plain:输入不完整，无法产出方案。"),
    "human_steps": [{"action": "approve"}]},
  "expected": {"terminal_status": "completed",
    "required_events": ["approval_requested", "approval_waiting",
                        "approval_approved", "approval_resumed"],
    "graph_revision": 2, "max_replans": 1}},

 {"case_id": "B009", "name": "hotl_notify", "category": "hotl",
  "description": "HOTL-A: a runtime failure raises signals -> NOTIFY; the human is an observer only — the run continues autonomously to a terminal state (never WAITING_HUMAN).",
  "input": {"graph": chain(),
    "planner_graphs": [v2_drop("task_4")],
    "scripts": dict(FULL_SCRIPTS,
                    task_4="plain:输入不完整，无法产出方案。")},
  "expected": {"terminal_status": "completed",
    "required_events": ["monitor_signal_detected", "intervention_notified"],
    "forbidden_events": ["approval_waiting", "runtime_paused"],
    "graph_revision": 2}},

 {"case_id": "B010", "name": "hotl_pause_resume", "category": "hotl",
  "description": "HOTL-B: the intervention policy (high=PAUSE) pauses the runtime at a safe barrier after the replan budget exhausts; a human RESUME continues to a terminal state.",
  "input": {"graph": chain(),
    "max_replans": 1,
    "planner_graphs": ["{invalid json", "{still invalid", "{third invalid"],
    "intervention_policy": {"high": "PAUSE"},
    "scripts": dict(FULL_SCRIPTS,
                    task_4="plain:输入不完整，无法产出方案。"),
    "human_steps": [{"action": "resume"}]},
  "expected": {"terminal_status": "needs_review",
    "required_events": ["runtime_pausing", "runtime_paused",
                        "runtime_resuming", "runtime_resumed"],
    "max_replans": 1}},

 {"case_id": "B011", "name": "four_agent_golden", "category": "golden",
  "description": "Golden four-agent E2E: analyst + knowledge + product + report specialists, parallel branches, artifacts with lineage, evals, checkpoints, monitor observations — COMPLETED.",
  "input": {"max_concurrency": 2,
    "graph": [T0,
      {"task_id": "task_1", "task_type": "requirement_analysis", "dependencies": ["task_0"]},
      {"task_id": "task_2", "task_type": "risk_analysis", "dependencies": ["task_0", "task_1"]},
      {"task_id": "task_3", "task_type": "knowledge_search", "dependencies": ["task_1"]},
      {"task_id": "task_4", "task_type": "coverage_gap", "dependencies": ["task_0", "task_1", "task_2"]},
      {"task_id": "task_5", "task_type": "solution", "dependencies": ["task_1", "task_2", "task_4"]},
      {"task_id": "task_6", "task_type": "product_candidates",
       "dependencies": ["task_5", "task_3"]},
      {"task_id": "task_7", "task_type": "report_generation",
       "dependencies": ["task_0", "task_1", "task_2", "task_6"]}],
    "scripts": {"task_0": "profile", "task_1": "req", "task_2": "risk",
                "task_3": "know", "task_4": "coverage_gap", "task_5": "solution",
                "task_6": "product", "task_7": "report"}},
  "expected": {"terminal_status": "completed",
    "required_agents": ["insurance_analyst", "knowledge_specialist",
                        "product_specialist", "report_specialist"],
    "required_artifacts": ["client-profile", "requirement-analysis", "risk-assessment",
                           "knowledge-evidence", "coverage-gap-analysis", "solution-plan",
                           "product-candidates", "insurance-report"],
    "required_events": ["agent_started", "task_completed", "checkpoint_created",
                        "monitor_started"],
    "forbidden_events": ["replan_triggered", "approval_waiting", "runtime_paused"],
    "graph_revision": 1}},
]

if __name__ == "__main__":
    for case in cases:
        with open(os.path.join(CDIR, "%s_%s.json" % (case["case_id"], case["name"])),
                  "w", encoding="utf-8") as f:
            json.dump(case, f, ensure_ascii=False, indent=2)
    print("wrote", len(cases), "cases")
