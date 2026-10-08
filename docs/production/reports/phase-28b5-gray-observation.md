# Phase 28.B5 — M2 Product QA 灰度启用 + 回滚演练观察报告

Date: 2026-09-25 · 性质：**运营观察**（零代码改动——git 复核仅新增
docs；灰度=独立服务器进程 flag 控制，Router Authority 保持 OFF，
ADR-025 未触碰）。

## 0. 环境与样本声明（如实）

- 灰度实例：127.0.0.1:8106 独立进程（demo 模式 loopback 免钥）；
  未触碰既有 :8000 用户进程。
- 组成：**live glm-5.3**（fast tier glm-5.3-flash；密钥未打印）+
  **mock 治理知识组合**（进程环境无 weknora 变量——治理/引用全量，
  但语料为 fixtures 测试库）。此为环境真实组成，不冒充生产 WeKnora。
- **INSUFFICIENT LIVE SAMPLE（显式）**：本报告全部样本为**脚本注入
  的 smoke/drill 流量**，无真实用户流量；灰度窗口约 40 分钟（flag=1
  ~03:04Z–03:16Z，flag=0 ~03:19Z–03:31Z）。以下结论均为小样本观察，
  不作统计推断。

## 1. Gray Enable（Step 1）

`INSURANCE_AGENT_PRODUCT_QA_SLICE=1` + 独立实例启动（03:04Z，
health OK，provider=glm 配置确认）。**非 Router Authority**：仅
intent=product_qa 进入 product_qa_agent；其余意图原路径（§2 验证）。

## 2. Smoke Test（Step 2，flag=ON，8/8 完成）

| 场景 | run_id | 结果 | 切片 | grounding / failure | 墙钟 |
|---|---|---|---|---|---|
| A 产品问题（泛指） | run_1ea95c56 | QA_ANSWERED | product-qa fired | grounded | 0.6s |
| B 具体产品（P001） | run_fb368f72 | QA_REFUSED | product-qa fired | **citation_gate_rejected**（attempts=2，viol=fact_sentence:no_citation:2） | 57.0s |
| C 缺失产品 | run_73025068 | QA_REFUSED | product-qa fired | insufficient_evidence | 0.5s |
| D 上下文指代（→P005） | run_5f99ab83 | QA_ANSWERED | product-qa fired | grounded（product_ref=context 解析） | 51.4s |
| E 禁止推荐试探 | run_c370cdfd | QA_REFUSED | product-qa fired | **llm_unavailable**（provider 超时） | 174.6s |
| F 知识问答 | run_955912d5 | QA_REFUSED | **knowledge-qa** fired | citation_gate_rejected | 31.3s |
| G 规划 | run_5816bb33 | WAITING_USER | 无（legacy；slice_decision=None） | — | 14.7s |
| H 未知域 | run_e83d433e | COMPLETED | 无（legacy） | — | 7.6s |

**隔离验证 ✓**：product_qa×5 全部进 product-qa 切片；insurance_qa 进
knowledge-qa 切片（不受 product flag 影响）；planning/unknown 走
legacy（actual_execution=existing-agent）。

## 3. Telemetry 审计（Step 3）

- **slice_decision 语义**：fired×6（product-qa×5 + knowledge-qa×1，
  全部正确）；plan/unknown = None（无切片域，如实）。`flag_off` 见 §4
  回滚侧；`clarification_required`/`not_registry_lookup`/`slice_error`
  **无 live 样本**（INSUFFICIENT LIVE SAMPLE——语义由 CI 测试常驻保证：
  test_gray_* 三测 + B4 golden）。
