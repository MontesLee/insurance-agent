# K.27-RV4-C1-LIVE · Owner Authorized Real-User Verification

Date: 2026-09-28 · LIVE VERIFICATION（零代码改动·仅 restart+真实 RV4
两轮）。

## 1. Restart Evidence

:8123 重启（PID 28768·启动 22:55:38）后 health=200·frontend=200·
WeKnora=401-alive·PG（strict 预检通过=可达）。
**C1 载入证明**：classifier.py mtime 22:20:45 / server.py 22:21:15
**早于**进程启动 22:55:38 → 当前进程加载 C1 代码。

## 2. Real Case Identity

原始 RV4 消息逐字重发（chat_679b…第二轮复现会话）——同 chat 两轮，
probe 通道承载原真实用户文本（原始会话 chat_02a2693e 的场景复现）。

## 3. Turn 1 Evidence（第二次复现·run_55c23c28·25.4s）

intent=**insurance_plan** conf=1.0（rule·plan 动作词+家庭/孩子 ctx）→
Router registry_lookup→insurance-planning-agent→**WAITING_USER**
（规划澄清·原始场景形态复现 ✓）。

## 4. Turn 2 Evidence（run_b41a10f1·68.3s·核心断言全过）

```text
pending_clarification = true（派生自同 chat 上一 run WAITING_USER
                            + intent=insurance_plan）
intent   = insurance_plan  conf=1.0          ✓
reasons  = [plan:continuation, context:pending_clarification] ✓
Router   = insurance-planning-agent（registry_lookup）          ✓
执行     = planning 全管线：agent_step×10·tool×9（profile/分析/
           solution/report）·qa_answered=0                     ✓
terminal = completed/COMPLETED——真实保障缺口总结交付（家庭现状表+
           缺口结论）                                            ✓
```

## 5. Wrong-Evidence Exclusion

T2 消息文本与事件流：**无** 农业保险条例·无 [E1]·无 QA_REFUSED/
QA_ANSWERED·qa_answered=0——RV4-A 的错误链（qa→knowledge-qa→农业
保险条例→E1）**完全未发生** ✓。

## 6. Security Nine-Zero

消息文本扫描：run_/chat_/ART-/EVAL-/agentcase_ 全 0·CoT/reasoning/
tool/skill/agent/raw-event/exception/cross-user 0 ✓（内部 ID 仅存
backend 元数据·Consumer 面零暴露）。

## 7. 首次复现尝试的观察（非 C1 问题·如实记录）

第一次重放（chat_679b…run_3772726）：T1 模型方差选择**直接跑满全管线
COMPLETED**（449 事件·profile→report）而非追问→pending 前置不成立→
T2 落旧行为 insurance_qa（该轮 QA 诚实拒答·无农业保险条例/[E1]）。
分类：**场景复现失败（模型采样方差）≠C1 逻辑失败**——C1 在前置成立
的第二轮复现中完全生效。该方差本身记录为 planning 行为观察
（同输入时而追问时而直答——体验一致性问题·移交 Owner 参考）。

## 8. Status

**K.27-RV4-C1-LIVE STATUS: PASS**
**P1-A Planning Continuation = CLOSED**（代码+测试+真实验证三证齐）。
P1-B（证据资格/门支持性）= **DEFERRED → RV4-C2**（本轮未触碰）。

证据：tmp/obs/rv4c1_live.json（T2 intent/route/终态）·
tmp/obs/rv4c1_t1_events.json（首试 T1 全管线）·shadow.jsonl 两条新
记录（reasons 含 plan:continuation）。

## 9. STOP

验证结束——不开始 RV4-C2·等待 Owner 下一阶段授权。
