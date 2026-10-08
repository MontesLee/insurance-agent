# Review Workspace IA Audit — Phase 27.7.7 Step 1

Date: 2026-09-24 · Method: code read (ReviewWorkspace.tsx + client.ts +
types) + live API matrix on real staged HR runs (run_9de5882e complete,
run_447ccd4b high-risk/no-primary, run_dad25ef1 no-candidates,
run_84f63c7c no-evidence/partial artifacts). No code changed in this step.

> **STATUS: Steps 2–4 implemented and live-verified the same day.**
> View model: `web/src/components/review/viewModel.ts` (+12 unit tests);
> UI: `ReviewWorkspace.tsx` rewritten to the 9-section IA below;
> workspace tests rewritten against real-shape fixtures (18 tests);
> gates: tsc clean, vitest 144/2s; browser reality-test on
> run_9de5882e (complete+restored), run_447ccd4b (no-primary, 🔴1/🟡8
> review items), run_48cc028f (trace-only, full 暂无信息 degradation) —
> screenshots in `screenshots-2777/`. One live-test fix: only genuine
> `deductible` constraints carry the 免赔额 label. DATA GAPs in §5
> remain open (backend unchanged by design).

## 1. Current information architecture (as built through 27.7.6)

| Section | Data source | What the reviewer actually sees |
|---|---|---|
| A 审批摘要 | /api/approvals/{id} | approval_id, request_type, project, task_id, stage, created_at, wait time, decision fields — **system internals first** |
| B 案例上下文 | /api/projects/{id}/supervisor | 6 of 9 fields are hardcoded "—" + supervisor status/risk_level (runtime internals) |
| A2 Review Card | /api/runs/{id}/review-card | level badge, 4 validation chips, customer dl, agent decision, risk findings, failed checks — good content, machine-flavored framing |
| C 执行时间线 | /api/runs/{id}/events | stage ids (`solution`, `product-candidate-provider`), raw statuses (`stage_started/failed`), run ids |
| D 生成的产物 | /api/runs/{id}/artifacts[/{type}] | artifact_type + artifact_id list, JSON drill-down/copy |
| E 证据链 | product-recommendation + knowledge-evidence | provenance refs + evidence content — real, but sits BELOW JSON artifacts |
| F/G | approve/reject + feedback | fine (authoritative, kept as-is) |

Reading order is agent-pipeline order (run → skill → artifact → JSON →
event), not human-decision order. The customer, their need, the gaps and
the recommendation — all present in artifact payloads — are invisible
until the reviewer opens raw JSON.

## 2. Per-artifact human-readable value (verified against real payloads)

| Artifact | Fields usable for humans | Verdict |
|---|---|---|
| client-profile | every field is `{value, status KNOWN/UNKNOWN}`; `missing_from_upstream`, `conflicts` | **PROMOTE** — powers Case Header + 已验证/需确认; degradation honest (UNKNOWN → 建议确认) |
| requirement-analysis | `requirements[].summary/priority/reason` (natural Chinese) | **PROMOTE** — 客户需求 summary card |
| risk-assessment | `risks[]`: name, severity/likelihood/residual, `existing_protection`, `coverage_assessment{protected,unprotected}_amount`, conclusion, reason, evidence refs | **PROMOTE** — risk table rows + expandable rationale |
| coverage-gap-analysis | `gaps[]`: subject, gap_level, current_coverage.status, target_coverage.direction+rationale, reason, related_risk_ids; `priorities`; `information_gaps` | **PROMOTE** — 缺口 column + 建议 column; join to risks via related_risk_ids |
| solution-plan | `solutions[]`: objective, coverage_direction, priority, trade_offs (option_a/b/chosen/reason), rejected_directions (direction+reason), related_gap_ids | **PROMOTE** — 为什么这样设计 + 保障结构 list (no fake bars: no ratio data) |
| product-candidates | candidates: product_name, company, features, `premium.annual`, `term.years`, constraints (deductible), eligibility.checks (PASS/UNKNOWN) | **PROMOTE** — product table. NOTE: this artifact's JSON carries `candidates` at the top level (no `payload` wrapper) — adapter must handle both shapes |
| product-recommendation | decision_context, candidate_evaluations (fit + natural-language reason + provenance), primary_recommendation (reason + product block), not_recommended reasons, uncertainties, human_review_required | **PROMOTE** — 为什么推荐 + 需要确认; null-primary runs degrade honestly ("未形成主推荐" + reasons) |
| knowledge-evidence | evidence_id → content/source/section | **KEEP** — 证据展开/查看来源 (moved into expandable rationale) |
| insurance-report | `structured_report` + `rendered_report` (full markdown, ~18KB) | **PROMOTE** — deliverable card with 打开完整报告 |
| review card | level/validation/flags/customer_summary | **KEEP** — feeds 审核状态 card + Human Review 🔴 items; full card stays as drill-down |
| events | stage_completed order | **DEMOTE** — human verb checklist (已完成需求分析…), raw log behind 查看详细执行记录 |
| run meta / supervisor / approval internals | run_id, restored, status codes, risk_level, approval_id, task_id, graph_revision | **DEMOTE** — Technical Details (collapsed) |

