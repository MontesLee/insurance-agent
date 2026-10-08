# 28.K.28-II-S2 · Expanded Gray 执行与观察

Date: 2026-09-29 启动 · Mode: **EXECUTION + OBSERVATION（零修改）** ·
状态：**S2 EXPANDED_GRAY — WINDOW OPEN（48h·自 Batch-2 分发起算）**
→ 完成报告待窗口期满（本文件为执行+协议+Cycle 记录）

## 1. Owner 参数（§0 原文）

Traffic=既有 pilot-key 机制·下一批次≈3×S1 ·Window=**48h 连续** ·
Claim Support=ON·LLM Judge=OFF·Planning=OFF·Authority NOT GRANTED。

## 2. 批次确定性识别（§2·仓库证据）

- K.3 预设序列：Batch-1=01/02（已分发）→ **Batch-2=03/04/05**
  （门=Batch-1 零 P0/P1 ✓历史全零）→ Batch-3=06/07/08（门=Batch-2
  安全）。REGISTRY 明载 03..08 UNDISTRIBUTED。
- 「≈3×」对账：S1=2 把已分发 → S2 准入 5 把（+3）≈2.5×；新增
  3 把=1.5×——按仓库唯一确定性读法取 **Batch-2（3 把）**，倍数
  口径差异如实记录。
- 未发明任何 instance/key/路由（§2 合规）。

## 3. Pre-Expansion Gate（§4·2026-09-29 17:2x 新鲜复验）

| 检查 | 结果 |
|---|---|
| Runtime | :8123 PID 25928·24082d5·工作树≡blob·health 200 |
| ON/OFF 签名 | **VERIFIED**（in-process 复验） |
| RV4-B | **refused**（真实 rules 复探） |
| RV4-A | C2 **0 qualified** |
| Escape/新增FP/Leakage/流式泄漏 | **0**（Seal 后零新流量·计数延续） |
| FR/P-R/负例类 | 沿 OD12_BASELINE（0/6·0.80/0.80·全 blocked） |
证据：`tmp/obs/k28ii_s2_pregate.json`。**门 PASS → 进入 S2。**

## 4. Enablement（§3）

本仓机制中灰度维度=**密钥准入面**（单实例+实例级 flag）：
- 实例/flag **沿 S1 不变**（:8123·PID 25928·CLAIM_SUPPORT_ENABLED=1
  ·全局默认零改动·无重启）；
- **Batch-2 staging**（K.3/K.12 惯例）：`distribute/{03,04,05}.key`
  （token-only）+ REGISTRY 批注 + `HANDOFF-s2-batch2.md`；
- **Owner 物理分发=窗口起点**（K.3 先例）——分发时刻由 Owner 记录
  于 REGISTRY（未分发前流量面=S1 等价，窗口不起算）。

## 5. 观察协议（§5·既有面·零新持久化）

- Hard Safety：Escape（transcript 审计）/新增 FP/Leakage（consumer
  面扫描）/流式泄漏（delta 审计）/RV4-B 放行/冻结组件回归（intent·
  C1·C2·K.26 套件）
- Quality：FR（拒答+attempts）/同根因重复/负例拦截
- Operations：runtime 错误·检索失败·EventBus/SSE 异常·回滚可用性
- 已知限制沿 S2-READINESS：per-claim 行不持久化（深查=探针+语料
  replay；本阶段不实现）
- **Cycle 机制**：会话内 3h 周期任务（session-bound·最长 7 天）+
  跨会话回放协议（checkpoint §K.28-II-S2）；记录
  `tmp/obs/k28ii_s2_observation.jsonl`

## 6. 自动回滚规则（§6·沿 OD-12 Gate A1-A6）

任一命中：停扩灰流量→现有机制回滚（env=0→restart→OFF 签名→旧路径
验证）→保全证据→报告精确失败→STOP。不自修代码、失败后不继续观察。

## 7. Cycle 记录

| Cycle | 时间 | 新 run | Escape | 泄漏 | 流式 | RV4-B | 冻结回归 | 备注 |
|---|---|---|---|---|---|---|---|---|
| 0（预门） | 09-29 17:2x | 0 | 0 | 0 | 0 | refused ✓ | ✓ | Batch-2 staged；窗口待 Owner 分发起算 |
| （后续 cycle 追加） | | | | | | | | |

## 8. S2→S3 边界（§7·冻结）

48h 期满零 Hard Safety 失败 → 产出 **S2 OBSERVATION COMPLETE** +
Owner Decision Block——**不自动 S3·不开 Authority·不改阈值/OD-12/
D-08**。

## 9. 状态声明（如实）

- 执行=**COMPLETE（扩灰就绪+Batch-2 staged+协议装载）**
- 窗口=**OPEN-BUT-UNSTARTED**（Owner 物理分发=起算点·截至本报告
  未分发→真实流量面仍=S1 等价·不伪造窗口计时）
- 48h 完成报告=窗口期满后产出（本文件 §7 持续追加）

## 10. Scope Audit（§11）

生产逻辑/baseline/语料/D-08/OD-12/Intent/C1/C2/K.26 修改=0·
Planning/LLM 开启=0·新 rollout framework=0·percentage routing=0。
新增=REGISTRY 批注+distribute 文件+HANDOFF+观察文件（既有惯例内）。
