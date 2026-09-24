# Pilot Case Template

```yaml
pilot_case_id: Cxx
case_type: <child_protection|single_adult|married_no_child|dual_income|
            mortgage_family|existing_insurance|underinsured|
            incomplete_info|evidence_sensitive|complex_family|
            knowledge_unavailable|no_requirements|...>
data_type: SYNTHETIC | DE-IDENTIFIED_REAL     # REAL_CUSTOMER forbidden
created_at: <ISO8601>
runtime_version: phase26c-productionization-v1.0 (c7ed9c6)
knowledge_version: <registry version / fixture-kb id>
llm_provider: N/A-deterministic-path          # queue path = real 0 LLM calls
llm_model: N/A
reviewer: <owner identity — filled at review time>
status: PENDING_HUMAN_REVIEW | APPROVED | REJECTED | NEEDS_CHANGE
seed_mutations: [...]                          # from tools/run_pilot.py
kb: null | empty
```

Machine-side fields (auto-recorded in data/pilot-machine-results.json):
outcomes / final_task_status / final_run_state / terminal_reason /
attempt / result_status / budget{task_attempts_used,
repair_attempts_used, llm_calls_used} / mechanical_approvals /
elapsed_s / artifacts directory (tmp/pilot27/<id>).
