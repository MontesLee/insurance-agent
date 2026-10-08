# Session Decisions

> Only decisions that constrain future development. Not a changelog.
> Architecture-level decisions graduate to an ADR in docs/production/.

## Decision
Governance UI never owns authority: decisions go through the existing
approve/reject endpoints; the approval state machine stays frozen.

## Context
ADR-017 (governance layer separation); Phase 27.5-4, 27.7.6-D.

## Consequence
"Request Fix" is recorded as REJECT with a `REQUEST_FIX:` reason
prefix (G-27.7.6D-01). A native NEED_FIX state would require a
state-machine change — do not add one casually.

---

## Decision
The Review Card layer (evaluation/human-review/) is an OFFLINE
projection: it imports nothing from runtime/ and never mutates state.

## Context
Phase 27.7.6 v2; zero-runtime-coupling constraint; the card is
served read-only by the API layer computing it in memory.

## Consequence
Card logic changes never risk the agent runtime; the four automatic
dimensions only aggregate eval-engine checks — extend via
risk-rules.yaml bindings, not new validators. A dimension with zero
underlying checks reports FAIL (honesty rule inherited from
eval_engine §19: no UNKNOWN-pass).

---

## Decision
`GET /api/runs/{id}/review-card` is keyed by the run DIRECTORY, not
the in-memory run registry.

## Context
Phase 27.7.6-D; /events and /artifacts are registry-bound and 404 for
pre-restart runs; review cards must survive backend restarts.

## Consequence
Cards work across restarts; run ids are validated against
`[A-Za-z0-9_-]{1,64}` before touching disk. Do not "fix" /events or
/artifacts to match without reviewing their Phase 1 contracts.

---

## Decision
LOW risk flags (style/formatting) are human-only: the generator can
never emit them.

## Context
No detector exists; inventing one would fabricate a capability
(no-fabrication rule, AGENTS.md §9).

## Consequence
They stay declared in risk-rules.yaml with `emit: human_only` for a
closed taxonomy; only human feedback can attach them.

---

## Decision
Windows .bat launchers in this repo are PURE ASCII, health-gated, and
log their backend startup.

## Context
2026-09-24 connectivity regression: start-human-session.bat contained
Chinese + em-dashes saved as UTF-8; under a GBK console codepage cmd
misparsed it byte-wise, the backend never started (and mojibake
redirect created junk files), while the UI opened with "Cannot reach
the runtime server" on every page.

## Consequence
Any new .bat: ASCII-only (Chinese instructions go in a .md), redirect
backend/vite output to tmp/ logs, poll /api/health before opening the
browser, reuse an already-healthy instance instead of double-starting.

---

## Decision
Phase 27.7.8 audit (docs/production/review-architecture-audit-2778.md)
recommends AI Review as a POST-RUN, evaluation-domain, advisory layer
— NOT an in-run agent. PROPOSAL ONLY, pending explicit authorization.

## Context
Read-only architecture audit 2026-09-24: three existing quality layers
(runtime eval engine, Review Card, evals/ offline) are all
deterministic; semantic review exists nowhere; ADR-004 forbids LLM
judgment inside the eval engine; ADR-017 forbids governance→runtime
control coupling; ADR-018 makes feedback evidence-only.

## Consequence
If authorized, build Option B first (ai-review-result schema +
generator beside the card generator; decide_v2 deterministic combiner;
AI may only ESCALATE, never de-escalate; reviewer failure fail-closes
to human). In-run semantic repair (Option C) needs a new ADR. Do not
add an LLM judge to runtime/eval_engine.py.

---

## Decision
Session continuity is file-based: CLAUDE.md protocol + `.agent/`
state files; conversation history is never treated as project memory.

## Context
Phase 27.7.6-E session-management retrofit (2026-09-24); audit found
no equivalent in-repo mechanism (AGENTS.md = conventions, phase docs
= evidence, ADRs = architecture decisions).

## Consequence
New sessions start from CLAUDE.md → .agent/current-task.md →
.agent/checkpoint.md → the pointed phase doc. Checkpoints are updated
at the triggers in CLAUDE.md; keep them concise or they stop being
read.

---

## Decision
Phase 27.9 audit verdict: the system is a "chat-first shell over two
disjoint execution worlds" (chat single-agent with prompt-internal
intent routing vs deterministic pipeline + harness specialist layer
that never meet). Proposed unification via a deterministic-first
Intent Layer + formal chat↔pipeline single-write-path contract +
Roadmap 27.9-A..E. PROPOSAL ONLY — not authorized.

## Context
Read-only audit 2026-09-24 (docs/production/architecture/
chat-first-agent-platform-audit-279.md): chatMode defaults to "agent"
(ChatLayout.tsx:30-32) with live glm provider configured; /api/runs
worker bypasses specialists (server.py:409 orch.run direct); chat
agent never touches Agent Registry/MessageBus (tools.py:463-465);
no QA run class exists (33 cases all planning categories); no
HTML/PDF/export in artifact delivery; governed LLMGateway (Phase 23)
unwired — agent path uses model.py OpenAICompatProvider directly.

## Consequence
If authorized: Phase B (Intent Router + Agent Registry) is the
architectural keystone and REQUIRES a new ADR (deterministic routing,
LLM advisory-only, specialist onboarding as a flagged, default-off
path). Chat stays display+link only for governance (ADR-017): review
outcomes link back to Review Center, never embedded controls. Chat
TASK_EXECUTION and /api/runs must converge on one documented
single-write execution path. Sequencing across 27.9-A..E, 27.8-A..D
and 27.7.8-R1 awaits user decision.

---

