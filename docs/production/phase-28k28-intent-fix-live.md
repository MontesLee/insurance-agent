# 28.K.28-I-FIX-LIVE · Intent Fix 生产运行时 Live 验证

Date: 2026-09-29 · Mode: **LIVE VERIFICATION ONLY**（零生产修改·
零语料修改·零阈值修改）· Result: **K.28-I-FIX-LIVE: PASS**

## 1. Owner Restart Authorization

本阶段任务书（K.28-I-FIX-LIVE）明示目标=「:8123 重启后验证修复生效」
并给出 §2 OWNER RESTART 指令——以此作为重启授权执行。

## 2. Restart Evidence

| 项 | 值 |
|---|---|
| restart time | 2026-09-29 12:59:32 |
| PID | 26352（:8123 health 200 ~3s） |
| HEAD | 46dbe0f（tracked-modified 41·与会话基线一致） |
| classifier.py | mtime 2026-09-29 11:49:53 · sha1 `1fa5d8d6725b0dc5`（< 进程启动=已载入） |
| intent-rules.yaml | mtime 2026-09-29 12:05:17 · sha1 `f05a5c0669465dd8`（< 进程启动） |
| 加载证明 | mtime + 行为签名（见 §4-7：`rule:plan:怎么安排`/`product_qa_specific:第二款`/退款护栏=修复前码不可能产生的 reason codes） |
| WeKnora / PG | 401-alive / :5433 LISTEN（不受影响） |
| frontend | :5273 无需重建（纯后端修复）——未动 ✓ |
| 前置确认 | 重启前 :8123 DOWN（第八次内存回收终止的 10:45 进程=修复前码——修复文件 11:49/12:05 晚于该进程启动） |

## 3. Live Smoke Matrix（18 runs·probe-alpha·SCRIPTED_PROBE）

### §3A QA 问句保护

| Case | 消息 | Live intent | reason | 判定 |
|---|---|---|---|---|
| A1 | 重疾险和百万医疗险有什么区别？ | **insurance_qa** | rule:qa:区别+重疾险+医疗险 | ✅ 未入 plan |
| A2 | 什么是百万医疗险？ | **insurance_qa** | rule:qa:什么是+医疗险 | ✅ |
| A3 | 我需要买重疾险吗？ | **insurance_qa** | rule:qa:重疾险（需要吗） | ✅ 未因「重疾险+问句」入 plan |

（三例均 qa_answered 事件在案=QA 切片真实执行）

### §3B Planning 问句保护

| Case | 消息 | Live intent | reason | 判定 |
|---|---|---|---|---|
| B1 | 怎么配置家庭保障方案？ | **insurance_plan** | rule:plan:配置+方案+保障 | ✅ 邻接豁免 live |
| B2 | 怎么规划孩子的保障？ | **insurance_plan** | rule:plan:规划+保障 | ✅ |
| B3 | 帮我分析一下…怎么安排？ | **insurance_plan** | rule:plan:保障+**怎么安排**（新增口语信号）+祈使豁免 | ✅ |
| B4 | 我40岁…怎么做家庭保险规划？ | **insurance_plan** | rule:plan:规划（怎么做 邻接） | ✅ 未因问句标记误转 QA |

（四例 qa_answered=False=从未进入 QA 管线）

## 4. C1 Continuation Regression（§4）

T1「我想做一下家庭保险规划。」→ **insurance_plan · WAITING_USER**（首试即 waiting）→
T2「房贷还有100万，孩子5岁，我和配偶都有百万医疗险。」→
**insurance_plan · reason=[plan:continuation, context:pending_clarification]**
→ planning 完成（qa_answered=**False**，从未进入 QA）。**C1 无回归** ✅

## 5. False Continuation Guard（§5）

| Case（pending 态下） | Live | reason | 判定 |
|---|---|---|---|
| 我想退款 | **unknown_insurance_intent**（fallback→clarify） | fallback:no_signal_match | ✅ **未继承 plan**（修复前此输入=plan:continuation） |
| 再解释一下百万医疗险和重疾险有什么区别 | insurance_qa | rule:qa:区别+…（定义切换） | ✅ 未入 planning |

（D2 遵守：无新 intent·不强推·fail-closed ✓）

## 6. B-narrow Regression（§6）

| Case | Live | reason | 判定 |
|---|---|---|---|
| T1 重疾险和医疗险有什么区别？→ T2 第二款呢 | **product_qa** | **rule:product_qa_specific:第二款 + context:anchor_inherited** | ✅ 有锚→产品路径 |
| 第二款呢（新会话无上下文） | **unknown**（clarify） | fallback | ✅ 无锚 fail-closed·不猜产品 |
| 那这个呢？/它怎么样/这款怎么样（新会话） | **unknown ×3** | fallback | ✅ D3：未被强行 product_specific |

