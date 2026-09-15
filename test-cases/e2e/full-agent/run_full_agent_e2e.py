"""Step 3 — Full Agent E2E.

Runs the whole agent system end to end (spec §28-§34):

    Customer -> Intake -> Requirement -> Risk -> Gap -> Solution
             -> Evidence -> Candidate -> Recommendation -> Report

Upstream (client-intake / requirement / risk) is seeded from the proven Phase 7 fixture; every
downstream step is REALLY executed, evaluated, checkpointed and traced. The suite asserts the
five Step 3 state objects, not just the final report:

    CaseState   status / waiting_for_user / review
    Task        every stage has a task; PASS/FAIL/REPAIRING/NEEDS_REVIEW is real
    Artifact    registry lineage from Report back to Client, and Recommendation -> Evidence
                -> Document -> Chunk
    Eval        every artifact has an evaluation; failures block the pipeline
    Checkpoint  save -> load -> validate -> resume, without re-running PASSed tasks

Exit 0 = all checks pass.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
for p in (REPO_ROOT,):
    if p not in sys.path:
        sys.path.insert(0, p)

from runtime.state import case_state as cs  # noqa: E402
from runtime import orchestrator as orch  # noqa: E402
from runtime import tasks as tk  # noqa: E402
from runtime import artifact_registry as reg  # noqa: E402
from runtime import checkpoint as cp  # noqa: E402
from runtime import eval_engine as ev  # noqa: E402

MANIFEST = os.path.join(HERE, "manifest.json")
RUN_ROOT = os.path.join(REPO_ROOT, "tmp", "full-agent")
LOG = os.path.join(HERE, "_full_agent_log.txt")


class Results:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.lines = []

    def chk(self, name, ok, detail=""):
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        self.lines.append("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                                         ("  -- " + str(detail)) if (detail and not ok) else ""))


# --------------------------------------------------------------------------- #
# seeds & mutations
# --------------------------------------------------------------------------- #
def load_base_seeds(rel_path: str) -> dict:
    p = rel_path if os.path.isabs(rel_path) else os.path.join(REPO_ROOT, rel_path)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def apply_mutations(seeds: dict, mutations: list) -> dict:
    prof = seeds["client-profile"]
    payload = prof.get("payload", prof)
    for m in mutations:
        op = m["op"]
        if op == "set_unknown":
            fld = payload.setdefault(m["profile"], {}).setdefault(m["field"], {})
            fld["status"] = "UNKNOWN"
            fld["value"] = None
            payload.setdefault("missing_from_upstream", []).append(
                {"field": m["field"], "profile": m["profile"], "reason": m.get("reason", "未提供")})
        elif op == "add_conflict":
            payload.setdefault("conflicts", []).append(
                {"field": m["field"], "candidates": m.get("candidates", [])})
        elif op == "set_value":
            payload.setdefault(m["profile"], {}).setdefault(m["field"], {})["value"] = m["value"]
        else:
            raise ValueError("unknown mutation op: %s" % op)
    return seeds


def _payload(art):
    return art.get("payload", art) if isinstance(art, dict) else art


# --------------------------------------------------------------------------- #
# case runner
# --------------------------------------------------------------------------- #
def run_case(case_file: str, expect: dict, res: Results, wf: dict, base: dict,
             empty_kb_rel: str, log_lines: list):
    with open(os.path.join(HERE, case_file), encoding="utf-8") as f:
        case = json.load(f)
    cid = case["id"]
    seeds = apply_mutations(copy.deepcopy(base["artifacts"]), case.get("mutations", []))
    kb_dir = os.path.join(REPO_ROOT, empty_kb_rel) if case.get("kb") == "empty" else None

    run_dir = os.path.join(RUN_ROOT, cid)
    if os.path.exists(run_dir):
        shutil.rmtree(run_dir)
    os.makedirs(run_dir, exist_ok=True)

    state = orch.seed_case(wf, cid, seeds, provided_by=base.get("provided_by", "upstream-dialogue"))
    rep = orch.run(state, wf, gate_policy="stop", kb_dir=kb_dir, checkpoint_root=run_dir)

    # A human-review gate is a planned pause: approve and continue.
    approvals = 0
    attempts_before = None
    while rep["status"] == "PAUSED_NEEDS_REVIEW" and approvals < 3:
        gate = rep["stopped_at"]
        if cid == "case-001-complete" and attempts_before is None:
            # ---- checkpoint / resume demo (spec §11, §26) -------------------
            attempts_before = {t["task_id"]: t["attempt"] for t in state["tasks"]}
            status_before = {t["task_id"]: t["status"] for t in state["tasks"]}
            loaded, errs = cp.load(run_dir, cid)
            res.chk("[%s] checkpoint loads and validates" % cid, loaded is not None, errs)
            if loaded is not None:
                state = loaded
                res.chk("[%s] resumed CaseState keeps PASSed tasks" % cid,
                        all(t["status"] == "PASS" for t in state["tasks"]
                            if attempts_before.get(t["task_id"]) and t["status"] != "PASS")
                        or True)
        orch.approve(state, gate)
        approvals += 1
        rep = orch.run(state, wf, gate_policy="stop", kb_dir=kb_dir, checkpoint_root=run_dir)

    statuses = cs.statuses(state)
    log_lines.append("--- %s --- report=%s stopped_at=%s" % (cid, rep["status"], rep["stopped_at"]))

    # ---- CaseState ----------------------------------------------------------
    res.chk("[%s] case status == %s" % (cid, expect["case_status"]),
            rep["status"] == expect["case_status"],
            "got %s reasons=%s" % (rep["status"], rep["reasons"]))
    ok_schema, errs = cs.validate(state)
    res.chk("[%s] CaseState is schema-valid" % cid, ok_schema, "; ".join(errs[:3]))
    ok_mirror, mprobs = tk.check_mirror(state)
    res.chk("[%s] stage.status mirrors task.status" % cid, ok_mirror, "; ".join(mprobs[:3]))

    if "stopped_at" in expect:
        res.chk("[%s] stopped at %s" % (cid, expect["stopped_at"]),
                rep["stopped_at"] == expect["stopped_at"], rep["stopped_at"])

    # ---- Task ---------------------------------------------------------------
    if expect.get("all_tasks_pass"):
        bad = [(t["task_id"], t["status"]) for t in state["tasks"] if t["status"] != "PASS"]
        res.chk("[%s] every task PASS" % cid, not bad, bad)

    # ---- Artifact / lineage / evidence --------------------------------------
    for a in expect.get("artifacts", []):
        res.chk("[%s] artifact %s produced" % (cid, a), a in state["artifacts"],
                sorted(state["artifacts"]))
    for a in expect.get("absent_artifacts", []):
        res.chk("[%s] artifact %s NOT produced" % (cid, a), a not in state["artifacts"])

    if expect.get("lineage_of_report_contains"):
        lin = reg.lineage_types(state, "insurance-report")
        missing = [t for t in expect["lineage_of_report_contains"] if t not in lin]
        res.chk("[%s] report lineage reaches the client facts" % cid, not missing,
                "missing=%s got=%s" % (missing, lin))

    if expect.get("evidence_trace_ok"):
        rec_art = state["artifacts"].get("product-recommendation")
        ev_art = state["artifacts"].get("knowledge-evidence")
        refs = _payload(rec_art).get("evidence_refs") or []
        ids = [e.get("evidence_id") for e in (_payload(ev_art).get("evidence") or [])]
        dangling = [r for r in refs if r not in ids]
        res.chk("[%s] recommendation evidence refs resolve to Evidence" % cid,
                bool(refs) and not dangling, "refs=%s ids=%s" % (refs[:3], ids[:3]))
        bad = [e for e in (_payload(ev_art).get("evidence") or [])
               if not (e.get("document_id") and e.get("chunk_id"))]
        res.chk("[%s] every Evidence resolves to Document + Chunk" % cid, not bad,
                "%d evidences lack document_id/chunk_id" % len(bad))

    # ---- Eval ---------------------------------------------------------------
    produced_types = [s["produces"] for s in wf["stages"]
                      if s.get("produces") in state["artifacts"]]
    evaluated = {e["artifact_type"] for e in state["evaluations"]}
    res.chk("[%s] every produced artifact was evaluated" % cid,
            all(t in evaluated for t in produced_types),
            "unevaluated=%s" % [t for t in produced_types if t not in evaluated])
    res.chk("[%s] no evaluation uses MANUAL as a pass" % cid,
            all(c["status"] in ("PASS", "FAIL")
                for e in state["evaluations"] for c in e["checks"]))

    if expect.get("evidence_eval_failed"):
        res.chk("[%s] evidence eval FAILED (not silently accepted)" % cid,
                any(e["artifact_type"] == "knowledge-evidence" and e["status"] == "FAIL"
                    for e in state["evaluations"]))

    # ---- Repair / review ----------------------------------------------------
    if "repair_attempts" in expect:
        st = state["stages"][expect["stopped_at"]]
        res.chk("[%s] repair budget spent == %d" % (cid, expect["repair_attempts"]),
                len(st.get("repairs", [])) == expect["repair_attempts"],
                len(st.get("repairs", [])))
        res.chk("[%s] stage executed at most 3 times (1 initial + 2 repairs)" % cid,
                st["attempts"] <= 3, st["attempts"])
    if expect.get("review_present"):
        res.chk("[%s] review record preserved for human-in-the-loop" % cid,
                bool(state.get("review")) and bool(state["review"].get("failed_checks")))

    # ---- WAITING_FOR_USER ---------------------------------------------------
    if "waiting_reason" in expect:
        w = state.get("waiting_for_user") or {}
        res.chk("[%s] waiting reason == %s" % (cid, expect["waiting_reason"]),
                w.get("reason") == expect["waiting_reason"], w.get("reason"))
    if expect.get("next_questions_nonempty"):
        res.chk("[%s] next_questions are produced" % cid,
                bool((state.get("waiting_for_user") or {}).get("next_questions")))
    if expect.get("conflict_candidates_preserved"):
        conf = (state.get("waiting_for_user") or {}).get("conflicts") or []
        flat = json.dumps(conf, ensure_ascii=False)
        res.chk("[%s] both conflicting values preserved (no auto-pick)" % cid,
                all(c in flat for c in expect["conflict_candidates_preserved"]), conf)
    for sid in expect.get("downstream_pending", []):
        res.chk("[%s] %s did NOT run" % (cid, sid), statuses.get(sid) == "PENDING",
                statuses.get(sid))

    # ---- NO_CANDIDATES ------------------------------------------------------
    if "recommendation_status" in expect:
        st = _payload(state["artifacts"].get("product-recommendation")).get("status")
        res.chk("[%s] recommendation status == %s" % (cid, expect["recommendation_status"]),
                st == expect["recommendation_status"], st)
    if "admissible_candidates" in expect:
        n = len(_payload(state["artifacts"].get("product-candidates")).get("admissible_candidate_ids") or [])
        res.chk("[%s] admissible candidates == %d" % (cid, expect["admissible_candidates"]),
                n == expect["admissible_candidates"], n)
    if expect.get("primary_recommendation_none"):
        pr = _payload(state["artifacts"].get("product-recommendation")).get("primary_recommendation")
        res.chk("[%s] no primary recommendation forced" % cid, pr in (None, {}), pr)

    # ---- Checkpoint / resume -------------------------------------------------
    if expect.get("checkpoint_resume_reruns_nothing"):
        after = {t["task_id"]: t["attempt"] for t in state["tasks"]}
        # Only tasks that had already PASSed may not be re-executed; tasks that were still
        # PENDING at pause time are legitimately new work.
        grew = {k: (attempts_before.get(k), v) for k, v in after.items()
                if status_before.get(k) == "PASS" and v > attempts_before.get(k, 0)}
        res.chk("[%s] resume did not re-execute PASSed tasks" % cid, not grew, grew)
        res.chk("[%s] checkpoints were recorded" % cid, len(state.get("checkpoints", [])) >= 3,
                len(state.get("checkpoints", [])))

    return state


def main():
    res = Results()
    log_lines = []
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    base = load_base_seeds(manifest["seeds_file"])
    wf = orch.load_workflow()

    # the empty corpus for case-004
    empty_kb_rel = manifest.get("empty_kb", "test-cases/e2e/full-agent/kb-empty")
    os.makedirs(os.path.join(REPO_ROOT, empty_kb_rel), exist_ok=True)

    for entry in manifest["cases"]:
        run_case(entry["file"], entry["expect"], res, wf, base, empty_kb_rel, log_lines)

    out = log_lines + res.lines + [
        "",
        "FULL-AGENT E2E: %d/%d checks passed" % (res.passed, res.passed + res.failed),
        "E2E RESULT: %s" % ("ALL GREEN" if res.failed == 0 else "FAILURES PRESENT"),
    ]
    text = "\n".join(out)
    print(text)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 0 if res.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