## Decision
Phase 28.0 migration plan (docs/production/architecture/
unified-chat-multi-agent-migration-280.md): canonical execution core =
the orchestrator spine (yaml graph + eval_engine + CaseState/artifact
registry + trace/SSE); runtime/agent demotes to Conversation
front-end; runtime/agents absorbs as registry-internal executors; no
orchestrator rewrite. Six ADRs proposed (ADR-019..024, numbers
reserved), incl. code-enforced answer grounding (AnswerContext +
deterministic citation-closure gate) and WeKnora-vs-Catalog boundary
(facts = deterministic catalog lookup, fail-closed on missing data).
PROPOSAL ONLY — not authorized.

## Context
Read-only audit 2026-09-24: three execution paths already converge on
orch._execute_stage; the split is identity+case-lifecycle, not
execution. Every chat turn creates a brand-new case
("agentcase-<run hex>", server.py:489,533-534) — continuation
machinery (replan/approval-resume/cp.resume) exists ONLY in harness
world. KnowledgeService (provider→governance→evidence, fail-closed,
K001-K004) already exists runtime-wired, but chat LLM NEVER sees
evidence chunks (tools.py:402-404 returns "N items stored" only) and
no code gate exists on answer text. Catalog: 12 demo products,
waiting_period/exclusions/health_declaration absent from data AND
schema; no production catalog file; no fact lookup to LLM.

## Consequence
If authorized, execute in dependency order 28.A (Intent Layer +
Router + Registry contract) → 28.C (QA Agent + WeKnora grounding,
first routed agent, no planning-spine risk) → 28.B (runtime
unification with byte-equal behavior regression gate) → 28.D
(planning migration) → 28.E (continuation, needs ADR-024
persistence); 28.F (artifacts) / 28.G (space separation) parallel
after B. Blocking prerequisites flagged: KB corpus (10 docs only),
catalog data engineering (blocks real product QA), dense-retrieval
decision, chat persistence backend.

---

## Decision
Governance hierarchy canonized (Phase 28.1, 2026-09-24): Vision
(why) > ARCHITECTURE_PRINCIPLES (how) > ADR (specific decisions) >
phase docs. CLAUDE.md now carries Project Identity + a mandatory
pre-implementation gate (4 questions; STOP if uncertain). A drift
baseline is fixed in docs/production/governance/product-direction-
audit.md (P0x3/P1x9/P2x4) and /product-audit (read-only command)
diffs future reality against it; the baseline must converge, never
grow. ADR-019..024 remain design-not-license until approved.

## Context
User-mandated north-star governance after the 27.7.7-28.0 audit
chain confirmed: identity/lifecycle split (not execution split)
between chat agent, deterministic pipeline, and unused specialist
layer; structural no-grounding in chat answers; product-fact
questions unanswerable (catalog schema+data gaps). All rules derived
from code evidence, not design docs.

## Consequence
Every future session reads the CLAUDE.md guardrails; large features
must inspect Vision/Principles/ADRs first; phases follow
docs/DEVELOPMENT_CHECKLIST.md Step 0-3 (product alignment gate
before code). Violations of the six principles require explicit ADR
exemption. New parallel runtimes / LLM-without-evidence paths /
router business logic / developer-only business features are
pre-classified as drift (four sentinels).

---

## Decision
Phase 28.0.1 decision gate (2026-09-25,
docs/production/architecture/phase-28-implementation-plan.md): GO —
conditional. Implementation order fixed as ADR-authoring (step 0,
docs-only) -> 28.A (Intent+Router+Registry, SHADOW mode + behavior-
equivalence baseline) -> 28.C (QA+grounding) -> 28.B (runtime
unification, byte-equal gate) -> 28.D -> 28.E; 28.F/28.G parallel
tracks. ADR-019..024 verdict: direction sound, NOT yet valid ADRs
(no standalone files; alternatives + implementation boundaries
missing) — step 0 must write them as full documents before any code.

## Context
Gate audit findings: no in-force ADR conflicts (004/011/016/008 need
explicit alignment notes, not changes); 6 blocking dependencies
(ADR authoring, KB corpus, catalog schema+data, behavior-equivalence
harness, chat persistence backend, ADR-014 identity for 28.G);
8 hidden couplings newly identified — headline: prompts.py intent
clauses must demote to presentation-only once Intent Layer ships
(dual-source-of-truth), tool-description lies must be fixed with
AnswerContext, review-card run-dir keying breaks under multi-run
cases (28.E must redesign), RunManager one-active-run-per-case slot
conflicts with continuation, QA LLM call should route via governed
gateway (ADR-011 debt), AGENTS.md upstream-immutability forbids
touching client-intake/requirement-analysis during absorption.

## Consequence
No implementation until step 0 ADRs are written and approved. 28.A
must ship shadow-mode (record, not arbitrate) + the byte-equality
baseline harness. Red lines enforced for the whole cycle: no
orchestrator rewrite, no eval-gate ownership change, no parallel
runtime/artifact/run stores, no LLM in router, no unevidenced
insurance facts, no deletion of demo mode/harness/specialists/tests.
Every phase closes with full regression baselines + negative
self-checks + /product-audit baseline-diff convergence.

---

## Decision
Phase 28.0.2 (2026-09-25): ADR-019..024 finalized as formal
PROPOSED documents in docs/adr/ (the repo's ORIGINAL ADR home —
ADR-001..007 already lived there; ADR-008..018 live in
docs/production/). Numbering reassigned per user spec vs the
migration-280 provisional set: 019 Intent Layer, 020 Router
Contract (split from old 020), 021 Agent Registry, 022 Knowledge
Grounding (absorbs WeKnora/Catalog boundary), 023 Chat Artifact
Experience (NEW topic, ex-28.F), 024 Conversation/Case/Run
Lifecycle. Old provisional 019 "Unified Runtime" NOT filed (open
item O-1 — carried by implementation-plan §5 + migration-280 §11
until a dedicated ADR is requested).

