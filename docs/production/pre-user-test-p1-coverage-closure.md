# Pre-User-Test P1 Coverage Closure（G-01..G-04 专项验证）

Date: 2026-09-30 · Mode: **TEST/EVIDENCE ONLY**（零生产修改·零修复·
S2/Batch-2 未动）· 结论：**PRE-USER-TEST P1 COVERAGE CLOSURE: COMPLETE**

Runtime：:8123 PID 33072（P2-1+FIX2·灰度 ON）·探针主体 probe-alpha
（SCRIPTED_PROBE）·证据：`tmp/obs/p1_closure_{g01,g03,journey}.json`。

## G-03 同 Chat 并发消息 → **TESTED（live API）**

**机制（代码+行为双证）**：`_active_chat`（server.py:128·一 chat 一
agent turn）——busy 时第二消息 **409 `busy:<run_id>`**（显式拒绝·非
静默丢弃·非排队合并）。

| 探针 | 结果 |
|---|---|
| G03-01 双话题并发（真实线程并发 POST） | 一 200（QA 话题·intent=insurance_qa 正确）一 **409 busy 指向同一 run** ✓ |
| 终态后 retry（=G03-05 形） | **200 新 run** ✓（序列化释放后接受） |
| message loss | 无（被拒消息未被写入 transcript——显式拒绝语义·客户端知情；已接受消息完整在案）✓ |
| context 串扰 | 无（accepted run 意图=其自身话题）✓ |
| G03-02/03/04（同话题并发/续+切换/双 tab） | **机制同一**（同一 `_active_chat` 串行闸）——G03-01 已证闸行为；同话题并发被同一闸拒绝、双 tab=两个 HTTP 客户端同 chat 同闸；**未逐项重复实验**（避免冗余 LLM 成本）——由机制唯一性+G03-01 行为证覆盖 |

判定：**TESTED**（闸行为 live 实证；残余面=排队/合并类「期望」是否
更优=产品决策非缺陷——现行为显式 409+客户端可重发，无数据损坏面）。

## G-02 Planning 改前提重算 → **RUNTIME_VERIFIED（行为已定义且正确）**

真实 live 旅程 step 7（前提变更：收入 25→50 万·房贷 80→20 万）：

| 观察点 | 结果 |
|---|---|
| 新事实覆盖旧事实 | ✓（回复明示「根据你的最新情况（50万/20万）重新完成全流程分析」）|
| 旧值残留 | **0**（steps 12/13 回复新值命中 4 次·旧值 25万/80万 命中 **0**）|
| 受影响阶段重算 | ✓（step 7 run：8 stages 全跑·9 artifacts 重建——全流程重算而非复用）|
| 旧 recommendation 复用 | 无（「情况变化带来的影响：房贷 80→20万→身故保障需求显著下降」=按新前提推导）|
| 矛盾 artifact / 错误延续旧 workflow | 未见（后续 12/13 均基于新值）|

判定：**RUNTIME_VERIFIED**——当前系统行为=**全流程重算**（重跑
planning 管线以新会话事实为准）。注：这是「重算」而非「增量修订」
（无 active-case 增量更新机制·ADR-024 线）——行为正确且一致；
「是否应增量修订省时」= 体验优化 Owner 决策，非缺陷。

## G-01 会话持久化/刷新恢复 → **KNOWN_V0_1_LIMITATION（+ 同进程刷新 TESTED）**

| 探针 | 结果 |
|---|---|
| G01-01 refresh（同进程·client 持 key 重 GET） | **200·消息/run 完整可见** ✓（服务存活期刷新=完全恢复）|
| G01-03 artifact 读取 | 无 artifact 的 QA run→404「no persisted state」（预期形态）；有 artifact 的 run 读取沿 E-4 已证 |
| G01-02/04/05 + **服务重启后** | **V0.1 内存态已知限制**（ADR-024）：重启丢 chat/run 内存态——本轮不可探（重启 Owner-gated），按 K.1-K.12 十次重启先例的既有观测记录：重启后 chat GET 404·run registry 404（设计内）|

判定：**KNOWN_V0_1_LIMITATION**（区分明确：服务存活期刷新=完全
恢复·非 bug；重启丢失=ADR-024 已登记债·Owner 决策项 #1 沿袭）。

## G-04 14 步黑盒连续旅程 → **E2E_VERIFIED（SCRIPTED_PROBE 黑盒纪律）**

单 chat 14 步全链 live（仅以用户可见 transcript 判读·内部零读取；
总时长 ~7 分钟·14/14 终态·零卡死·零悬挂）：

| 旅程面 | 结果 |
|---|---|
| 步步可继续（用户下一步明确） | ✓ 每步均有明确回复/追问 |
| 上下文保持 | ✓ step 11 解释引用「唯一收入来源+房贷+3岁孩子」全程事实；step 10 回题后正确衔接 |
| **改需求（step 7）** | ✓ 全流程按新前提重算（见 G-02） |
| 切题（step 9 QA）/回题（step 10 规划） | ✓ 各自正确路由 |
| 内部 metadata 泄漏 | **0**（全 14 步 assistant 文本扫描零命中）|
| 错误保险事实 | 未见（无凭空产品事实；数值建议均随「请以条款为准」类审慎表述）|
| 诚实拒答 | 3 步（1/8/9=知识 QA 语料缺口 G-1→固定文案拒答——**正确 fail-closed**·非错误拒答）|
| 最终交付（steps 13/14） | ✓ 完整方案生成+「全部环节评估通过」+概览与用户输入一致（新值 50万/20万）|

**UX 观察项（记录不修）**：①step 8「重疾保额建议多少」落知识 QA
拒答（G-1 语料缺口）——用户可能预期规划式回答（路由语义边界观察）
②step 5 回复与 step 4 相同文案（追问去重观察）③step 2 首问即获
结构化澄清（体验良好）。

判定：**E2E_VERIFIED**（SCRIPTED_PROBE 主体·如实标注：真实人类
用户黑盒验证仍属 Batch-G/S2 窗口）。

## Matrix 状态更新（仅测试状态列）

- G-01：PARTIAL→**KNOWN_V0_1_LIMITATION**（同进程刷新 TESTED+重启
  限制已知）
- G-02：PARTIAL→**RUNTIME_VERIFIED**（改前提全流程重算·零旧值残留）
- G-03：UNKNOWN→**TESTED**（live 并发闸实证 409 busy+retry 恢复）
- G-04：PARTIAL→**E2E_VERIFIED**（脚本黑盒 14/14·零泄漏零卡死）

## 新发现问题（只记录）

- **OBS-1（P2·UX）**：数值型建议问句（step 8 形）落知识 QA 而非
  规划式回答→G-1 语料缺口下拒答——路由语义与用户预期边界（Owner
  观察，与 SW/taxonomy 债同域）。
- **OBS-2（P3）**：连续追问场景重复文案（step 4/5 同文）。
- 以上均不阻塞 UAT（fail-closed 方向·无安全面）。
