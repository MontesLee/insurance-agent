# Phase 28.K.9 — GLM Provider Health Check + Batch-1 Release Gate

Date: 2026-09-27 · 性质：**HEALTH CHECK + RELEASE GATE ONLY**（零代码/
配置/提示词/凭据/限流改动·未启动 pilot·未触碰孤儿进程[仅只读 HTTP 读取
既有运行证据]·零 commit·未分发 key）。

## 1. Executive Summary

- **更正（K.8 记录勘误）**：K.8 报告"日志 429×1"为 grep 误命中（端
  口号 54296）——后端访问日志实际 **0 条 HTTP 429**。全文更正。
- 时间线法证：全部 6 例 llm_unavailable（K.5×3 + K.8 子集×3 + K.7
  探针×2 计 8 次）延迟聚类 125-216s；生效 QA 预算 timeout_s=60s
  （B5.1 校准值）→ 失败=混合型（部分看门狗超时+部分快速失败），非
  配额拒绝特征。
- **当前探针全绿**：小请求 7/7（2.1-3.1s·中位 2.4s）+ 长上下文
  代表性生成 2/2（23.2s/31.6s——贴近但未超 60s 预算；长答案余量薄）。
- 429 源判定=上游供应商间歇不稳定（延迟+瞬态错误；精确错误类别
  UNKNOWN——网关 call_log 未持久化=可观测性缺口）；本地限流/并发/
  测试harness 均排除（体量分析+非 sim 探针亦失败）。
- **Provider=YELLOW（当前健康·同日反复死路史）→ Batch-1=HOLD**
  （除非 Owner 明示接受 YELLOW 风险；详见 §13-15）。

## 2. G-2 Evidence Timeline（逐例；UNKNOWN=证据不可得）

```text
#  时间(Z,09-26/27) 来源        操作                HTTP  错误类
                     重试数/延迟                        终局
1  ~15:0x  K.5 S02   QA生成(gateway)   UNKNOWN UNKNOWN
   170.7s attempts=2  → llm_unavailable 拒答（用户可见"暂不可用"）
   未恢复（该轮）
2  ~15:2x  K.5 S10t1 同上 155.7s attempts=2 → 同上
3  ~15:3x  K.5 S10t2 同上 215.8s attempts=2 → 同上
4  ~16:5x  K.7探针A2 :8124 QA生成 attempts=1 → llm_unavailable
   （非 sim 窗口——排除 E 为唯一因）
5  ~16:5x  K.7探针A2b 同上
6  17:37:12→17:40:02 K.8子集S01 QA生成 glm attempts=2（171s）
7  17:40:09→17:42:13 K.8子集S02 QA生成 glm attempts=1（126s）
8  17:42:27→17:45:11 K.8子集S06t1 QA生成 glm attempts=2（166s）
   #6-8 事件时间戳取自孤儿实例只读读取（run events）
公共字段：endpoint=glm chat/completions（env 配置）·网关内部重试
数/延迟=UNKNOWN（call_log 未持久化）·6-8 例同窗口两条完整规划链
成功（恢复性实证）
```

## 3. 429 Source Determination

```text
A 上游供应商：成立（最佳解释）——间歇性慢响应（长生成 23-32s 实测）
  + 瞬态错误；精确错误类 UNKNOWN（未持久化）
B 本地网关：部分载体（规范化/重试发生处）但非源
C 本地限流器：排除——任何 60s 窗口 QA 网关调用 ≤~6 << 60/min
D 并发控制：排除——全部顺序轮次
E 测试 harness：非唯一因（K.7 非 sim 探针亦失败）；sim 同配额
  可能为贡献负载（未隔离证明）
F —
确认的 HTTP 429：0（历史全部窗口；K.8"1×429"=端口误命中勘误）
```

## 4. Provider Health Probe（最小受控·无业务数据/无持久状态）

```text
Probe A 单发（主模型）：2.1s 200 正常 ✓
Probe B 顺序×5（主模型）：2.2/2.4/2.8/2.5/2.4s 全 ✓（中位 2.4s）
Probe F 单发（fast 模型）：3.1s ✓
长上下文代表性（≈4K 字符+300 字产出，QA 轮形态）：23.2s ✓ /
  31.6s ✓（贴近 60s 预算——长答案余量薄，OBSERVATION）
有界 9 请求全部成功；未做并发/压力/配额探测（按禁令）
```