## Context
Gate audit had found all six proposals "direction sound, not valid
ADRs" (no files/alternatives/boundaries). Each formal ADR now has
nine sections incl. rejected alternatives and implementation
boundaries; gate-audit hidden couplings baked in (prompts.py demotion
in 019; import whitelist in 020; TASK_AGENT_MAP equivalence in 021;
tool-description fix + gateway routing + FAIL-CLOSED in 022;
renderer uniqueness in 023; card run-dir keying + RunManager slot
in 024). Dependency map + per-ADR implementation gates docs created.

## Consequence
Nothing is approved yet — all six remain PROPOSED; approval unlocks
per adr-dependency-map §4 / phase-28-implementation-gates 汇总:
019+021+020 -> 28.A; +022 -> 28.C; O-1 ruling + equivalence gate ->
28.B/D; +024 -> 28.E (card re-keying FIRST); 023 anytime -> 28.F.
Decisions reserved for approval time: qa-answer artifact/Review
Card policy (022), intent confidence threshold (019), server-side
PDF (023, default no).

---

## Decision
Phase 28.0.3 review board (2026-09-25,
docs/production/architecture/adr-approval-review-2803.md): 020/021/
022/023 APPROVE (with board rulings recorded: intent=Hybrid,
truth in schema+rules+events NOT prompt; registry v1=configuration
form; insurance facts REQUIRE evidence unconditionally, missing=
fail-closed refusal template; v1 default output=Markdown, PDF=
browser print, server PDF future). 019 MODIFY (add conversation-
context input clause — anaphoric messages like "改成30万" have no
keywords; context signal incl. active_case_present required).
024 MODIFY (add feedback-anchor clause binding feedback to run+
artifact version; add data_policy/451-gate + retention alignment
as implementation prerequisite). No REJECT. O-1 ruling recommended:
create ADR-025 but author it just before 28.B (highest-risk change
deserves an ADR home; details depend on 28.A/28.C findings). Eight
human decisions listed (HD-1..8) with recommendations.

## Context
Author-reviewer separation: the board re-examined all six ADRs
against five criteria. Two real gaps found (context-anaphora input
for intent; feedback version-anchoring after plan modification);
both are v1-day-one inputs, not v2 niceties. ADR-020 confirmed
tightest (three enforcement layers: contract text, import
whitelist, CI boundary test). ADR-024 confirmed highest blast
radius (card keying / RunManager slot / store overlay).

## Consequence
ADR files NOT edited by the board (proposed amendment texts await
owner confirmation — HD-8). 28.A unlocks upon: 019(+M1)/020/021
approval; 28.C additionally needs 022 + HD-2; 28.B/D need HD-4
(ADR-025) + equivalence gate; 28.E needs 024(+M1/M2) + HD-5 + 28.D;
28.F needs 023 + HD-3 (anytime after 28.B).

---

## Decision
Phase 28.0.4 governance freeze (2026-09-25): canonical product/
architecture baselines are NOW docs/production/architecture/
PRODUCT_VISION.md + ARCHITECTURE_PRINCIPLES.md (FROZEN v1.0; six
principles: Chat is the Product Surface / Intent != Prompt /
Router is Deterministic / Insurance Fact Requires Evidence /
One Runtime / Human Review is Escalation). The Phase-28.1 files
at docs/PROJECT_VISION.md + docs/ARCHITECTURE_PRINCIPLES.md were
DEMOTED TO NAVIGATION STUBS (content fully merged — prevents the
dual-source-of-truth the freeze exists to prevent). CLAUDE.md
guardrails v2: Product Alignment Check (4 questions), Architecture
Drift Detection (git-diff watch on orchestrator/agent-execution/
artifact-lifecycle -> "Architecture Impact Detected"), Forbidden
Actions (6 absolute bans). /product-audit upgraded to v2 output
contract (six PASS/FAIL sections + ADR-drift file list + final
GREEN/WARNING/BLOCKED with explicit verdict rules). New
docs/templates/feature-proposal-template.md (12-line proposal
gate). Spec's ".commands/" interpreted as .claude/commands/
(functional Claude Code dir; no dead root copy created).

## Context
28.0.4 mandated near-duplicates of the 28.1 governance docs at
new paths while also requiring "avoid duplicate rules" — resolved
by canonicalization + stubs. No conflicts with AGENTS.md (skill
layer) or any ADR; principles deliberately precede ADR-019..024
approval (they describe the target state; if the ADR set is
trimmed, revisit Principle 2/3 implementation wording only).

## Consequence
Single authoritative vision/principles; every session gets the
alignment gate + drift detector + 6 bans via CLAUDE.md; feature
work requires the proposal template; /product-audit produces
GREEN/WARNING/BLOCKED verdicts (BLOCKED = forbidden-action pattern
or P0 regression). HD-1..8 queue unchanged. Baselines are FROZEN:
edits require explicit owner decision.

---

## Decision
Phase 28.0.5 (2026-09-25): OWNER FINAL RULINGS applied. ADR-019
APPROVED with M1 in text (intent input = message + recent
conversation context + active case context; context unavailable ->
modify intent -> clarification; prompt NEVER an intent source).
ADR-020 APPROVED as-is (deterministic router; three layers: schema
contract + import boundary + CI tests). ADR-021 APPROVED as-is
(v1 = configuration based; runtime dynamic registry forbidden).
ADR-022 APPROVED as-is (insurance fact grounding required:
product fact/coverage/waiting period/exclusion/policy term from
Catalog or WeKnora evidence only; missing = fail closed). ADR-023
APPROVED as-is (v1 = Markdown default; HTML/PDF = future scope
from v1; renderer uniqueness + L1 rules effective v1). ADR-024
APPROVED_WITH_CONSTRAINTS (added #5 feedback binding run_id+
artifact_version — prevents future cross-version feedback
contamination; added #6 data policy: retention/access-boundary/
deletion-strategy must be defined first, else implementation
BLOCKED — conversation persistence + data-retention paths
explicitly blocked until then).

## Context
Owner acted on the 28.0.3 review board matrix. Decision record:
docs/production/architecture/phase-28-decision-freeze.md.