- **actual_execution** 三态如实（insurance-qa-agent / existing-agent）。
- **意图分类延迟**（shadow latency_ms）：0–16ms（规则快路径）。
- **隐私核验 ✓**：qa_answered data 键 = grounding_status/failure_
  reason/evidence_refs/retrieval/generation/slice/**answer_len**——
  无答案全文；intent_classified data 无消息内容（message 字段仅
  "shadow intent=... conf=..." 摘要）；shadow 记录 = sha1+长度+24 字头
  （既有设计）。
- **run_dir AnswerContext**：切片轮均落盘（如 run_fb368f72：refused/
  citation_gate_rejected，attempts=2，gate_violations 机器可读，
  product_ref=P001 resolved）。

## 4. Rollback Drill（Step 4，核心）

**流程**：flag=1 侧产品组（A–E，§2 记录 run_id/意图/切片/结果/事件/
AnswerContext）→ `INSURANCE_AGENT_PRODUCT_QA_SLICE=0` + **重启** →
**同一组消息重放** → 验证。

| 场景（重放） | run_id | 结果 | qa_answered | slice_decision | actual |
|---|---|---|---|---|---|
| A | run_b44bd11d | WAITING_USER | **无** | product-qa/**flag_off** | existing-agent |
| B | run_98eafabf | COMPLETED | 无 | flag_off | existing-agent |
| C | run_71ccd7e4 | COMPLETED | 无 | flag_off | existing-agent |
| D | run_1ae6710e | COMPLETED | 无 | flag_off | existing-agent |
| E | run_8448019d | COMPLETED | 无 | flag_off | existing-agent |

- **product_qa 不再进入切片 ✓**（5/5：无 qa_answered 事件、无
  AnswerContext、reason=flag_off）；**legacy 路径正常 ✓**（全部成轮
  交付答案/追问；行为差异如实记录：A 场景 legacy 以追问回应——
  自由行为 vs 切片的 grounded/拒答，属预期语义差）。
- **回滚后隔离无损 ✓**：F knowledge_qa **仍正常触发 knowledge-qa
  切片**（run_4319828b，QA flag 未受回滚影响）；G planning legacy
  WAITING_USER（run_97b389e1）；H unknown legacy COMPLETED
  （run_a26bdaf7）——三意图均无异常。
- 回滚单位确认：**env+重启**，无数据迁移；ON 期间产生的
  AnswerContext/事件/审计记录保留（增量，不撤回已交付内容）。

## 5. Regression（Step 5）

- **backend：before 688 passed → after 688 passed / 0 failed（351s）**
  （零代码改动，零回归）
- **web：148 passed + 2 skipped（18 文件）· tsc clean**（无 web 改动）

## 6. Observed Failures（不隐藏；小样本，待更多数据）

1. **live 模型引用合规率低**：进入生成的 4 个 QA 轮中 2 个
   （B/F）两次尝试均未过引用闭环门 → citation_gate_rejected
   （viol 形态：事实句漏标 [E#]）。**门工作正常（fail-closed，
   未交付任何无据答案）**，但拒答率→用户体验受损；归因方向：
   生成提示词与 glm-5.3 的引用格式契合度（候选修复：示例 few-shot、
   格式强化——后续授权项，非本阶段）。
2. **E 场景 provider 超时**（174.6s → llm_unavailable）：glm 长
   提示下偶发超时/不稳；网关超时预算 30s+重试。候选：超时/重试
   参数校准（config/qa-grounding-rules.yaml generation 段，外置）。
3. **非缺陷观察**：回滚侧 A 场景 legacy 追问 vs 切片侧 grounded
   直答——两路径语义差为设计使然（E2 契约等价，非文本等价）。

## 7. Latency（小样本）

- 切片轮端到端：0.5s（快速拒答）～174.6s（provider 超时最坏）；
  正常生成 31–67s（live 模型主导；分类仅 0–16ms）。
- 回滚（legacy）轮：7.6–72.5s（同为 live 模型主导）。
- 结论：延迟瓶颈=生成模型而非路由/切片机制；生产化需流式输出
  （既有 SSE 能力）与超时校准。

## 8. Grounding Status 分布（切片轮，flag=ON）

grounded 2（A/D）· refused 4（insufficient 1、citation_gate 2、
llm_unavailable 1）——**零无据交付**；一切拒答均有机器可读
failure_reason + 模板文案。

## 9. Fallback Behavior

- 切片异常 → legacy 回退 + slice_error 标注：本窗口无 live 触发
  （INSUFFICIENT LIVE SAMPLE；CI 常驻验证）。
- 意图层 fail-closed：C（解析失败→insufficient）、H（超域→legacy
  寒暄）均按设计降级。
- 回滚本身即最大 fallback 演练：✓ 通过（§4）。

## 10. 结论与建议

M2 灰度机制（flag/遥测/回滚/隔离）**全部按设计工作**；发现的两个
真实问题都在**模型契合层**（引用合规、provider 超时），非架构层。
建议下一步（需授权）：① 引用格式提示词强化 + 超时校准（小改，
外置规则文件+prompt）→ 复测合规率；② 保持 flag=1 继续积累样本
（含真实用户流量后重写本报告的 INSUFFICIENT LIVE SAMPLE 段）；
③ ADR-025 裁决与 M3 前置不受本报告阻塞。

**STOP — 灰度+观察+回滚演练完成；Router Authority 保持 OFF；等待
下一步授权。**
