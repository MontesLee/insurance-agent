# Phase 28.K.7 — P1 Remediation Implementation 报告

Date: 2026-09-26 深夜~2026-09-27 · 授权：D-K6-1（S-1 方案 B）·D-K6-2
（S-2 杠杆②）·D-K6-3（G-2 网关级）。禁令全遵守（零新 Agent/Skill/
Router 重写/门放宽/UI/Auth/Persistence/语义变更；未 commit；未分发
key；pilot 孤儿进程未触碰）。

## 1-2. S-1 Root Cause & Implementation

根因（K.6 已闭环）：闭包治理=切片层；unknown→通用环 finish 无闭包。

实施（方案 B，三处最小改动，全部复用既有机制）：

```text
runtime/intent/classifier.py  步骤7 fail-closed unknown 追加
  reason "domain:insurance_anchor"（复用既有 insurance_anchors 标记；
  仅当前消息，context 继承排除——mid-conversation 天气不受治理路由）
runtime/server.py  切片缝：unknown+marker → _qa_slice=True（同一
  knowledge-qa 管线）；slice_decision 仅对受治理 unknown 记录
  （非保险 unknown 无切片考量，M3 契约保持）
runtime/qa_agent/agent.py  输入契约接受受治理 unknown（其内禀
  clarify=True 允许——"不确定"信号本身；insurance_qa 严格契约不变）
```

## 3. S-1 Regression（新 16 项中 8 项 + live）

```text
A1 无据：unit（量子保险…→refused insufficient_evidence）✓ live
   （"保险精算的微观市场均衡…"→切片→8s 诚实拒答）✓
A2 有据：unit（grounded+citations）✓；live（"偿付能力"→切片→
   retrieval allowed=4→治理接管 ✓；生成层 glm 今夜不可用→诚实有界
   失败（=C2 契约；grounded 交付=unit+28.K 历史实证）
A3 诱导：unit（未引用建议→citation_gate_rejected 有界再生成→拒，
   建议零交付）✓
A4 非保险：unit（天气→invalid_input 直调/不进切片）✓ live（天气→
   qa_slice=False 原路径）✓
集成：anchor-unknown→qa_answered(slice=knowledge-qa) ✓；天气→无
   qa_answered ✓
```

## 4-5. S-2 Root Cause & Implementation

根因（K.6+本轮铁证）：SOLUTION_VALIDATION 查询=纯模板串；多产品
方案（solution_type=None→general 域）+ purpose 后缀「适用性 策略验证」
→ 治理语料确定性 0 命中（S08 实存 artifact query 佐证：带后缀 0 /
去后缀 2）。

实施（杠杆②，配置级最小校准）：

```text
knowledge/evidence/resources/config/evidence-request.rules.json
  purpose_query_suffix.SOLUTION_VALIDATION: "适用性 策略验证" → ""
  （+ k7_calibration 出处注记）。确定性/防注入不变（仍纯模板生成）。
校准后 live 实测（真实 request_evidence 路径）：
  general(多产品)=2 · medical=1 · critical_illness=1 · life=1 ·
  accident=0 · savings=0（后两者=语料真缺口→fail-closed 保持正确，
  语料扩充=Owner 决策，未动）
```

## 6. S-2 Regression

```text
新：模板确定性断言（各域精确串+POLICY_FACT 不变+同输入同输出）✓
   规则完整性（模板静态非空/无自由文本）✓
既有覆盖（电池全绿）：agent_loop §20/§44（EVAL fail→needs_review
   无假成功）· dynamic_replanning（repair 预算）· K.1（needs_review
   终态文案）· G/E-4（产物所有权与交付）· B6 基线 tripwire（v2）
LIVE DoD（隔离短命实例 :8124，已按规清理）：
  全信息家庭规划 2 轮 → COMPLETED → 9 artifacts 全 VALID
  （client-profile→…→solution→knowledge-evidence→**product-candidates
  PASS**→recommendation→**insurance-report**）→ 不透明 ref
  ar_cc8a… → 消费者下载 36,778B ✓✓
  （turn-2 首试文本误中 QA 规则=已知路由词行为，换 plan 语境文本
   后全链通过——如实记录）
```

## 7-8. G-2 Root Cause & Implementation

根因（本轮受控二分实证）：provider 429 以裸 RuntimeError 上抛；网关
`_do_generate` 末端的 except-Exception 全量规范化器本可将其规范为
LLMError；但 (a) 429 未被识别为可重试 RateLimitError（无退避重试）、
(b) 首版修复把 except RuntimeError 插在规范化器之前反而截断链路
（except 链互斥——受控二分定位后纠正）。