## Consequence
Implementation unlocked: 28.A (Intent+Router+Registry, shadow
mode). Blocked: 28.C until KB dataset decision (+HD-2 before
start); 28.E until ADR-024 boundary (3 data-policy definitions);
28.B/D per gates (O-1/ADR-025 before 28.B + equivalence gate).
HD-1 filled from 28.A shadow data. ADR text changes from here on
go through explicit ADR revision flow, never silent edits.

---

## Decision
Phase 28.A-0 (2026-09-25): Intent Layer CONTRACT foundation landed
— schema/intent-result.schema.json (v1 5-intent enum, confidence +
rule|llm|hybrid source, nullable context_refs, reason_codes>=1,
additionalProperties:false structurally bans workflow/skill/tool/
agent fields; if/then encodes ADR-019 M1: modify_existing_plan
without active_case_id requires clarification_required=true),
schema/router-decision.schema.json (decision_source only
registry_lookup|fallback|blocked — NO llm value structurally;
registry_lookup iff validation.valid; invalid intent result can
only route fallback/blocked), schema/agent-registry.schema.json
(ADR-021 v1 declaration subset, 8 fields, closed — execution
fields deferred to a versioned revision with 28.A-1+). 10
contract tests (six mandated checks mapped; frozen golden v1
vocabulary; pytest + standalone dual-run) in tests/contract/.
Zero runtime/web changes; no router wiring; no execution-path
change. Root schema/ dir is NEW (platform contracts; contracts/
remains artifact contracts).

## Context
First implementation phase under the approved ADR-019/020/021 +
frozen governance baselines. CLAUDE.md alignment check recorded
in phase-28a0-report.md.

## Consequence
28.A-1 (intent rules module, intent_classified events dual-ended,
shadow mode + consistency report, prompts.py demotion,
equivalence baseline, HD-1 calibration) is the next unlocked
step, awaiting authorization. Contract vocabulary changes from
here require versioned schema revisions — never silent.

---

## Decision
Phase 28.A-1 (2026-09-25): intent layer runtime foundation landed in
SHADOW mode. runtime/intent/classifier.py (deterministic-first: rules
fast-path -> optional LLM candidate [advisory, provider not yet wired]
-> deterministic resolver -> schema final gate fail-closed to unknown;
HD-1 floor 0.75 for high-risk LLM proposals), config/intent-rules.yaml
(externalized versioned rules; signal hierarchy: specific-product >
evaluative+anchor > modify-verb > plan-action > definition/concept;
familial words never fire plan; insurance anchors required so
out-of-domain text degrades to unknown), runtime/agent_registry.py
(config-based loader; fail-closed startup: schema violation /
out-of-vocabulary intent / ambiguous claim / missing unknown-agent
all refuse to boot; NO mutation API = dynamic registration
structurally impossible), runtime/router.py (lookup/validate/dispatch;
table derived from registry; invalid IntentResult routes as unknown
with errors preserved — bogus value never leaks into contract docs),
runtime/intent/shadow.py (JSONL records; sha1+24-char head, never full
text; annotate legacy_intent post-run), intent_classified added to
EVENT_TYPES, server wiring: registry load in RunManager.__init__ +
fail-quiet shadow block in _agent_worker + post-run annotate.
prompts.py intent clauses DEMOTED to behavioral reference (authority
= Intent Layer; agent_decide reporting kept for shadow comparison).
Production execution path UNCHANGED (actual_execution=existing-agent).

## Context
Rule hierarchy refined during corpus tracing: familial/financial
context words alone must not fire insurance_plan (guidance stays
guidance); specific product references (P001/这款) override definition
phrasing; evaluative markers (怎么样) require an insurance anchor so
"今天天气怎么样" degrades to unknown instead of product_qa.

## Consequence
Full battery 629 passed / 0 failed (599 baseline + 20 new + 10
contract). Shadow corpus baseline: 22/22 v1-correct, 100% legacy-mapped
agreement, unknown 14% (docs/production/reports/
intent-shadow-report-2026-09-25.md). Live shadow traffic accumulates
after next server restart. Next candidates: 28.A-2 (LLM candidate
provider wiring + HD-1 calibration from live shadow data) or router
go-authoritative decision (28.B scope, needs ADR-025 + equivalence
gate). Web event type for intent_classified intentionally deferred.

---

## 2026-09-25 — Phase 28.A-2: LLM candidate advisory-only adapter + context signals (ADR-019 rules 1/7)

## Decision
1. LLM candidate integration shape: adapter (runtime/intent/
   llm_candidate.py) accepts an INJECTED provider object (LLMProvider
   protocol) — never constructs or imports one; env-gated
   INSURANCE_AGENT_INTENT_LLM=1, default OFF. Candidate output
   contract is closed: {intent, confidence, explanation?, evidence?};
   any of agent/workflow/decision_source/tool/skill/action keys is
   REJECTED (parse -> None -> llm:invalid_proposal); timeout/transport
   RAISES (-> llm:candidate_error); rules fast path never consults the
   LLM; the deterministic resolver + schema gate always decide (HD-1
   floor from rules file, quoted as provisional).