## 5. Retry Behavior Verification

```text
代码门（K.7）：单测锁定——瞬态 429→RateLimitError→有界指数退避
  (1.5/4s)→恢复；持续→恰 1+max_retries 次→诚实失败；不可重试→
  立即。本阶段未自然复现 429（Probe C 未触发——按禁令不人工制造）。
live 佐证：#6-8 失败轮的最终形态=诚实"暂不可用"文案（零假成功）；
  同窗口后续轮/链成功=恢复路径存在。
```

## 6. Provider Health Classification：**YELLOW**

```text
当前：无 outage·探针 9/9 绿·无持续 429·无当前 llm_unavailable
史：同日多窗口反复 llm_unavailable（8 次·含 3/8 子集轮死路）+长生成
   延迟贴近预算（31.6s vs 60s）
非 GREEN：反复死路史不满足"no repeated llm_unavailable"
非 RED：当前健康·非持续中断·同窗口恢复实证
```

## 7-10. Safety / S-1 / S-2 / Negative（沿用 K.8 live 证据）

```text
Safety five-zero=PASS · S-1=PASS（受治理 unknown→knowledge-qa·
  K.8 A-D）· S-2=PASS（9 VALID→报告 34.6KB 交付+跨主体 404）·
  Negative=PASS（空证据→fail-closed→needs_review 契约未放宽·套件
  锁定）——均零改动维持。
```

## 11. Performance Observation

```text
探针中位 2.4s/最大 3.1s（小）；长生成 23.2/31.6s；历史轮次首响
5-306s；错误轮 125-216s（含重试消耗）；重试延迟 UNKNOWN（未持久化）。
分类：OBSERVATION / PILOT RISK（长生成贴近 60s 预算=QA 死路主
嫌疑；未优化未改超时——按禁令）。
```

## 12. Accident/Savings Knowledge Gap（仅记录）

```text
accident/savings → 治理证据不足 → fail-closed（K.7 校准后实测
0 命中；医疗/重疾/寿险/综合域有据）。非 K.9 阻断项；未动语料。
```

## 13. Batch-1 Decision：**HOLD**

```text
Safety ✓ S-1 ✓ S-2 ✓ Negative ✓ Runtime 证据完整 ✓
Provider=YELLOW——按 PART 7"acceptable YELLOW"可 GO 的前提是 Owner
明示接受风险；当前证据（同日 3/8 子集轮死路+长生成贴近预算）不足
以默认"acceptable"。故 HOLD，等待 Owner 二选一（下节）。
```

## 14. Blocking Evidence（精确）

```text
①同日多窗口 llm_unavailable ×8（用户可见"稍后再用"死路；K.8 子集
  3/8 生成轮）
②长上下文实测 23-32s vs QA 60s 看门狗——长答案余量薄（31.6s 样本
  已 >50% 预算）
③网关内部重试/错误类不可观测（call_log 未持久化）——根因精确化
  受限（可观测性缺口，非本阶段可修）
```

## 15. Owner Actions Required

```text
选项一（接受风险 GO）：明示接受 YELLOW（QA 轮可能 ~1/4-1/3 暂时
  不可用死路·规划链历史健康）→ 授权 Batch-1 分发。
选项二（再验窗口）：指定时段重跑 K.5 子集（或 QA 探针串）复验
  llm_unavailable 率→若显著降低按新证据重判。
选项三（后续阶段授权修复方向，均非本阶段）：QA timeout_s/生成
  长度校准（rules 配置）· 网关 call_log 持久化（可观测性）·
  供应商配额/套餐核实（凭据侧=administrative）。
```

## 16. Next Phase

```text
Owner 裁决 §15 三选项 → GO 则授权 key 分发（Batch-1 2 用户）+
窗口观察；HOLD 维持则按选项二/三择期。
```

```text
Phase 28.K.9 Status: COMPLETE
Provider Health: YELLOW
S-1: PASS · S-2: PASS · Safety: PASS
Batch-1: HOLD（待 Owner 对 YELLOW 风险的明示裁决）
REAL_USER: 0 · Keys Distributed: 0 · Pilot Runtime: 未启动（孤儿
:8123/:5273 仍在运行但未触碰——仅只读 HTTP 取证；处置待 Owner）·
Code Changes: NONE · Commit: NONE
```
