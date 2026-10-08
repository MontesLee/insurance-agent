# Phase 27.7.8 — AI Review Architecture Audit & Review Lifecycle Design

Date: 2026-09-24 · Method: READ-ONLY audit (no code/UI/schema/runtime
changes). Evidence: two full code sweeps (`evaluation/`, `evals/`,
`runtime/`), governance docs (ADR-004/017/018, human-feedback-loop-v0.1,
human-on-the-loop), Phase 16 quality report, pilot taxonomy F01–F18, and
LIVE API pulls of the 6 staged HR runs (incl. two repair runs).

> **STATUS: analysis only — STOP after this report.** Deliverables:
> capability map, reusability analysis, gaps, architecture options,
> recommended lifecycle, contract proposal, workspace IA, roadmap.
> Nothing implemented; no Reviewer Agent created; no schema changed.

---

## 1. Q1 — Does review capability already exist?

**Yes — but it is distributed across three layers, and every existing
layer is deterministic. There is no semantic review anywhere.**

| Layer | Location | Role | Runs when | Output | Runtime effect | Reusable? |
|---|---|---|---|---|---|---|
| Runtime Eval Engine | `runtime/eval_engine.py` + `runtime/resources/config/eval.rules.json` | Per-artifact VALIDATION (structure/existence/consistency/provenance/catalog) | Inside every run, blocking (orchestrator.py:475 main gate; :231 evidence service; :287 seeding; harness.py:2522 agent-mode sole owner) | EVAL-NNN record {status, checks[], repairable} + EVAL_PASS/FAIL event | PASS required to store artifact & advance; FAIL enters repair | High — pure, config-driven, no LLM; honesty rule "unevaluable ⇒ FAIL" |
| Repair Controller | `runtime/repair.py` + `repair.rules.json` | Issue→action mapping + input patching | After eval FAIL / execution error (orchestrator.py:509-557; harness.py:2490-2585) | RERUN_FROM_UPSTREAM / DROP_INVALID_PRODUCTS; ≤2 repairs, 3 attempts | Re-runs SAME skill with patched input; exhaustion ⇒ NEEDS_REVIEW | High — bounded, audited, never edits produced artifacts |
| Review Card generator | `evaluation/human-review/review_card_generator.py` (+ schema, risk-rules.yaml) | Post-run deterministic REVIEWER-CLASSIFIER: aggregates evals + state + trace into 4 check dimensions, 9 risk-flag types, review level | On demand, offline: CLI or `GET /api/runs/{id}/review-card` (server.py:933, disk-keyed, survives restarts) | `human_review_card.json` (schema-validated v1.0): AUTO_PASS / SUMMARY_REVIEW / DEEP_REVIEW + reasons + sampling(10%, seeded) | None by itself — feeds governance UI + human routing | **Highest** — this IS a reviewer; the missing layer is what it aggregates |
| Offline eval suites | `evals/` (agent-benchmark, agent_quality, benchmark, business, knowledge, security, observability) | Regression referee + adversarial/mutation teeth | pytest / CLI only ("production never imports evals/", test-enforced) | Hard gates (e.g. `product_hallucination_zero`), 30×7 decision matrix, 18 injection cases, mutation 8/8 | None (gate for CHANGE, not for runs) | Medium — datasets double as AI-review calibration material |
| HITL Approval Gateway | `runtime/approval/` + harness gates | Human decision boundary | REPLAN approval (policy.py:37-61), FINAL_REVIEW gate (harness.py:2230-2275, mode-gated) | PENDING→WAITING_HUMAN→APPROVED/REJECTED/EXPIRED | Blocks delivery; approve⇒ready_for_delivery | High — escalation endpoint already exists |
| HOTL Supervisor | `runtime/control/` (monitor/policy/manager) | Deterministic runtime-health watcher | Continuous (observe over events) | Signals→risk LOW..CRITICAL→NONE/NOTIFY/PAUSE/WAIT_APPROVAL | Pause at safe barriers; audited commands | High — escalation plumbing exists |

The `evaluation` package therefore already **performs reviewer duty**
(triage + evidence packaging) even though its name says "evaluation".
What it cannot do: judge whether the analysis is *reasonable* — the
card's own design admits this: its two LOW flags (`style_issue`,
`formatting_issue`) are `emit: human_only` (risk-rules.yaml:84-90) —
judgment categories no detector may produce.