2. Context-aware classification scope (ADR-019 rule 7): ONLY
   demonstrative product references (那款/这款/这个产品/那款/P0xx) may
   inherit the insurance-domain anchor from conversation context;
   evaluative phrasing NEVER inherits (mid-conversation "今天天气
   怎么样" must stay unknown). Externalized switch
   context.anchor_inheritance in config/intent-rules.yaml.
3. Shadow observability schema (records only; IntentResult schema
   UNTOUCHED): reason_codes, derived resolver outcome, latency_ms,
   post-annotate mismatch_type ([]=agreement; intent_difference/
   confidence_difference/missing_context; legacy absent = not
   comparable, excluded from the agreement denominator).
4. intent_classified web-contract sync: BLOCKED_FOR_IMPLEMENTATION
   this phase (web/** outside allowed paths) — recorded in
   docs/production/decisions/2026-09-25-28a2-web-event-contract-sync.md;
   must close before 28.B authority switch.

## Context
28.A-2 mission: complete Intent Layer maturity without changing
production routing. Two touches beyond the literal allowed-path list
(runtime/server.py shadow block, config/intent-rules.yaml rule
content) were required by the observability/context mandates and kept
minimal-additive in the same fail-quiet pattern 28.A-1 established —
flagged explicitly in phase-28a2-report.md git review.

## Consequence
Corpus regression drift-free (22/22, identical distributions). New
suite 17/17; full battery 646/0 expected over the 629 baseline. Live
calibration report tooling ready (report.py --shadow); 8 pre-A-2 live
records tolerated (missing fields reported, not fabricated). 28.C
readiness: CONDITIONALLY READY (3 human decisions + HD-2).

---

## 2026-09-25 — Phase 28.C-0: QA Agent design rulings (docs-only, pending owner D1-D6)

## Decision
Design delivered without implementation (phase-28c0-qa-agent-design.md).
Four design positions adopted in the document, all flagged for owner
confirmation before 28.C-1: (1) AnswerContext v1 = schema-validated
RUN-SCOPED record, NOT a new contracts artifact_type — avoids
eval.rules/risk-rules/contracts triple linkage + Review-Card all-red
cascade (coupling #8); (2) QA LLM calls should go through the ADR-011
gateway (runtime/llm/gateway.py — implemented, unwired) repaying the
R6 bypass debt on the only new LLM call point; (3) citation-closure
gate is deterministic code BEFORE delivery (cited⊆evidence + fact-
sentence coverage + one bounded regeneration then refuse) — LLM never
self-audits, hallucination structurally unreachable at the delivery
surface; (4) confidence in contracts comes ONLY from bounded retrieval
scores, never model self-reports.

## Context
Owner decision (phase input): proceed with QA Agent BEFORE the full
Router authority switch (28.B) — consistent with ADR-020 migration
("28.C 起 QA 意图真实路由" = first authoritative slice, insurance_qa +
product_qa only; all other intents stay shadow/existing path).

## Consequence
Zero code this phase (git: docs + .agent + memory only). 28.C-1
implementation order fixed in the design (schema → gate → AnswerContext
seam + tool-description fix → gateway wiring → execution unit + QA
authority slice → e2e). Open: D1-D6 owner rulings; B3 catalog schema
step 1; HD-2 KB dataset (blocks value, not code).

---

## 2026-09-25 — Phase 28.C-1: QA Agent production slice (rulings D1-D4/D6 applied)

## Decision
First Intent->Agent production slice went live: insurance_qa turns in
the chat path route (Router registry lookup) to the Insurance QA Agent
instead of the general chat agent (ruling D4). All other intents keep
the existing path byte-for-byte; global router authority remains
disabled (28.B). Applied rulings: D1 AnswerContext is a run-scoped
schema-valid record (schema/qa-answer-context.schema.json, closed
draft-07) — NOT an artifact, never in contracts enum or the artifact
registry; D2 QA LLM calls go through the LLM Gateway — first wiring of
runtime/llm/gateway.py (R6 bypass debt repaid) via a thin
_GatewayProviderAdapter (GLMProvider pattern), process-level singleton;
D3 grounding is a deterministic code gate (citation closure: cited ⊆
evidence_map + externalized fact-marker sentences need in-sentence
citations + one bounded regeneration then refuse); D6 catalog_missing_
fact fail-closed value/template reserved for the product_qa slice.
Ops kill-switch INSURANCE_AGENT_QA_SLICE=0 (default ON).

## Context
Owner decision: QA Agent before the full Router authority switch —
consistent with ADR-020 migration ("28.C 起 QA 意图真实路由"). One
existing test fixture adapted (test_agent_api SSE case message switched
to plan wording) because its insurance_qa-worded fixture would now
correctly route into the slice; the test targets SSE plumbing and its
script/asserts are unchanged.

## Consequence
Battery 662/0 (646 + 16 new; zero regression). Hallucinated citations
are structurally unreachable at the delivery surface (scenario E).
Conflict -> deterministic both-sides template (never averaged).
Failures kb_unavailable/insufficient_evidence/llm_unavailable/
citation_gate_rejected all produce honest refusals. Known: non-strict
server without weknora env grounds QA on fixtures (deploy with weknora
env or strict mode); product_qa slice + catalog path = next step.

---

## 2026-09-25 — Phase 28.C-2: Product QA slice + shared grounding (autonomous)

## Decision
1. Shared module extraction (spec >30% rule): runtime/grounding/ now
   owns the citation gate, AnswerContext builders, and the grounded
   generation attempts loop; runtime/qa_agent/{gate,context} are
   compatibility shims — C-1 tests unchanged and green
   (behavior-equivalence by verbatim move).
2. Product evidence boundary (ADR-022 §1 table implementation reading,
   recorded in phase-28c2-pre-audit §7): resolved product -> E1
   deterministic version-pinned CATALOG record + E2.. governed evidence
   QUALIFYING for the product (evidence_refs-linked document or content
   naming the product). Generic category knowledge never substitutes
   for a specific product's parameter; an asked parameter absent from
   both the catalog record and qualifying evidence fails closed
   (catalog_missing_fact, ruling D6). The knowledge service is ALWAYS
   queried — its outage refuses the turn even with a catalog anchor
   (K003).
3. product_qa production slice rides the same seam behind
   INSURANCE_AGENT_PRODUCT_QA_SLICE, DEFAULT OFF (spec Step 3; unlike
   the D4 knowledge-QA slice). Both behaviors belong to registry agent
   insurance-qa-agent — routing table unchanged.
4. Intent layer: catalog product names/ids are now a deterministic
   specific-product signal (rule:product_qa_catalog_name:P0xx) via
   runtime/catalog_refs.py; corpus 22/22 drift-free.
5. 28.B readiness (read-only): NOT READY — blockers B-1 web event
   contract sync, B-2 B4 equivalence gate, B-3 ADR-025, B-4 live shadow
   calibration, B-5 planning target behavior; recommended order fixed
   in phase-28b-readiness-audit.md §8.

## Consequence
Battery 677/0 (662 + 15). Catalog is now a production evidence source
(deterministic, version-pinned). Spec example name "健康满分" absent
from demo catalog — scenario A ran against real P001 (documented). No
STOP rule triggered; ADR/vision/orchestrator/artifact-contracts/
approval/WeKnora untouched (git verified).

---

## 2026-09-25 — Phase 28.B prep: web event contract synced via canonical vocabulary file

## Decision
1. New canonical contract source schema/event-vocabulary.json:
   "vocabulary" (52 types, generated FROM runtime/events.py EVENT_TYPES —
   backend test asserts EXACT equality, no drift either direction) +
   "reserved" ([grounding_started, grounding_completed] — contract-first:
   frontend-receivable types with NO backend emission yet; a future
   backend addition must consciously graduate them out of reserved).
2. web/src/types/runtime.ts EventType union rewritten to the FULL
   vocabulary + reserved (54). Discovery: the old union had only 22 of
   52 backend types — planner/multi-agent/approval/checkpoint types were
   already untyped (silent-swallow exposure predates this phase).
   runReducer TRANSITIONS relaxed Record -> Partial<Record> (type-only;
   the lookup was already undefined-safe by design).
3. Dual-end guards: tests/contract/test_event_vocabulary.py (backend
   side, in the pytest battery) + web/src/types/runtime.test.ts
   (frontend side, in vitest; jsdom-safe cwd-based repo-root discovery —
   import.meta.url loses the file scheme under jsdom).
4. No UI changes (spec); AgentActivity v2 = design doc only; grounding/
   route standalone emissions remain runtime-authorized future work,
   listed as P-3/O-5/O-6 in the migration checklist.

## Consequence
Frontend can now receive intent_classified/qa_answered/
grounding_started/grounding_completed at the type level; the dual-end
drift risk (coupling #3) is closed by tests. Backend 681/0 (677+4);
web 148+2 skipped, tsc clean. runtime/** untouched.

---

## 2026-09-25 — Phase 28.B3: ADR-025 filed + B4 design + golden inventory

## Decision
1. ADR-025 (Router Authority Migration) filed as PROPOSED per spec
   mandate — the O-1 open item closes INSIDE it by declaration: the
   authority migration creates NO new runtime; "unified runtime" = the
   existing server+orchestrator spine with router-dispatched behavior
   units (Principle 5). Eight mandated topics are explicit numbered
   Decision subsections; migration stages M0..M5; equivalence split
   into E1 byte-level (planning) vs E2 contract-level (QA).
2. B4 gate is DESIGN ONLY: same-process dual-run over golden cases;
   six comparators with an event-normalization rule (additive event
   types stripped; timestamp/latency whitelisted) and negative probes
   (hallucination injection must be gate-rejected — proving the gate is
   alive); per-case PASS|RED; self-equivalence precheck before any
   baseline is trusted.
3. Golden case inventory (25 cases, PENDING_CAPTURE) covers all five
   intents with negative anchors (D6 double-missing, no-sales-advice,
   never-default-to-planning, fail-closed clarification) and documents
   that modify cases assert CLARIFICATION-phase expectations while
   ADR-024 continuation remains BLOCKED.
4. Readiness verdict: M0 complete / M1 achieved / M2 startable / M3+M4
   blocked on enumerated gates. No STOP triggered in-phase; the STOP
   surface is moved to M3/M4 entry conditions.

## Consequence
Governance + equivalence foundation for the switch is in place on
paper; nothing executable changed (docs-only, git verified). Next
human actions: rule on ADR-025, authorize M2 gray-enable, then
authorize B4 implementation + baseline capture.

---

## 2026-09-25 — Phase 28.B4: B4 gate implemented; hermetic-runner ruling

## Decision
1. The B4 gate is TEST infrastructure at runtime/evaluation/
   router_equivalence/ (new namespace deliberately under runtime/ per
   spec structure; distinct from the top-level evaluation/ engine —
   ADR-004 territory untouched; never on the production execution
   path). Same-process dual-run: legacy = all slice flags OFF,
   candidate = case flags; per-side fresh RunManager/EventBus/run_root.
2. HERMETIC RUNNER RULE: the gate forces INSURANCE_AGENT_NO_DOTENV=1.
   Rationale (found the hard way): a bare CLI run reads the repo .env,
   and a configured LLM_FAST_MODEL makes create_agent_run build a LIVE
   fast provider that replaces the scripted FakeLLM in both the QA
   slice (fast_provider or provider) and the legacy chat agent — the
   gate went nondeterministically 4-RED. pytest masked this because
   tests/_common sets NO_DOTENV via setdefault. Any future harness that
   drives the server with scripted providers must do the same.
3. Safety-probe golden cases must script BOTH failing generation
   attempts: FakeLLMProvider returns the neutral text "(fake provider
   exhausted)" once the script runs out, which can PASS the citation
   gate and mask a probe.
4. M2 gray observation rides the EXISTING
   INSURANCE_AGENT_PRODUCT_QA_SLICE flag (no second flag; single
   source of truth). Observability added instead: shadow
   slice_decision {slice, fired, reason} + slice_error annotation on
   crash-fallback. Normalizer volatility whitelist is closed
   (trace_id included); new payload fields default to COMPARED (drift
   surfaces, never hides).
5. The p14 isolation test greps runtime/** for the literal substring
   "evals/" — docstrings count; keep the new package's wording clean.

## Consequence
Gate is CI-resident (7 new tests; 14/14 cases PASS, 0 RED; report at
docs/production/reports/router-equivalence-report.md). Backend 688/0
(681+7); web unchanged 148+2 + tsc clean. Authority not switched;
ADR-025 untouched; no blocker doc (no STOP condition hit).

---

## 2026-09-25 — Phase 28.B5: M2 gray enable + rollback drill (operations)

## Decision
Gray enablement executed on an isolated real server instance with
INSURANCE_AGENT_PRODUCT_QA_SLICE=1 (live glm + mock governed
knowledge; composition documented, not disguised). The rollback drill
is the phase's core deliverable and PASSED: flag=0 + restart re-runs
the same product set through the legacy path (5/5 flag_off reasons, no
slice events, no AnswerContext) while insurance_qa/planning/unknown
remain unaffected. All findings recorded with explicit INSUFFICIENT
LIVE SAMPLE markers (scripted smoke traffic only, no real users).

## Consequence
M2 mechanics (flag/telemetry/isolation/rollback) proven on a real
server. Two model-fit issues surfaced honestly: live-model citation
compliance (2/4 generation-reaching turns citation_gate_rejected —
gate fail-closed, zero ungrounded delivery) and one provider timeout
(174.6s -> llm_unavailable). Candidate follow-ups (authorized):
citation-format prompt strengthening; timeout/retry calibration in the
externalized rules file. Zero code changes this phase; 688/0 + web
148+2 + tsc clean.

---

## 2026-09-25 — Phase 28.B5.1: prompt externalization + watchdog (model-fit)

## Decision
1. System prompts left the code: both QA agents now load their prompt
   from the existing externalized rules files (prompt_version v1->v3,
   two calibration rounds against traced failure modes: full-width
   parens, summary-style uncited bullets, speculation bridges,
   uncited disclaimer sentences, unbounded length). The GATE, its
   vocabularies and thresholds are pinned unchanged by tests.
2. The gateway adapter now ENFORCES request.timeout_s via a wall-clock
   watchdog (llm TimeoutError, retryable — the gateway's existing
   retry policy handles it). This is a wiring fix making the
   externalized budget real, not new architecture; total generation
   budget bounded at 240s worst. timeout_s 30->60 based on traced
   legitimate slow successes (~50s).
3. E-scenario recommendation probes remain gate-rejected by design —
   compliance metrics exclude them (refusal is the safe outcome), and
   the exclusion is stated openly in the report.

## Consequence
Citation 2/4 -> 3/4 (residual = model variance + disclaimer-style
answers on recommendation prompts); timeout failures eliminated
(0 llm_unavailable; all walls <= 154.3s < 240s budget). B4 14/14 PASS
under the new rules; backend 703/0 (+15); web 148+2; tsc clean.
Further compliance gains flagged as owner decisions (model-tier
experiments, or fact-marker exemption for disclaimers = gate-semantics
change).

---

## 2026-09-25 — Phase 28.B6: ADR-025 approved (owner record); M3 gate READY

## Decision
1. ADR-025 approved via Owner decision record appended to the EXISTING
   Status section (scope = governance framework + per-stage gating;
   every stage still needs separate authorization; rollback contract
   is a hard precondition; M3 separately gated). Technical content
   untouched and pinned by test.
2. Planning prompt FROZEN by sha256 (three-part discipline: hash
   update + baseline re-capture + review, enforced by test).
3. Planning E1 baseline captured and committed as fingerprints
   (tests/golden/planning-baseline.json) with a cross-process tripwire
   test; the M3 candidate must reproduce them byte-for-byte under the
   UNCHANGED comparator/normalizer.
4. Two governance debts registered rather than hidden: planning
   narrative text has no code-level citation gate (M3 contract
   forbids agent-level fact invention; code gate = future owner
   decision) and chat-path GATE auto-approve (V0.1).
5. Future flags (PLAN_SLICE / ROUTER_AUTHORITY) proven inert until
   M3/M4 code exists — authority cannot switch by env side effect.

## Consequence
M3 gate = READY FOR IMPLEMENTATION (pending explicit authorization).
Backend 713/0 (+10 preflight); web 148+2; tsc clean; B4 GREEN 17/17.
Zero tracked-file changes this phase; authority OFF; planning slice
OFF; M3 not started.

---

## 2026-09-25 — Phase 28.D (M3): planning slice implemented; authority still OFF

## Decision
1. The planning behavior unit is a GUARD + MOUNT: the existing chat
   tool-stack mounted on the planning registry entry (the migration
   plan's original 28.B semantics), behind
   INSURANCE_AGENT_PLAN_SLICE (default OFF). Identity + guard only —
   no second runtime, no new events/artifacts; spine exceptions
   propagate so crash semantics stay byte-identical to legacy (E1
   requirement).
2. E1 is now REAL: golden candidates run as insurance-planning-agent
   and reproduce the committed baseline fingerprints byte-for-byte
   (B4 17/17 GREEN; firing verified non-trivial; trivial-note test
   inverted).
3. Router Authority remains OFF — the M4 raise (staged no-plan→full,
   demo-map + legacy tool-selection retirement) needs separate owner
   authorization per ADR-025.

## Consequence
Backend 720/0 (+7); web 148+2; tsc clean; gray observation + rollback
drill passed on a real server (plan fired with correct live behavior;
M1 clarification live-verified; isolation intact). Integration
root-caused one test-infra env leak (runner BASE_OFF now restores
PLAN_SLICE) and updated two stale assertions to M3 reality.

---

## 2026-09-25 — Phase 28.M4: staged Router authority; gate held

## Decision
1. Router authority is a SINGLE staged resolver (slices/no-plan/full)
   with fail-closed config (invalid => nothing fires). Authority
   coverage per ADR-025 §5; unknown never staged. One reader module,
   test-enforced.
2. The unified dual-run IS the B4 gate with staged candidates (17/17
   GREEN). Authority mode is behaviorally EQUIVALENT to flag mode
   (same execution identity/result); the only observable difference
   is the honest slice_decision reason=authority.
3. Production authority was NOT raised: code default = slices, no
   persistent env change, isolated instances torn down. The phase
   stops at the production authorization gate — owner decision
   required (recommended path: no-plan gray with real traffic first,
   then full + M5 cleanup authorization).

## Consequence
Backend 729/0 (+9); web 148+2; tsc clean; B4 GREEN. Rollback verified
in code, tests, and a live three-phase drill (no-plan -> full ->
unset). Remaining M5 cleanup surface (demo keyword map, legacy chat
tool-selection as unknown carrier, prompt intent clauses) untouched.

---

## 2026-09-25 — Phase 28.M5-A: no-plan production gray observed; gate held

## Decision
Owner authorized ROUTER_AUTHORITY=no-plan for controlled production
gray. Deployed on an isolated instance (the Owner's :8000 process is
OLD code and was NOT touched — cutover is an owner action). Real user
traffic was ZERO, so INSUFFICIENT LIVE SAMPLE remains explicitly
maintained; all metrics come from 10 clearly-tagged injected probes.

## Consequence
Staging mechanics verified under the production-shaped composition:
authority triggered every QA-class turn, planning stayed isolated,
zero safety violations, zero ungrounded delivery, rollback drill
passed. Operational finding surfaced honestly: live-model citation
compliance dropped to 1/7 this round (vs 3/4 in B5.1) — the gate
refused everything non-compliant (6 honest refusals), but refusal
rate is now the top owner-attention item (candidate mitigations
already on record: model-tier experiments; disclaimer exemption =
gate-semantics change needing explicit approval). Full authority NOT
enabled; next gate = explicit owner authorization.

---

## 2026-09-25 — Phase 28.M5-B: full-authority gray validated; permanent state NOT decided

## Decision
Owner authorized a controlled full-authority production gray. Executed
on an isolated instance (owner's :8000 process untouched); code
default remains slices; slice-flag semantics preserved; no cleanup
performed. The routing matrix (10/10), planning full-path (identity/
workflow/behavior/cross-case), safety probes S1-S5, B4 equivalence,
rollback drill, and full regression all PASSED. Real-user traffic
remained zero — INSUFFICIENT LIVE SAMPLE explicitly maintained and
the report states the technical-path-vs-production-effectiveness
distinction verbatim.

## Consequence
Full Authority is a validated CONTROLLED configuration, not a
permanent switch: permanent full, M5 cleanup, and the
citation-compliance mitigation all await explicit owner decisions.
The live-model citation compliance (1/7 across two consecutive
phases) is now a stable operational finding — the gate refuses
everything non-compliant (zero unsafe delivery) but the refusal rate
is the main usability cost of full-authority QA exposure.

---

## 2026-09-25 — Phase 28.M5-C: real-traffic window on the production port

## Decision
The stale :8000 process (pre-M-series code, idle) was restarted onto
current code with runtime-level ROUTER_AUTHORITY=full per this phase's
explicit owner authorization (standard documented command; no invented
deployment). A 13-minute observation window ran on the real production
port with strict traffic classification.

## Consequence
REAL_USER = 0 (web UI not running; instance bus counter proves only
probe traffic) — INSUFFICIENT LIVE SAMPLE maintained; probes and the
concurrent regression battery's 109 shadow records were separated by
chat-id prefix AND the instance's own run counter, never conflated.
All routing/planning/safety/grounding behaviors matched the M5-B
baseline on the production port; rollback drilled and the instance
restored to the authorized full-gray state. Permanent authority, M5
cleanup, weknora provisioning, and citation mitigation remain owner
decisions.

## K.29-B (2026-10-01晚~10-02)
1. **发现不修原则执行**:loop.py system_prompt 丢弃(P1)、judge ws/
   metadata 校准债——均在封印 span,本阶段 STOP 记录,修复=Owner
   另立阶段(建议合并为一个"QA 链路修复"阶段:P1 修复+A 臂重测)。
2. **benchmark 端点**:按量 429/1113 耗尽 → Owner 指示 coding plan;
   进程 env 注入,.env 未动(未来 :8123 重启会失败=Owner 知晓项)。
3. **A2 诊断臂设计**:同 A 但系统提示词实达——量化 P1 影响而非
   替代生产判断;D-04「模型能力」结论据此限定条件重读。
4. **三分类 genuine 口径**:未引用/ws 伪影/真未支持;evidence-meta
   广义正则事后统一(幂等);strict 生产语义处处保持。
5. **Verdict=NEEDS_MORE_BENCHMARK**:安全面无 by-construction 阻断,
   但 strict 支持率 26-27%/PARTIAL 42% 使 29-C shadow 信号不可
   解释;五缺口列于报告 §10.2。

## OD-FIX3-98 = APPROVED (2026-10-07 01:4x, Owner task directive)
- Owner 确认 S-N5 remediation（SN5_REMEDIATED·flashx→flash·429=0）并授权
  Batch-2 physical distribution（tmp/pilot-keys/distribute/{03,04,05}.key·
  HANDOFF-s2-batch2.md·入口 http://localhost:5273）。
- 授权范围 = 仅 key 分发 + Phase16 真实样本采集。
- 不授权：Full Authority / 自动 promotion / S2 / Hybrid / taxonomy·τ·D-04 修改 /
  cohort 扩大 / 自动 recovery。
- Preflight 全 PASS（S-N5/rollback/Phase16 计数 0/0/kill ABSENT/G11 0/30/
  keys 3/3 token-only 且 whoami 有效/前端 5273+代理 200）。
- "Authority=OFF" 核对项释义（留痕）：= Full Authority NOT GRANTED；
  Phase16 controlled authority = ARMED（Owner 批准的实验配置·未变）。
- 分发状态（Owner 选择）: 稍后分发——DISTRIBUTION_PENDING_OWNER_DELIVERY；
  Owner 回报物理分发完成时刻后起算真实样本积累（不伪造起点）。
