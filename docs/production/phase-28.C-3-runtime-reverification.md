# 28.C-3 Runtime Reverification → Pre-UAT Readiness（自主执行全程）

Date: 2026-10-01 · Mode: **Long-Running Autonomous**（零生产代码
修改·全部 SEALED 零触碰·S2/Batch-2/K.29 未动）·
**Final Verdict: RUNTIME_VERIFIED + READY_FOR_UAT**

## 1. Runtime

```
Before: :8123 DOWN（docker 崩溃沿袭）
After:  UP — PID 39012 · 15:08:53 · health 200（~3s）· HEAD e1aba0e
        （sealed code·C2/claim_support/OBS-1 全载入）
Phase B 依赖验证：auth ✓ · WeKnora 401-alive ✓ · PG :5433 ✓ ·
        GLM 真实探针 'OK' ✓ · :5273 ✓ · :80 ✓ · ollama 容器 ✓
```

## 2. Core Case（真实用户入口·零注入·零指定 Agent）

```
Question: 给孩子配置重疾险前，我应该先考虑什么？
run: run_b4ffd9e983a44708 · 40.1s · completed
Intent:            insurance_qa（rule:qa:重疾险）
Router:            insurance-qa-agent（knowledge-qa slice）
WeKnora hits:      1（allowed=1·governed success）
QualifiedEvidence: 1 —— C2 放行 02_critical_illness（域语料）
LLM generation:    真实 glm · attempts=2（证据进入生成上下文实证）
Claim Support:     门内行为保持（拒答发生在引用门=生成后门）
Citation Gate:     fact_sentence:no_citation×2 → 拒（C-2 预期安全行为）
Final:             QA_REFUSED ·「本次生成的回答未能通过引用校验…」
```

**C-1 判定：PASS**——intent/router/hits/qualified 全达标；生成真实
消费了 WeKnora 证据（attempts=2）。最终回答被引用门诚实拒绝=既有
**G-2/D-04 引用校准债**（glm flash 不逐句引用·P2·Owner 线），非
语料缺口（修复前是 insufficient_evidence·现在是 citation_gate——
失败层已从「没知识」上移到「校准」）。

**C-2 安全检查**：无 unsupported fact 逃逸（零交付即零逃逸）·无
数字/等待期/产品/监管/promise 泄漏·无 citation mismatch（无交付）。

## 3. Regression（Phase D·live API 四问）

| Query | Intent | Hits | Qualified | Final |
|---|---|---:|---:|---|
| D1 什么是重疾险？ | insurance_qa | 1 | →gen | citation_gate_rejected |
| D2 等待期是什么？ | insurance_qa | 1 | →gen | citation_gate_rejected |
| D3 儿童重疾（THE CASE） | insurance_qa | 1 | →gen | citation_rejected（同 C） |
| D4 无关（餐厅） | unknown_insurance_intent | 0 | — | COMPLETED（clarify 路径·正确） |

注：拒答上下文的 evidence_refs 为空是拒答形态（refs 只在 grounded
落）；qualified 实际发生由生成被触发实证。

## 4. Safety（Phase E）

```
Unsupported claims:      0（零交付·拒答文案固定模板）
Citation mismatch:       0（无交付）
Leakage:                 0（拒答文案扫描 ZERO）
Grounding anomalies:     0（C2 8/8·K.26 6/6·Claim Support 65/65·
                          Intent 12/12·B4 7/7=33 项 targeted 全绿）
错误路由:                 0（四问 intent 全正确）
```

## 5. Architecture

```
WeKnora = only Runtime KB:   YES（运行时唯一走 KnowledgeService）
Direct Markdown read:        NO（runtime/ 域路径 grep=0）
Second KB:                   NO（第二向量库 grep=0）
Admin UI:                    YES（:80 200·API 级全证）
```

## 6. Regression（Phase G 全量）

```
Full regression: pytest tests/runtime tests/contract -q
Passed: 865   Failed: 0   Skipped: 2
（零意外失败；早前一次 6 红=pg_cred.txt 被 OS 清理·已恢复复绿=
  environment 类·非回归）
```

## 7. UAT Readiness（Phase F 只读审计）

```
P0 = 0（沿 Pre-UAT Final Gap 封存证据）
P1 = 0
P2 = 沿袭（引用校准 G-2/D-04 现为儿童案例当前主要 P2 项·GLM
     YELLOW·前端断线 UX·PG 告警面）
S2 = OPEN-UNSTARTED（Batch-2 三 key staged 未分发·REGISTRY 确认）
Batch-2 = 未分发（distribute/{03,04,05}.key 就绪在案）
K.29 = DESIGN（READY_FOR_IMPLEMENTATION·未实现·未开启）
```

## 8. Final Verdict

**RUNTIME_VERIFIED + READY_FOR_UAT**——28.C-3 的知识恢复已在真实
运行时端到端实证：儿童重疾案例从「0-hit 语料空缺拒答」恢复为
「qualified evidence→真实生成→引用门」；当前唯一剩余主 P2=引用
校准（Owner 线·D-04）；其余沿 Pre-UAT 结论不变。

## 9. Boundaries（确认）

未启动 S2·未分发 Batch-2·未进入 K.29-B·未开启 Hybrid/LLM Intent/
Claim Judge·零生产代码修改（:8123 重启+验证 only）。

证据：`tmp/obs/c3reverify_{case,regd}.json` · live run
`run_b4ffd9e983a44708`（qa-answer-context 在 tmp/webui-runs）。