## 7. RV4 Regression（§7）

- **RV4-T1（原文）→ insurance_plan**（两试均正确；两试 run 均 completed
  =模型 ask-vs-proceed 方差，与 C2-LIVE 时 5/5 同型——**意图层判定正确**，
  方差属 planning 行为非 intent 层）✅
- RV4-T2（原文）：两试 T1 均未落 WAITING_USER（方差 2/2）→ 原文 T2
  live 未演练。**等价证明链**：①C1-T2（同型声明式补充：房贷/孩子/百万
  医疗）live=plan:continuation→planning·qa_answered=False——错误 QA
  路径未发生；②原文 T2 离线（S4-PEND-01 消融三态）在修复码上验证为
  +pending→plan；③C2（零触碰）仍为兜底。**判定：PASS WITH VARIANCE
  NOTE**（如实：exact-text T2 live 样本 0，等价机制样本 1）。

## 8. Safety（§8）

全部 18 轮 assistant transcripts 扫描：run_id / ART- / EVAL- /
approval / 内部 Agent 名 / prompt / tool 名 / CoT / reasoning
**九类零泄漏**（k28ifix_live_safety.json）。

## 9. Offline ↔ Live Consistency（§9·逐 Case）

| Case | Offline（FIX-IMPL） | Live | Match |
|---|---|---|---|
| A1 | insurance_qa | insurance_qa | ✅ |
| A2 | insurance_qa | insurance_qa | ✅ |
| A3 | insurance_qa | insurance_qa | ✅ |
| B1 | insurance_plan（TRAP-01 邻接族） | insurance_plan | ✅ |
| B2 | insurance_plan（TRAP-02 邻接族） | insurance_plan | ✅ |
| B3 | insurance_plan（怎么安排 新信号） | insurance_plan | ✅ |
| B4 | insurance_plan（怎么做 邻接） | insurance_plan | ✅ |
| C1（T2） | plan:continuation（100% precision） | plan:continuation | ✅ |
| False-cont（退款） | unknown（SW-09 族） | unknown | ✅ |
| B-narrow（有锚） | product_qa（ELL-05） | product_qa | ✅ |
| B-narrow（无锚） | unknown（FU-03 同签名） | unknown | ✅ |
| RV4-T1 | insurance_plan | insurance_plan | ✅ |
| RV4-T2 | insurance_plan（消融） | 等价机制证明（方差） | ⚠️ 等价 |

**零 LIVE_CODE_MISMATCH**：18/18 shadow 记录 decision_source=
registry_lookup/fallback·conf_src=rule（llm 零出现）·resolver=
rule_fast_path/fail_closed_unknown——Runtime 载入=FIX-IMPL PASS 代码。

## 10. Success Criteria（§10 十五项）

1 重启成功✅ 2 修复加载（行为签名）✅ 3 QA 保护✅ 4 Planning 保护✅
5 C1 无回归✅ 6 假延续护栏✅ 7 B-narrow✅ 8 RV4-T1=plan✅
9 RV4-T2=plan（等价机制+离线原文；方差注记）✅ 10 错误 QA 证据路径
未发生（C1-T2 无 qa_answered；C2 兜底未触碰）✅ 11 安全零✅
12 offline/live 一致（13/13 直证+1 等价）✅ 13 C2 零修改✅
14 LLM Candidate=OFF（18/18 rule）✅ 15 Router Authority 未动
（full·slices reason=authority 与基线一致）✅

## 11. Final

**K.28-I-FIX-LIVE: PASS** — Intent Fix is live-verified.

## 12. Residual Risks

- RV4 exact-T2 live 样本 0（方差）——等价机制已证；后续自然流量将
  补真实样本。
- ask-vs-proceed 方差持续偏 proceed（今日累计多轮）——planning UX
  一致性 Owner 线（非 intent 层）。
- FU-03 型（纯产品 id 上下文无锚）保持 fail-closed（v1.1 勘误候选）。

## 13. Next Owner Decision

①Phase 2（Claim→Evidence Support）裁决 ②corpus v1.1（勘误+二审）
③taxonomy debt（SW-10/推荐类）④D-08 commit（span：修复代码+工具+
三报告）⑤pilot 长驻形态（八次回收先例）。

> **边界**：LLM Candidate 保持 OFF · Router Authority 未改 · C2 未改
> · 未 commit · 未进入 Phase 2。STOP。