## 2. Q2 — Is Human Reviewer Validation still necessary?

Split by what each tier can own in THIS insurance agent (grounded in
the pilot taxonomy F01–F18 and the 12-case owner review):

### Tier 1 — Automatically judgable (deterministic; already implemented)
schema conformance · required fields · evidence existence
(`required_non_empty` — empty KB hit FAILs) · provenance integrity
(every evidence_id/document_id/chunk_id present; every recommendation
evidence_ref resolves — dangling ⇒ FAIL) · cross-artifact reference
consistency (gap→risk, solution→gap, orphan refs) · catalog existence
(`catalog_exists`, `candidate_known`, `catalog_has_primary_product`) ·
contamination/anti-hallucination (no catalog leakage into analysis
layers) · catalog governance (expiry/demo/missing-evidence fail-closed)
· trace/task integrity (all tasks PASS; no unfinalized case) · repair
history surfacing (`repair_used` flag). These are **proven live** —
run_84f63c7c's card FAILed evidence_check with 3 failed evals and
flagged `repair_used` with `evidence_ref: task:TASK-006:attempt=3`.

### Tier 2 — Fits LLM Review (semantic; NO layer exists today)
- Is the risk analysis *reasonable* for this family structure (not
  just schema-valid)? (F04 observed no failures, but 12 cases ≠ proof)
- Do needs ↔ gaps ↔ solutions ↔ recommendation actually match in
  meaning, not just by id-trace? (offline agent_quality does the
  id-projection deterministically; the semantic residue is unmeasured)
- Is the recommendation reason *valid* — e.g. is "no primary" the
  right call, or a rule artifact? (exactly F27-02: 10/10 candidates
  rejected by evidence rules — a human had to discover this)
- Hidden assumptions (income stability, health status guessed from
  absence) · report faithfulness to the analysis (RPT-Q covers
  id-subset offline; tone/framing drift is semantic) · missed obvious
  risks (e.g. sole breadwinner with mortgage but no income-protection
  analysis).

### Tier 3 — Must stay Human (escalation; cannot be automated on data the system holds)
- **客户事实确认** — health disclosure (健康告知), existing policies,
  income/budget truth: the agent holds client-*claimed* data; legal
  suitability requires the client's own confirmation. Ties directly to
  the 27.7.7 `DATA GAP: 健康告知/条款类确认项`.
- **客户偏好与预算确认** — premium vs declared budget tolerance is a
  preference, not a fact (recommendation exceeding budget = escalate).
- **条款边界确认** — clause interpretation against a specific contract
  wording; knowledge base may be stale (F07/knowledge governance
  exists, but "is this clause current" is a governance/human call).
- **高风险业务决策** — high exposure (CRITICAL risk / unprotected ≥¥1M),
  contradiction in client facts (conflicts[]), delivering "no
  recommendation" to a customer with a critical gap (business
  consequence: customer walks away unprotected — F27-02's real cost).
- **Accountability** — anything that results in advice delivered to a
  customer. The final-review gate exists precisely for this.

Conclusion: **Human Reviewer Validation should not remain the DEFAULT
path for every run — it should become the ESCALATION path.** Humans
currently spend attention on Tier-1-recoverable and Tier-2-judgeable
content because no Tier-2 layer exists. The 27.7.7 workspace already
cut the reading cost; the remaining cost is judgment volume.

## 3. The real quality chain (Runtime loop ≠ Offline evaluation)