实施（网关级，两处）：

```text
runtime/llm/gateway.py
  ① 末端规范化器内：" 429" 识别 → RateLimitError(retryable)——
     其余错误维持既有规范化（llm_unavailable 契约不变）
  ② 重试环：RateLimitError 专用有界指数退避（_RETRY_BACKOFF_S=
     (1.5, 4.0)s，_sleep 间接层供测试观测/置零）；timeout 类即时
     重试不变（总量预算契约 timeout*(1+retries) 保持）
```

## 9. G-2 Regression（5 项）

```text
正常请求零退避 ✓ 瞬态 429→恢复（含 1 次退避且时长=首档）✓
持续 429→RateLimitError（恰 1+max_retries 次·无失控重试·退避=2 次）✓
不可重试→立即失败（1 次·零退避）✓ 退避有界递增 ✓
（live 无法注入受控 429——单测证明；:8124 夜间真实 llm_unavailable
的诚实有界行为与 C2 契约一致）
```

## 10. Full Regression

```text
backend **787 passed + 2 skipped（零失败）**（=K.6 771 + K.7 16；
含 B4 7/7·B6 10/10·M4 9/9·M3 7/7·E-6 5/5·B-02 15/15·GOV 11/11·
HD-2·grounding/calibration 全量）
web **221 passed + 2 skipped** · tsc **clean**
首跑 4 失败全部闭环：B4（网关规范化器位置 bug——受控二分定位修复）
·b51（退避收窄为 RateLimit 专用·预算契约保持）·M3（slice_decision
仅受治理 unknown 记录）·B6（规划基线按三段纪律重采集 v2，出处注记
在案：4 case 的 knowledge-evidence 哈希因校准合法变更；prompts
冻结 sha 未动）
```

## 11. Safety Result

```text
hallucinated insurance facts=0（live 交付全为治理/诚实拒答）·
grounding bypass=0（knowledge-qa 闭包门行为=校准套件+live）·
cross-user exposure=0（B-02 15/15）·internal leakage=0（consumerDom
+K.1 套件）·wrong routing=0（B4/M4/新增 S-1 路由断言）
```

## 12. Remaining Risks

```text
①pilot 孤儿 :8123/:5273 仍运行 K.7 前旧码——K.7 修复未在 pilot 生效
  （重启=Owner 授权项）
②glm 今晚可用性不稳（:8124 多轮 llm_unavailable；provider 侧；G-2
  已按契约有界处理）——Batch-1 前建议核实配额
③accident/savings 域语料缺口（fail-closed 正确；扩充=Owner）
④A2 的 live grounded 交付待 provider 可用窗口复验（unit 已证）
⑤知识 QA 口语长问法检索敏感（G-1 族）未动（授权范围外）
```

## 13. Batch-1 Readiness

```text
技术门：S-1 ✓（治理闭环 live）·S-2 ✓（核心规划链 live 打通+报告
交付）·G-2 ✓（有界退避+诚实失败）——K.6 的两 P1 与 G-2 已清。
剩余前置：①Owner 授权 pilot 干净重启载入 K.7 代码 ②glm 配额核实
③（建议）重跑 K.5 场景子集于新码作对照。满足后 Batch-1 GO。
```

## 14. Exact Files Changed（8）

```text
M runtime/intent/classifier.py（unknown 域标记）
M runtime/server.py（受治理 unknown→knowledge-qa 切片缝+记录门控）
M runtime/qa_agent/agent.py（输入契约扩展）
M runtime/llm/gateway.py（429 规范化+RateLimit 退避）
M knowledge/evidence/resources/config/evidence-request.rules.json
  （SOLUTION_VALIDATION 后缀置空+校准注记）
M tests/golden/planning-baseline.json（v2 重采集·出处注记）
A tests/runtime/test_k7_remediation.py（16）
M .agent/ 簿记（本报告另计）
```

## 15. Exact Commands/Tests

```text
python -m pytest tests/runtime/test_k7_remediation.py -q（16/16）
python -m pytest tests/runtime tests/contract -q（787+2 零失败）
web: npm test（221+2）· npm run typecheck（clean）
live 诊断/校准/DoD：tmp/ 临时探针（request_evidence 逐域矩阵·
:8124 短命实例 S-1×3+规划全链·事后 taskkill 清理）
基线重采集：tests/golden/planning-baseline.json v2（pinned strftime）
```

```text
Code Changes: 8（6 修改+1 golden+1 新测试）
Commit: NONE
REAL_USER: 0
Batch-1: NOT DISTRIBUTED
STOP — WAITING FOR OWNER REVIEW
```