## 3. Keep / demote / hide / reorganize

- **Keep-promote**: all nine artifact payloads above; they already carry
  natural-language `reason` fields for every conclusion (the agent's
  honesty rules produce them) — the UI never writes its own conclusions.
- **Demote to Technical Details**: run_id, restored flag, case_id,
  approval_id/request_type/task_id/graph_revision, supervisor
  status/risk_level, artifact ids/lineage, schema/skill/version fields,
  raw JSON viewer + copy, full event log.
- **Hide (never first-paint)**: raw event types, producer skills,
  artifact_type as a headline, JSON.
- **Reorganize**: reading order becomes 客户 → 需求 → 风险/缺口 → 方案 →
  推荐 → 需人工确认 → 产物 → 过程 → 技术详情.
- **Keep unchanged**: DecisionPanel (F), FeedbackPanel (G), Review Queue,
  Chat UI, Developer Mode, ApprovalDetail record view.

## 4. New information architecture (implemented in Steps 2–4)

1. **Case Header** — customer line (35岁 · 已婚 · 1个孩子 · 北京-style from
   client-profile), case title (/api/cases desc lookup — existing
   endpoint), core need headline, approval status badge, 开始人工审核 →
   scrolls to decision panel.
2. **Executive Summary** — 5 cards: 客户需求 / 当前保障 / 主要缺口 /
   Agent 建议 / 审核状态. One question per card.
3. **Risk & Coverage Gap** — 风险→当前情况→保障缺口→Agent建议 rows
   (risk ⋈ gap via related_risk_ids), each expandable to 结论/理由/测算/
   证据引用 (knowledge-evidence content inlined).
4. **Solution** — 为什么这样设计 (solutions[].reason + rejected_directions
   “考虑过但未采用”) + 保障结构 plain list (no fabricated ratios).
5. **Product Recommendation** — 为什么推荐这个产品 (primary.reason) +
   product table (产品/解决什么问题/年保费/保障期限/特点) + 推荐依据
   (fit/evidence/provenance) + 需要确认 (eligibility UNKNOWN checks).
   Null-primary runs: “本次未形成产品推荐” + not_recommended/uncertainties
   reasons, nothing invented.
6. **Human Review** — 🔴 需要确认 (card HIGH flags, human_review_required,
   failed checks) / 🟡 建议确认 (card MEDIUM flags, uncertainties,
   eligibility UNKNOWN, client UNKNOWN fields, information_gaps) /
   🟢 已验证 (client KNOWN fields grouped). Empty bucket → 无.
7. **Generated Deliverables** — insurance-report as 成果 card with
   打开完整报告 (rendered markdown); other artifacts as status cards;
   raw JSON drill-down retained.
8. **Agent 工作过程** — ✓ human-verb checklist from stage_completed
   order; 查看详细执行记录 expands the full event log.
9. **Technical Details** — collapsed: run/approval/supervisor verbatim,
   artifact registry + lineage, raw payloads, event log.

## 5. DATA GAPs found (backend unchanged, per constraint)

- `DATA GAP: 客户姓名` — client-profile has no name field; header uses
  the demographic line instead (honest).
- `DATA GAP: 产品保障额度(sum insured)` — catalog candidates expose
  premium/term/features/constraints but no coverage-amount field; the
  product table omits the 保障额度 column rather than fabricating.
- `DATA GAP: 健康告知/条款类确认项` — no data source carries
  health-disclosure/clause confirmation items; 需要确认 renders only
  data-driven items (eligibility UNKNOWN, uncertainties, flags).
- `DATA GAP: 保额测算过程` — coverage_assessment gives protected/
  unprotected amounts only; no step-by-step calculation exists, so the
  expandable shows amounts + confidence + reason, not a fake derivation.

## 6. Verification inputs used

run_9de5882e (complete, primary C001 demo-百万医疗险A, premium 400),
run_447ccd4b (5 risks/4 gaps, primary=None, 6 uncertainties,
human_review_required=true), run_dad25ef1 (all 10 candidates
not_recommended), run_84f63c7c (6 of 9 artifacts, rec 404, card
DEEP_REVIEW/FAIL), /api/cases desc strings.