```
                        RUNTIME QUALITY LOOP (per run, blocking)
Customer input (case / chat)
  ↓
client-intake ── gate: human_review (WAITING_FOR_USER on UNKNOWN; never guesses)
  ↓
requirement-analysis → risk-analysis → coverage-gap-analysis
  ↓                     [each stage:]
solution                skill executes (python engine, tuple3 honest-fail)
  ↓                       ↓
product-candidate-… ──→ contract jsonschema validation ──FAIL→ CONTRACT_VIOLATION
  ↓                       ↓ PASS
product-recommendation ← deterministic EVAL ENGINE (12 check families)
  ↓                       ↓ FAIL ──→ REPAIR plan (≤2) → input patch →
report-generation         RERUN same skill → RE-EVAL ──exhausted→ NEEDS_REVIEW
  ↓                       ↓                                    ↓
  ↓                     PASS: artifact frozen (sha256)          ↓ dynamic replan
  ↓                                                           (Phase 8, only after
  ↓                                                            repair exhaustion,
  ↓                                                            budget ≤2)
  ↓                                                            ↓ high-impact diff
  ↓                                                            ↓ APPROVAL_REPLAN (P9)
  ↓                                                           ↓
  └────────────→ FINAL_REVIEW gate: APPROVAL_FINAL_REVIEW ──→ WAITING_HUMAN
                        (mode-gated; approve ⇒ ready_for_delivery)
Throughout: HOTL monitor → signals → NONE/NOTIFY/PAUSE/WAIT_APPROVAL (P10)
            RunBudget co-enforces attempts/repairs/replans; late/over-budget
            successes rejected (26C); recovery reconciles WAITING_FOR_APPROVAL

                        POST-RUN (on demand, evaluation domain)
run dir (case_state.json + trace.jsonl)
  ↓
Review Card generator ──→ AUTO_PASS / SUMMARY_REVIEW / DEEP_REVIEW + flags
  ↓
Governance UI (27.7.7 human-readable workspace) ──→ human decision (approve/reject)
                                                        + feedback (ADR-018: evidence)

                        OFFLINE EVALUATION (gate for CHANGE, never for runs)
pytest battery (599) · benchmark B001-B011 + 18 failure-injection F01-F18
agent-benchmark 33 cases (hard gates: hallucination 0, provenance 0, …)
agent_quality 30 cases × 7 dims (mutation detection 8/8) · golden G-001..009
knowledge/business/security/observability suites
```

Key discipline the options must respect: the runtime loop is
**deterministic-first** (ADR-004: "the inspected party grades its own
paper — not credible"; no LLM judgment, no MANUAL status in the eval
engine), and the governance layer is **read-mostly, no control
coupling** (ADR-017), and human feedback is **evidence, never a control
signal** (ADR-018).

## 4. §五 Capability table (keyword sweep result)

