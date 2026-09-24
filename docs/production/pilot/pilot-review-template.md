# Pilot Review Template (human — one per case)

Reviewer: ____________  Date: ______  Time spent (min, else UNKNOWN): ____

Per-section verdicts (OK / CONCERN / FAIL + one line each):
1. Requirement — 客户真正想解决的问题是否被正确识别?
2. Risk — 主要家庭风险是否遗漏?
3. Gap — 保障缺口是否与风险对应?
4. Solution — 解决方案是否合理?
5. Product — 产品是否真的符合方案?
6. Evidence — 推荐结论是否有可靠 evidence?
7. Report — 客户是否能看懂?

Final: APPROVE / REJECT / NEEDS_CHANGE
(NEEDS_CHANGE ≠ system MODIFY — that capability is P2-open
PA-26C5-P2-01; record what you would have changed.)

Structured fields:
reviewer_changes: <free text or NONE>
rejection_reason: <if REJECT>
missing_information: <what the agent should have asked for>
incorrect_reasoning: <where>
evidence_problem: <where>
product_problem: <where>
report_problem: <where>

Note: mechanical approvals recorded by the runner (actor
`pilot-operator`) only carried the pipeline past its gates; your
review is the first BUSINESS judgment of these artifacts.
