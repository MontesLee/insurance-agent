# Phase 27.7.5 — Feedback Validation Result (AI-Operator Session)

Status: SESSION EXECUTED 2026-09-24 · Reviewer: **AI-Operator**
(Claude driving the real UI; NOT a human insurance professional)
· MVP @ 55ac759 · Full session through real browser UI on
localhost (bridgic-browser → Chrome → React app → FastAPI).

## Human Reviewer Results (Phase 27.7.6)

**PENDING_HUMAN_PARTICIPANT** —— 无法由 AI 代替。

This phase requires at least one real human reviewer (preferably
a non-developer insurance professional) to complete R1–R6 and
demonstrate whether they will voluntarily produce structured
feedback. Everything is ready:

- **Launcher**: `docs/production/pilot/start-human-session.bat`
  (starts backend + frontend, opens browser with instructions)
- **Staged approvals**: 6 WAITING_HUMAN records already in the
  harness store (project `pilot-2775-feedback-validation`)
- **Export**: after the session, DevTools Console →
  `copy(JSON.parse(localStorage.getItem("webui:feedback:v1")))`
- **Analysis**: fill the table below from the exported records

### Post-session table (to be filled by the analysis reviewer)

| Case | Decision | Feedback? | Category | Score(0-4) | Conversion |
|---|---|---|---|---|---|
| R1 | | | | | |
| R2 | | | | | |
| R3 | | | | | |
| R4 | | | | | |
| R5 | | | | | |
| R6 | | | | | |

### Human Metrics (to be computed)

| Metric | Result |
|-|-|
| A · Completion (APPROVE) | |
| A · Completion (REJECT) | |
| B · Actionable (avg / ≥2 / ≥4) | |
| C · Taxonomy (unclassable count) | |
| D · Conversion (eval/knowledge/product) | |
| E · Latency (avg) | |

### Final Gate (computed from human data)

☐ GO — proceed to Phase 27.8
☐ ITERATE — adjust capture UX, re-pilot
☐ STOP — no learning pipeline

---

> **Honesty disclosure**: this session validates the CAPTURE
> MECHANICS end-to-end (UI → decision → feedback → localStorage →
> export) and demonstrates achievable feedback quality, but it
> CANNOT answer "will a human reviewer voluntarily produce
> structured feedback?" (Metric A's real test). The decision gate
> below is scoped accordingly.

---

## 1. Pilot Summary

| 项 | 值 |
|---|---|
| Cases | 6(R1–R6,staged as real WAITING_HUMAN approvals)|
| Decisions | 6/6 completed(3 APPROVE, 3 REJECT)|
| Feedback records | 6/6 filled(100%)|
| Reviewer | AI-Operator(Claude)|
| 时间范围 | 2026-09-24 05:24–06:25 UTC(单会话)|
| 环境 | real UI(vite 5173 → FastAPI 8000)· real browser|

## 2. Metrics Result

| Metric | Result | Caveat |
|-|-|-|
| A · Completion | APPROVE 3/3=100% · REJECT 3/3=100% | **AI-operator;human willingness UNPROVEN** |
| B · Actionable | 6/6 scored ≥3 · avg 3.7 · ≥4: 4 | Self-scored(见 §4 逐条)|
| C · Taxonomy Fit | unclassable=0 · 4/6 cats used · 无 Other 需求 | 2 cats unused(WRONG_RECOMMENDATION, UX_ISSUE — 本 session 无此类 case)|
| D · Conversion | eval_case=4 · knowledge=1 · product=1 | 6/6 convertible |
| E · Latency | avg 35s/case(26–47s range) | AI speed;human will differ |

## 3. Per-Case Record

| Case | Decision | Category | Score | Conversion | Description (truncated) |
|---|---|---|---|---|---|
| R1/C02 | APPROVE | EVIDENCE_ISSUE | 4 | eval_case | critical_illness 缺知识背书,根因 F27-02… |
| R2/C01 | REJECT | KNOWLEDGE_GAP | 3 | knowledge | 演示目录单域+知识不足 → 无 primary;报告无补救路径… |
| R3/C10 | APPROVE | REASONING | 3 | product | 赡养责任未量化为风险敞口… |
| R4/C11 | REJECT | EVIDENCE_ISSUE | 4 | eval_case | NEEDS_REVIEW 终局被记 SUCCEEDED(F27-01)… |
| R5/C08 | APPROVE | MISSING_INFORMATION | 4 | eval_case | WAITING_FOR_USER 正确但 blocking_fields 未持久化(EH-01)… |
| R6/C12 | REJECT | REASONING | 4 | eval_case | 空需求集被接受跑完全链(F27-03)… |

