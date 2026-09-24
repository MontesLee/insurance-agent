"""Stage REAL waiting approvals for the 27.7.5 validation pilot.

Creates PENDING approval records through the runtime's OWN
creation path (runtime.approval.create_request → ApprovalStore)
in the harness project dirs the server reads — no fabricated
DECISIONS (records stay PENDING/WAITING_HUMAN for the real
reviewer), no backend/runtime code changes.

Cases map to Phase 27 evidence (R1-R6 of the validation plan):
each approval reason names the underlying pilot case and what to
look at; context carries the case_id so reviewers can find the
artifacts (tmp/pilot27/<case>/...).
"""
from __future__ import annotations

import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                    "..", "..", "..", ".."))
sys.path.insert(0, REPO)

HARNESS_ROOT = os.environ.get(
    "INSURANCE_AGENT_HARNESS_ROOT",
    os.path.join(REPO, "tmp", "webui-runs", "harness-projects"))

PILOT_PROJECT = "pilot-2775-feedback-validation"

CASES = [
    ("R1", "C02", "recommendation",
     "single_adult 案例的最终推荐(C001 百万医疗)待审:需求匹配/证据是否充分",
     ["product-recommendation", "knowledge-evidence"]),
    ("R2", "C01", "recommendation",
     "child_protection 案例无 primary(INCOMPLETE_EVIDENCE):证据不足不推荐是否符合业务预期",
     ["product-recommendation", "knowledge-evidence"]),
    ("R3", "C10", "risk",
     "complex_family(3孩+赡养4老人)风险分析:主要风险是否有遗漏",
     ["risk-assessment", "coverage-gap-analysis"]),
    ("R4", "C11", "evidence",
     "knowledge 不可用(空 KB)导致 NEEDS_REVIEW:fail-closed 行为审查",
     ["knowledge-evidence"]),
    ("R5", "C08", "information",
     "信息不全(收入/预算/已有保险 UNKNOWN)返回 WAITING_FOR_USER:处理方式审查",
     ["client-profile"]),
    ("R6", "C12", "boundary",
     "空需求集跑完全链产出报告:边界行为审查(F27-03 场景)",
     ["requirement-analysis", "insurance-report"]),
]


def main() -> int:
    from runtime.approval import create_request
    from runtime.approval.store import ApprovalStore

    pdir = os.path.join(HARNESS_ROOT, PILOT_PROJECT)
    os.makedirs(pdir, exist_ok=True)
    # minimal project marker so the approvals endpoint sees the project
    pmeta = os.path.join(pdir, "project.json")
    if not os.path.exists(pmeta):
        with open(pmeta, "w", encoding="utf-8") as f:
            json.dump({
                "project_id": PILOT_PROJECT,
                "name": "27.7.5 Feedback Validation Pilot",
                "case_id": "phase27-synthetic",
                "status": "waiting_review",
                "state_version": 1,
                "created_at": "2026-09-24T00:00:00Z",
                "updated_at": "2026-09-24T00:00:00Z",
                "tasks": {},
                "current_graph_revision": 1,
                "graph_revisions": [],
                "replans": [],
                "source_request": "phase 27.7.5 validation pilot staging",
            }, f, ensure_ascii=False, indent=1)

    store = ApprovalStore(pdir)
    existing = {a.get("context", {}).get("slot") for a in store.all()}
    created = []
    for slot, case_id, kind, reason, task_types in CASES:
        if slot in existing:
            continue  # idempotent restaging
        rec = create_request(
            project_id=PILOT_PROJECT,
            request_type="APPROVAL_FINAL_REVIEW",
            reason=reason,
            context={
                "slot": slot,
                "pilot_case": case_id,
                "kind": kind,
                "task_types": sorted(task_types),
                "artifacts_hint":
                    f"tmp/pilot27/{case_id}/ (Phase 27 round-1 evidence)",
            },
        )
        store.append(rec)
        created.append((slot, rec["approval_id"], rec["status"]))
    print(json.dumps({
        "project": PILOT_PROJECT,
        "harness_root": HARNESS_ROOT,
        "created": created,
        "total_waiting": len(store.all()),
    }, ensure_ascii=False, indent=1))
    print("STAGED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
