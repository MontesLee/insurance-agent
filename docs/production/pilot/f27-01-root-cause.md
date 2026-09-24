# F27-01 Root Cause — business finals settle as run SUCCEEDED

## Observed (runtime evidence)
- C08: result_status WAITING_FOR_USER; task/run SUCCEEDED; 0 gates.
- C11: result_status NEEDS_REVIEW (repair-exhausted); task/run
  SUCCEEDED; 0 gates. Trace: knowledge-evidence eval FAIL ×3
  (EVAL-006/007/008, required_non_empty) → REPAIR_EXHAUSTED at
  product-candidate-provider → no candidates/rec/report produced.

## Source-level trace (code, c7ed9c6)
1. orchestrator.run Step-3 (orchestrator.py ~L596-612): missing/
   conflicting client facts → check_client_information →
   cs.wait_for_user(...) → **returns** _report("WAITING_FOR_USER",
   "client-intake", ...) — a FINAL report (correct content: real
   blocking fields + next_questions; no fabrication).
2. Repair-exhausted finals: _run_stage returns NEEDS_REVIEW and
   orch.run ends with a NEEDS_REVIEW report (also final).
3. make_agent_executor.execute() (agent_runtime.py): the defer
   branch triggers ONLY on rep["status"]=="PAUSED_NEEDS_REVIEW"
   (or a resumed paused stage). WAITING_FOR_USER / final
   NEEDS_REVIEW fall through to the ordinary result return.
4. AgentTaskWorker._execute: any non-defer dict result →
   rc.settle_success(task, result).
5. run_control.settle_success: task CAS SUCCEEDED (execution) +
   run CAS SUCCEEDED — **never inspects result["status"]** (the
   business payload).

## Answers (§11)
Q1 Task final state: settle_success task CAS (execution authority).
Q2 Run final state: settle_success run CAS — inherits execution
   success blindly.
Q3 WAITING_FOR_USER→SUCCEEDED path: orch Step-3 early return →
   executor (no classification) → settle_success.
Q4 NEEDS_REVIEW→SUCCEEDED path: repair-exhausted final report →
   same two hops.
Q5 Classification: **agent result classification bug combined with
   a settle semantics gap** — NOT a task-state-machine, approval-
   gate, or state-CAS bug.

## Design semantic gap (§12)
26C-2 documents Run = BUSINESS lifecycle authority, but run.
SUCCEEDED is set purely on EXECUTION success. Today run.SUCCEEDED
means "execution completed", not "business outcome completed" —
the code contradicts the documented authority split.

## Classification (§13)
**A. P1 — Engineering Fix Required** (evidence above). No
fabrication occurred anywhere (C08/C11 delivered nothing), so this
is state-semantics, not content safety — but it misleads every
run-state consumer and leaves the "final output requires human
review" invariant uncovered at WAITING_FOR_USER / repair-exhausted
finals.

## Proposed fix direction (NOT implemented in this gate)
Classify final business statuses in the executor (WAITING_FOR_USER
→ defer-like parking; final NEEDS_REVIEW → WAITING_HUMAN park or
run FAILED-with-reason), and make settle_success consult
result["status"] for the run transition. Engineering phase item.
