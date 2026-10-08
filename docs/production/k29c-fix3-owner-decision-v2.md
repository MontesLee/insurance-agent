# K.29-C FIX-3 · Owner Decision v2

Date: 2026-10-02 · 输入:Phase 0 全套工件（审计/v2 plan/模拟器设计/
shadow 设计）·全部零生产改动完成。

---

## Decision 1 — 是否授权 B+D 离线验证？

**建议:授权（低成本·高信息·零生产面）**

- 内容:编写 tools/k29c_fix3_simulation.py(设计已冻结·四臂
  C1/B/D/BD·安全四指标硬门+收益三指标·分钟级离线运行)。
- 授权的是**离线工具与运行**,不是实施:B/D 的生产实施(claim_
  support.py B-i/D-i 插入·SEALED 解封)仍需其后的独立授权
  (以模拟结果+v2 语料硬门为输入)。
- 不授权的后果:Decision 2/3 缺量化输入;FIX-3 停在纸面。
- 风险:无(纯离线·不触生产/Golden/SEALED)。

## Decision 2 — 是否准备 Semantic Judge Shadow？

**建议:授权「准备」=S0 离线评测器实现(不挂接·不开启)**

- 内容:按 k29c-semantic-shadow-design.md §3 规格实现离线 judge
  评测(对金标/v2 语料重放 ALLOW_UPGRADE/KEEP_BASELINE/UNCERTAIN),
  产出 would-flip/would-escape/反转召回数据。
- **明确不属于本次授权**:S1' in-process 影子(loop.py 观测缝)、
  任何 authority、任何 run 时调用。三者各自需未来独立授权。
- 成本:judge 模型槽位与调用预算(金标 104+v2 73≈200 次小调用/
  轮·重放 3 轮稳定性≈600 次)——需 Owner 指定模型(coding plan
  端点已验证可用)。
- 不授权的后果:E 类 61% 主体无安全解锁路径的证据;Option C
  停留概念。

## Decision 3 — Benchmark v2 是否冻结？

**建议:暂缓冻结·先批准生成规则,样本生成后二审再冻**

- 现状:tests/golden/k29c_fix3_benchmark_v2_plan.json(0.2-plan-
  only·六族·最低配额 73·F2/F4/F5/F6-anchor=硬门·含 F6 证据冲突
  盲区首次入册)。
- 建议顺序:①Owner 批准 plan(配额/来源配比/生成规则)→ ②样本
  生成(独立小阶段·金标派生不动原文件)→ ③首评+受审修正 →
  ④二审(是否需要第二评审人=本 Decision 子项)→ ⑤冻结 v1.0+
  回归锁。
- 争议点预披露:F5 的 metadata-date 子集(该办法自2019年12月1日
  起施行)在现行规则下必然 REJECT——语义上该 ACCEPT 但属 C4 已
  否决域;plan 将其定为「钉住语义的 REJECT+设计注记」·冻结时
  Owner 可改判。
- 不冻结的后果:B/D/C 的验收硬门悬空(金标 v1 负面族覆盖否定
  反转但无 F4/F6 形态)。

---

## 附:Phase 0 工件索引

| 工件 | 路径 |
|---|---|
| 架构审计(管线/插入点/SEALED/OD-12 路径) | docs/production/k29c-fix3-phase0-audit.md |
| Benchmark v2 计划(schema+生成规则·零样本) | tests/golden/k29c_fix3_benchmark_v2_plan.json |
| B+D 离线模拟器设计 | tools/k29c_fix3_simulation_plan.md |
| Semantic Shadow 设计(三值·错误→KEEP_BASELINE) | docs/production/k29c-semantic-shadow-design.md |
| 决策包 | 本文件 |

前置链:K.29-B benchmark → K.29-C 校准研究 → FIX-3 设计
(k29c-fix3-design.md)→ **本 Phase 0**。

## 生产改动清单(本阶段)

**零。** claim_support/gate/C2/Golden/taxonomy/env/Hybrid/S2 全部
未触碰(Phase-1 prompt 修复为此前已授权阶段的遗留·已在工作树)。