All records have: category + description + evidence_refs +
expected_behavior + anchor(approval_id#decision)+ status=
captured + provenance=governance-ui.

## 4. Feedback Examples

**High quality(score 4 — R4):**
> Category: EVIDENCE_ISSUE
> "空 KB 时 knowledge-search 的 3 次 EVAL required_non_empty 全
> FAIL → repair_exhausted → 最终 NEEDS_REVIEW,这个链路本身正确;
> 真正的问题是 NEEDS_REVIEW 终局被 settle_success 记为 run/task
> SUCCEEDED(F27-01)且无人工门。期望:业务终局
> WAITING_FOR_USER/NEEDS_REVIEW 应进入 WAITING_HUMAN 或 FAILED,
> 绝不 SUCCEEDED。"
> → 对象+原因+根因代码路径+期望行为+可复现输入 = eval-case ready

**Low end(score 3 — R3):**
> Category: REASONING
> "三代同堂+3孩场景下,赡养4位老人仅作为文本进入
> economic_responsibility,未量化为具体风险敞口(无金额、无期限),
> 风险清单因此低估家庭责任。"
> → 对象+原因+期望清楚,但缺可复现的量化边界 → product-req

## 5. Findings

**Signal(强):**
- FV-S1: ALL 6 feedbacks are actionable(≥3), with structured
  refs to artifacts, findings, and code paths. The capture form
  produces evaluation-ready records when the reviewer knows the
  domain. 4/6 directly convertible to eval cases(F27-01, F27-03
  already have root-cause docs that pair 1:1 with the feedback).
- FV-S2: The taxonomy held: every real issue found a category,
  no "Other" need arose. Two unused categories correspond to
  case types not in this session (wrong recommendation with
  evidence present; UX issue without a business error).

**UX Issue:**
- FV-U1 (P3): Decision must happen before feedback — navigating
  back to queue from workspace goes to DETAIL not QUEUE (one
  extra click). Minor friction.
- FV-U2 (P3): Project-ID manual entry persists correctly but
  first-time discovery requires instruction (known gap).

**Taxonomy Issue:**
- FV-T1 (INFO): MISSING_INFORMATION served dual duty
  (agent-should-ask vs. agent-didn't-persist-the-ask). The
  category worked, but a future sub-tag could separate them.

**Architecture Issue:**
- FV-A1 (P2, real finding): **PENDING → WAITING_HUMAN transition
  gap in the staging→review flow.** Staged approvals created
  directly as PENDING cannot be approved from the UI (409 —
  illegal transition); the reviewer needed an external
  ApprovalManager.wait() call to move them to WAITING_HUMAN.
  In a real harness run this happens automatically, but any
  tooling that stages approvals directly must replicate the
  harness's wait() step. Recorded as staging-tooling gap, not a
  runtime defect.

## 6. Decision Gate

**ITERATE** —— with a precise scope:

**What IS proven by this session:**
- The capture pipeline works end-to-end (real UI → decision →
  structured feedback → localStorage → export → analysis) ✓
- The taxonomy is sufficient for real findings ✓
- Feedback quality CAN reach eval-case-ready(4/6 achieved score
  ≥4 by a domain-aware operator)✓
- The evidence-chain display provides enough context for a
  reviewer to make grounded decisions ✓

**What is NOT proven:**
- **Human willingness(Metric A)**—— an AI operator with deep
  codebase knowledge produced 100% completion; a human insurance
  professional may fill 10% or 80%. This is THE critical unknown
  for Phase 27.8's ROI.

**Recommended next step:**
1. At least ONE human reviewer session(Owner or a trusted
   colleague)using the same R1–R6 → measures real Metric A.
2. If human completion ≥ 30%(REJECT side), proceed to 27.8.
3. If < 30%, iterate on capture UX before any pipeline work.

## Verification

Code changed: NO · Runtime changed: NO · Backend changed: NO ·
Production schema changed: NO(staging used the harness runtime's
own ApprovalStore; the PENDING→WAITING_HUMAN transition gap is a
tooling finding, not a runtime defect)

## Backend truth verification (post-session)

All 6 approvals resolved through the real API(approve/reject
endpoints with REVIEWER role); feedback records in browser
localStorage; zero direct database writes from the UI.
