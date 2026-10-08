# K.32 · FlashX Production Tiering Readiness & Staged Rollout Audit

## 1. Status

**READY_WITH_BLOCKERS**（Step2+ FlashX 核心证据已备[K.31-A 分类 A]；
存在明确生产化前置事项，可进入 implementation 规划，不可直接 rollout）。

## 2. Scope & Timebox

15 分钟硬时限内完成：文档+代码审计 + 1 个契约测试套件复验。
零生产改动（runtime/frontend/`.env`/flag 全部未动）。

## 3. Evidence Reused from K.31-A

D Δmed -21.0s(-19%)·E -20.7s(-48%)·6/6 配对同向；verbosity 真实槽位
0.64-1.13；retry/repair/needs_review 0/20；QA 同签名拒答（n=2·G-1 根因）；
分类 A。**K.32 未重测任何 E2E/QA 项。**

## 4. Current Routing Matrix（以当前代码为准·零 drift）

| 执行类 | 当前模型 [CODE] | FlashX 候选 | K.32 建议 |
|---|---|---|---|
| C1 Step1 决策 | glm-5.3（agent.py:77 `provider`） | 不换（K.30 实测 flash 系反慢） | 保持 |
| C2 Step2+ 续步 | glm-5.3-flash（`fast_provider`） | glm-5.3-flashx | 灰度对象 |
| C3 QA 接地生成 | glm-5.3-flash（server.py:813 **与 C2 共槽**） | （未就绪） | 暂保持 flash |
| C4 QA 重生成 | 同 C3 | 同上 | 暂保持 flash |
| C5 intent 候选 | 关闭（env 未设；开启时走 fast 层） | — | 不变 |

runtime 代码中 flashx 出现次数=0——只能经进程 env 进入 ✓。

## 5. Production Readiness Audit

**5.1 Routing Control**：`LLM_FAST_MODEL` 进程 env > `.env`（K.31-A 双向
实证）；Step1 不受影响 ✓；**但 C2 与 C3/C4 共享同一 fast 槽位——现有
配置无法「步2+=flashx 而 QA=flash」**→ 需代码新增独立 env 缝（STOP-3，
列为 blocker B1）。Percentage routing：**不支持**（仅进程/实例级）。

**5.2 Rollback / Fallback**：模型级 flashx→flash 自动 fallback：
**NOT CURRENTLY AVAILABLE**（gateway/loop 重试均为同模型；与现行 flash
行为一致，非新增风险）。Rollback = 撤 env + 重启（单次重启·K.31-A 实操
验证·分钟级）。run deadline/watchdog 与 fail-closed 拒答兜底现存 ✓。

**5.3 Observability**：`agent.llm_call`（model+run_id+step+duration+
tokens+status）+ run_profiler + `/api/agent/config` 契约缝——Flash/FlashX
**可区分可归因** ✓。REUSE EXISTING OBSERVABILITY（禁止新建·未新建）。

**5.4 Configuration Safety**：env 缺失→回落 `.env`→flash（config.py:88
再回落主模型）——**不存在意外进入 flashx 的路径** ✓；startup-safe ✓；
泄漏面=进程 env（无文件持久化）✓。

**5.5 QA / Citation Gate**：G-1 未修复；gate 代码未变；QA 现行 flash ✓。
**QA FlashX Production Readiness: NOT ESTABLISHED**（n=2+G-1）。因 B1
共槽，Stage 1 若不先实现隔离则 QA 会随灰度切到 flashx（K.31-A 无新回归
但样本小——rollout 设计需明示此取舍）。

**5.6 Provider / Billing**：glm-5.3-flashx 在 provider `/models` 在册
[K.30 实测]·同 endpoint/同 credential/同 OpenAI 兼容协议 ✓。
**Billing verification: NOT VERIFIED FROM REPOSITORY**。

**5.7 Benchmark Comparability**：K.31-A 双臂同日同 effort=high——内部
可比 ✓；K.28 属 effort=low 时代（.env 14:49 变更前）——与后续
**NOT DIRECTLY COMPARABLE**。K.32 未产生新 benchmark 数据。

## 6. Staged Rollout Design（依当前代码能力·operator-controlled canary）

- **Stage 0（现行）**：step2+/QA=flash（生产现状）。
- **Stage 1（金丝雀）**：实施 B1 隔离缝后——pilot 实例
  `LLM_FAST_MODEL=glm-5.3-flashx`（QA 保持 flash 的独立 env），probe-alpha
  合成流量先行 + Owner 真实用户小样本；观测 1-3 天。
- **Stage 2（扩大）**：pilot 常驻实例切换，真实用户全量（仍非 :8000）。
- **Stage 3（全量）**：`.env` 变更（正式 production default 迁移，需
  Owner 授权 + 独立 phase）。
- Percentage routing 不支持——以实例/环境为灰度单位（已如实声明）。

## 7. Rollback Triggers（客观·不评分）

Reliability：agent_step_error>0（K.31-A 基线=0）·schema/tool 失败>0·
terminal run_failed>0。Quality：needs_review>0·citation_gate_rejected
比例超 flash 基线（QA 若在灰度内）。Performance：E2E P50 回退至 flash
基线以上·TTFC>5s。**Product behavior：C 场景早澄清/WAITING_USER 差异
（K.31-A flashx 2/3）——Observed behavior difference 已记录；
Product decision required: YES；Automatic rollback trigger: NOT DEFINED
until product decision。**

## 8. Open Decisions

①C 早澄清行为的产品判断 ②QA 是否随 Stage 1 金丝雀同行（B1 实施前
必然同行）③flashx 计费/限流档位核实 ④Stage 3 的 `.env` 正式迁移时点。

## 9. Blockers

- **B1（工程）**：C2 与 C3/C4 共槽——需新增独立 QA fast-model env 缝
  （productionization implementation，本阶段禁改故未实施）。
- B2（证据）：QA flashx NOT ESTABLISHED（n=2·G-1）——不阻塞 C2 灰度
  （若接受 QA 同行）。
- B3（商务）：billing NOT VERIFIED FROM REPOSITORY。

## 10. Recommendation for Next Phase

K.32-B（productionization implementation proposal）：①B1 独立 QA env 缝
设计（最小 diff）②金丝雅观测清单（复用 agent.llm_call）③rollback 演练
步骤文档化。实施仍需 Owner 授权。

## 11. Verification

- 契约测试复验：`pytest tests/runtime/test_agent_config.py` **11 passed**
  （15s·时限内）。
- 其余复用：K.31-A 前后电池 853+2·routing 缝代码 grep 实证·
  `/api/agent/config` K.31-A 双向核验记录。
- Frontend/tsc：未修改，不跑。

## 12. STOP

**PRODUCTION CHANGE: NONE · STOP（15 分钟时限内完成）。**