| Capability | Exists? | Location | Runtime/Offline | Current function |
|---|---|---|---|---|
| schema validation | ✅ | orchestrator.validate_artifact :134-143; eval `schema` check; contracts/*.schema.json | Runtime (blocking) | Contract conformance before eval |
| required-fields/existence | ✅ | eval_engine `required_fields`/`required_non_empty` :146-172 | Runtime | Empty evidence/artifacts FAIL |
| provenance check | ✅ | eval_engine :198-235; knowledge governance registry (service.py:380) | Runtime | Dangling evidence refs FAIL; KB hits re-verified against registry |
| hallucination check | ✅ (structural) | `contamination` + catalog invariants + catalog_governance; offline hard gate `product_hallucination_zero` | Runtime + Offline | No fabricated products/leakage; not semantic truthfulness |
| semantic evaluation | ❌ (deterministic projections only) | evals/agent_quality (id-trace, paraphrase signatures) | Offline | Change gate; nothing at runtime; no LLM judge anywhere |
| LLM review | ❌ | — | — | Does not exist (by design so far) |
| repair | ✅ | runtime/repair.py; orchestrator :509-557; harness :2490-2585 | Runtime | Input-patch rerun, ≤2 repairs, never edits artifacts |
| rerun / retry | ✅ | RERUN_FROM_UPSTREAM/RERUN_STAGE; queue requeue (run_control.py:395-490); human RETRY_TASK | Runtime | Bounded reruns, budget-gated |
| replan | ✅ | harness :1465-1770 (Phase 8) | Runtime | Only after repair exhaustion; id-merge preserves PASS |
| gate (quality gates) | ✅ | eval.rules.json check registry; offline hard-gate sets | Runtime + Offline | Closed vocabulary, config-driven |
| validation (state/trace) | ✅ | trace_check in card; checkpoint.validate; transitions guards | Runtime + Post-run | Execution integrity |
| verify (mutation testing) | ✅ | tests/workflow/test_step3_mutation.py; M01-M08; M-AUTH/M-OBS | Offline | Proves detectors have teeth (8/8) |
| safety | ✅ | fail-closed everywhere (unevaluable⇒FAIL; WAITING_FOR_USER never guesses; budget UNKNOWN sentinel) | Runtime | Never silent-pass |
| review (post-run) | ✅ deterministic | evaluation/human-review card | Post-run, on demand | Triage AUTO_PASS/SUMMARY/DEEP + flags + 10% sampling |
| approval (human) | ✅ | runtime/approval + harness gates; UI endpoints | Runtime boundary | REPLAN + FINAL_REVIEW; state machine frozen (ADR-017) |
| supervisor | ✅ | runtime/control (Phase 10) | Runtime-adjacent | Deterministic health signals → intervention policy |
| feedback | ✅ (capture) | web feedback panel → localStorage (GAP-27.7-01 no backend) | Governance | Evidence for offline curation (ADR-018) |
| review result contract | ◐ | review-card.schema.json v1.0 | Post-run | Deterministic dimension only; no semantic issues/confidence |
| benchmark/golden | ✅ | evals/agent-benchmark (33+9 cases), evals/benchmark (11+18) | Offline | Regression baseline + adversarial |
| confidence | ❌ | — | — | coverage_assessment.confidence exists in risk artifacts only |

## 5. §六 Repair-loop evolution analysis

Target: `Agent → Validation → Review → Issue Detection → Repair →
Rerun → Review Again → PASS`.

**Already supported (with code):**
- Agent→Validation→Issue Detection: eval FAIL carries check_id +
  repairable flag (eval_engine.py:358-372).
- Issue→Repair→Rerun: `repair.plan()` maps check_id→action
  (cross_artifact_orphan_refs→RERUN_FROM_UPSTREAM,
  catalog_exists→DROP_INVALID_PRODUCTS; repair.py:36-43), orchestrator
  re-runs the same skill on patched input (:448, :555).
- Re-validation: every repair re-enters the SAME eval gate
  (orchestrator :472-481; harness :2490-2585 "repair-reevaluates",
  test_enforced in test_eval_boundary.py).
- Bounded exhaustion: ≤2 repairs / 3 attempts → REPAIR_EXHAUSTED →
  NEEDS_REVIEW (repair.rules.json; orchestrator :517-526).
- **Live evidence**: run_84f63c7c & run_381c2836 contain the complete
  chain — stage_failed(EVAL-007) → repair_started(RERUN_FROM_UPSTREAM)
  → repair_completed(changed=True) → 2nd failure → repair_exhausted
  (budget=exhausted) → card DEEP_REVIEW + `repair_used` flag.

**Missing:**
1. A **Review** stage between Validation and Issue Detection that can
   detect SEMANTIC issues (the loop today only closes over structural
   failures). No component produces semantic issues; no schema for them.
2. **Semantic issue→repair mapping**: repair.rules.json's repairable
   map covers 2 structural families; semantic issues (e.g. "report
   overstates coverage") have no action, and ESCALATE is terminal for
   schema/contamination/provenance.
3. **Review Again**: no re-review after repair (would require the
   reviewer to be re-invoked inside the loop).
4. **Determinism strategy**: replay/checkpoint determinism is a core
   contract; an in-loop LLM reviewer breaks byte-replay unless its I/O
   is frozen as artifacts. Not designed yet.
5. ADR-004 explicitly rejects LLM judgment in the eval engine — an
   in-run LLM gate needs a new ADR, not a loophole.

**Minimal completion path (not implemented):** keep the deterministic
loop untouched; add the semantic review as a POST-run pass first
(§7 Option B). In-run semantic gates (true Option C) require: semantic
issue schema + repair mapping extension + frozen-transcript replay
strategy + RunBudget `llm_calls` integration + ADR-004 amendment.

## 6. §七 Three options (applicability, no ranking)

### Option A — Agent → Human Review → Final  *(≈ today, mode-gated)*
- **Strengths**: maximal accountability; zero new components; matches
  the regulatory instinct for advice delivery; the 27.7.7 workspace
  already made it usable.
- **Weaknesses**: human attention is the scarcest resource and is spent
  on Tier-1/Tier-2 content a machine could own (every run becomes
  WAITING_HUMAN regardless of card level); semantic quality is sampled
  only when a human happens to notice (F27-02 was found by owner
  review, not by any gate); does not scale past pilot volume.
- **Fits**: pilot scale; high-consequence cases; while no trustworthy
  LLM provider policy exists (current state — F13: LLM provider never
  exercised; R-05 history).

### Option B — Agent → LLM Review → Human Review if needed → Final
- **Reuse**: Review Card (input + companion verdict), workspace bundle
  loader (all 9 artifacts + events already assembled), card endpoint
  pattern (disk-keyed, in-memory, schema-validated), feedback taxonomy
  categories, HOTL alert routing, existing approval endpoints.
- **New**: an AI-review generator in the evaluation domain (sibling of
  card generator) + ai-review-result schema + a deterministic combiner
  (`decide_v2(card, ai_result)`) + a live LLM provider policy
  (prerequisite; currently absent) + calibration dataset (bootstrap
  from the 12 pilot cases + human-review session results).
- **Risks**: reviewer non-determinism (mitigate: schema-validated
  output, recorded transcripts, temperature policy); reviewer failure
  must fail-closed to human (never to PASS); reviewer must be a
  different context than the producer (ADR-004 spirit); cost/latency
  per run; over-triggering escalation just moves the bottleneck.
- **Fits**: current version — post-run only, no runtime change, no
  replay impact, ADR-017/018 intact.

### Option C — full in-run loop (Deterministic → LLM Review → Repair → Rerun → LLM Review → Human Escalation)
- **Coverage by existing code**: the deterministic segment is ~complete
  (validation→issue→repair→rerun→re-validate→exhaustion→escalation);
  budget plumbing exists (RunBudget has llm_calls/repair_attempts);
  replan/approval/supervisor escalation exist.
- **Gaps**: everything LLM (issues 0%), semantic repair mapping,
  in-run determinism/replay strategy, re-review loop, latency budget,
  ADR-004 amendment; re-opens the frozen 26C/27 runtime baseline.
- **Fits**: later, after B proves the reviewer's precision on real
  runs, and only for bounded high-value stages (report-generation,
  product-recommendation) rather than the whole DAG.

## 7. §八 Recommended target architecture (for THIS version)

```
Current Agent (unchanged runtime pipeline)
        ↓ finished run dir (case_state.json + trace.jsonl + artifacts)
QUALITY LAYER (existing, deterministic, verbatim)
        eval engine results · Review Card v1.0 (4 dimensions, flags, level)
        ↓
REVIEW LAYER (NEW — evaluation domain, post-run)
        AI Review: semantic checks over the 9 artifacts + card
        → ai-review-result (schema-validated; issues w/ severity,
          category, evidence_refs, repairable, confidence)
        fail-closed: reviewer unavailable/error ⇒ NEEDS_HUMAN_ESCALATION
        ↓
DECISION LAYER (deterministic code, NOT an LLM)
        decide_v2(card, ai_result, config) →
          AUTO_PASS        (card PASS ∧ ai PASS ∧ sampling not hit)
          NEEDS_INFO       (missing client facts → existing WAITING_FOR_USER /
                            PROVIDE_INFORMATION mechanisms)
          SUGGEST_RERUN    (repairable issue → existing RETRY_TASK/REPLAN
                            via control plane, human-approved)
          HUMAN_ESCALATION (summary | deep)
        Rule: AI may only ESCALATE, never de-escalate; only a human
        decision may lower a level (recorded as Decision+Feedback).
        ↓
OUTPUT: governance workspace (AI Review section + escalation panel)
        → human approve/reject + feedback (ADR-018: evidence)
```

Why this fits now: **Quality Layer** stays exactly the trusted
deterministic core (ADR-004 untouched). **Review Layer** lives beside
the card generator — evaluation domain, read-only, no runtime import,
no replay impact (ADR-017 untouched). **Decision Layer** is code, so
accountability and auditability remain deterministic; the LLM only
*raises* issues with evidence, it never flips a verdict. Option C's
in-run loop is deliberately NOT recommended for this version (§6).

## 8. §九 Human Review redefined as Human Escalation

Default flow becomes: AI Review → Risk Classification → route.

- **HIGH — Human Escalation (deep)**: any card HIGH flag
  (missing_evidence, false_product_information, unresolved_task_failure,
  case_not_finalized) · health/eligibility unknowns affecting
  underwriting (健康告知 tier-3) · contradiction in client facts
  (conflicts[]) · high exposure (CRITICAL risk or unprotected ≥¥1M) ·
  recommendation premium exceeding declared budget (适当性) ·
  no-primary for a customer with a CRITICAL gap · AI issue severity
  HIGH · validation FAIL of any dimension · sampling hit.
- **MEDIUM — request info / (human-approved) rerun**: card MEDIUM flags
  (insufficient_customer_context, repair_used, no_primary without
  critical gap) · uncertainties / eligibility UNKNOWN · AI issue
  severity MEDIUM (reasoning gap, report faithfulness drift) ·
  information_gaps. Resolution uses EXISTING mechanisms:
  PROVIDE_INFORMATION, RETRY_TASK, REPLAN — the human stays the actor.
- **LOW — auto-pass with audit trail**: card PASS ∧ ai PASS ∧ no
  sampling hit; LOW/style notes (human_only categories) remain
  attachable by reviewers post-hoc.

Note what this does NOT change: delivery of advice still passes the
mode-gated FINAL_REVIEW approval for CONTROLLED_PILOT/PRODUCTION —
escalation levels route review *burden*, and the final gate stays.

## 9. §十 Review Result Contract proposal

**Reuse first**: review-card.schema.json v1.0 already carries
severity-bearing flags with evidence_refs, a review_action with
levels+reasons, sampling, and eval_summary — the deterministic half of
the contract is DONE and must stay verbatim (UI renders it verbatim
today). The feedback taxonomy (A Agent Reasoning / B Missing Info /
C Wrong Recommendation / D Evidence / E Knowledge / F Other) already
gives issue categories. What's genuinely missing: semantic issues,
confidence, reviewer identity, and an explicit card↔AI relationship.

**Minimal NEW schema — `ai-review-result.schema.json` v0.1**
(evaluation domain, sibling of the card; additive; nothing removed):

| Field | Exists today? | Why needed |
|---|---|---|
| `schema_version`, `review_id`, `case_id`, `run_id`, `generated_at` | pattern exists (card) | identity/auditability |
| `reviewer {model, version, prompt_version}` | ❌ new | reproducibility; skills already carry version conventions |
| `input_refs {card_id, artifact_ids[], trace_path}` | ◐ (card has `source`) | what the reviewer read — evidence-before-judgment |
| `status: PASS \| NEEDS_INFO \| NEEDS_HUMAN_ESCALATION` | ◐ (card has validation_status + level) | routing vocabulary; **no NEEDS_REPAIR at v0.1** — post-run review doesn't repair; rerun goes through the control plane |
| `issues[] {severity(HIGH/MEDIUM/LOW), category(A–F), description, evidence_refs[], repairable, confidence∈[0,1]\|null}` | ◐ severity/evidence_refs from card; category from taxonomy; **confidence ❌ new (nullable — never fake)** | the semantic payload; repairable feeds SUGGEST_RERUN routing only |
| `checked_aspects[]` | ❌ new | what was reviewed (vs. silently skipped) — honesty |
| `card_agreement: AGREE \| DISAGREE {reasons[]}` | ❌ new | audit the auditor vs the deterministic layer |

Combiner contract: `decide_v2` is a pure function, config-driven
(risk-rules-style YAML), covered by the same closed-vocabulary and
fail-closed rules as the card. AI can only escalate.

## 10. §十一 Review Workspace next-version IA (design only)

Keep the 27.7.7 nine-section IA; insert after "Human Review" and
before the Decision panel:

1. **AI Review 区** — verdict line (✓ 客户信息一致 / ✓ 风险分析有依据 /
   ✓ 推荐匹配需求 / ✓ 报告忠实于分析), then 发现 (issues: severity,
   category label, description verbatim, evidence_refs resolved via the
   existing inline-evidence mechanism, confidence rendered only when
   non-null), then reviewer id (model@prompt_version) + checked_aspects
   + card_agreement. Reviewer unavailable → “AI 审核：暂不可用（已按
   需人工审核处理）” — fail-closed, never silent.
2. **Human Escalation 区** — for escalated runs: 原因 (verbatim from
   decide_v2 reasons / flags / HIGH issues) + 建议动作 mapped ONLY to
   existing mechanisms (联系客户补充信息 / 人工重跑该阶段 / 人工复审)
   — no new control surface (ADR-017).
3. **Technical Details (collapsed, unchanged)** — trace, run,
   artifacts, schema, raw payloads, full Review Card, plus raw
   ai-review-result JSON + copy button (audit parity with artifacts).

## 11. §十二 Real-data validation (live API, 2026-09-24)

| Run | Class | Data available for AI Review? | Verdict |
|---|---|---|---|
| run_9de5882e | complete, restored | 9 artifacts w/ natural-language reasons, 9/9 evals PASS, card AUTO_PASS, full events, case def via /api/cases | ✅ sufficient |
| run_447ccd4b | no primary | not_recommended reasons + 6 uncertainties + human_review_required; card flags | ✅ sufficient — exactly the F27-02-type case a semantic reviewer should adjudicate |
| run_48cc028f | trace-only (no case_state) | 3 stages, 3 artifacts, card DEEP_REVIEW fail-closed | ⚠ reviewer must degrade to NEEDS_HUMAN_ESCALATION (card already forces it) |
| run_84f63c7c / run_381c2836 | repair-exhausted | full repair trace (attempts, failed evals, budget=exhausted), card `repair_used` w/ task ref | ✅ sufficient — can judge whether the repair-exhausted conclusion stands |
| run_dad25ef1 | all-10-rejected | candidates + not_recommended + uncertainty provenance | ✅ sufficient |

**Genuinely missing for AI Review (DATA GAPs — backend untouched):**
1. `DATA GAP: live LLM provider` — F13 never exercised; R-05 history;
   a provider policy is the hard prerequisite (without it the reviewer
   runs only in recorded-fixture mode).
2. `DATA GAP: 语义判断金标集` — no labeled good/bad-analysis dataset to
   calibrate precision/recall; bootstrap = 12 pilot owner reviews +
   the pending human-reviewer session results.
3. `DATA GAP: 客户对话上下文` — benchmark cases are static; real chats
   carry intake nuances the reviewer should read (chat persistence
   exists, run↔chat linkage does not).
4. `DATA GAP: 报告数值一致性检查` — amounts repeated across
   artifacts/report are only id-checked offline (RPT-Q), no runtime
   numeric-consistency check family exists.

## 12. §十三 Roadmap (proposal — each phase awaits explicit authorization)

| | Phase R1 | Phase R2 | Phase R3 (optional, later) |
|---|---|---|---|
| 目标 | ai-review-result schema + generator (evaluation domain, fixture-replayable) + calibration dataset bootstrap | decide_v2 router + workspace AI Review/Escalation sections + escalation config | in-run semantic gate for 2 high-value stages (Option C subset) |
| 后端 | additive only: schema + generator + (optional) GET /api/runs/{id}/ai-review mirroring the card endpoint; **no runtime/contract change** | none | YES — runtime change; requires new ADR (ADR-004 amendment) + frozen-transcript replay design |
| 前端 | none | workspace sections + VM extension (tests) | minor |
| 新增 Agent | no (evaluation-domain generator, like the card) | no | bounded in-run reviewer stage (new task type) |
| Schema | NEW ai-review-result.schema.json (additive) | none | eval.rules repairable-map extension |
| 测试 | schema conformance; fail-closed on missing/absent state; determinism over recorded transcripts (no live LLM in tests); card_agreement cases | vitest: verdict rendering, escalation routing, fail-closed reviewer-unavailable; decide_v2 unit matrix | eval-boundary extension tests (reviewer cannot self-pass), replay determinism, budget integration |
| 依赖 | none (fixture mode) | R1 | provider policy (R-05 successor) + B-phase precision evidence |

## 13. STOP

No code, schema, UI, skill, agent, or runtime change made in this
phase. This document is the deliverable (audit + architecture decision
proposal + implementation plan). Next action requires explicit
authorization per phase.
