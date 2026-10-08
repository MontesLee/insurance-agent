# K.29 · Owner Decision Package — QA 能力验证链路（Phase 2-4 汇总）

Date: 2026-10-02 · Mode: DECISION PACKAGE（只描述选项·不自选）

---

## 1. Current State

- **Phase 1 修复 LIVE（磁盘代码）**:_GatewayProviderAdapter 现转发
  system_prompt;qa-answer-v3（2043 字符）经生产组合逐字节到达
  provider（tmp/obs/k29_phase2_delivery_verify.json 全过）。
  **:8123 仍跑修复前码——重启即载入（Owner 决策点·独立于本包）**。
- 全回归 870+2（基线 865+2·零新增失败）;Intent/C1/C2/Claim Support/
  Citation Gate/K.26 全 SEALED 未动;HYBRID_ANSWER_ENABLED=OFF;
  S2 Batch-2 OPEN-UNSTARTED。
- **修复后生产 QA 实测（A-fixed·40 例×2 模型·冻结语料）**:
  grounded **0/30+0/30**——交付面仍全拒（诚实拒答·fail-closed）。

## 2. Evidence（路径+关键数）

| 证据 | 路径 |
|---|---|
| 送达验证（4 检查全过） | tmp/obs/k29_phase2_delivery_verify.json |
| A-fixed benchmark | tmp/obs/k29b/A_fixed_main_all.jsonl / A_fixed_flash_all.jsonl |
| Before/After 对比+安全 | tmp/obs/k29_phase2_before_after.json |
| Phase 1 修复+回归 | docs/production/k29-bfix-phase1-implementation.md |
| Phase 0 审计 | docs/production/k29-bfix-prompt-delivery-audit.md |
| Phase 3 归因 | docs/production/k29-phase3-b-resolution.md |
| K.29-B 基线 benchmark | docs/production/phase-29-B-offline-benchmark.md |

关键数（before → after·main/flash）:

| 维度 | main | flash |
|---|---|---|
| 引用完整度 | 0.273→**0.381** | 0.246→**0.402** |
| no_citation 违规 | 35→**1** | 47→**3** |
| would-be 真违规（安全面·改善） | 16→**1** | 11→**5** |
| false success（交付面） | 0→**0** | 0→**0** |
| claim_support 拦截 | 55→107（瓶颈迁移） | 30→112 |
| grounded | 0→**0** | 0→**0** |

拒答构成（修复后·权威）:纯 Claim Support 拦截 22/23+20/23·
纯引用纪律 1/23+3/23;PARTIAL（paraphrase）为最大违规类
（78/61 条）·UNSUPPORTED 次之（29/51·多为证据缺失叙述）。

## 3. Remaining Blockers（进入 Hybrid Shadow 的前置缺口）

1. **Claim Support paraphrase 天花板（P 杠杆）**:cited∧PARTIAL 被
   SUPPORTED-only 规则拒——上界模拟:接受 PARTIAL 可翻转 12/23
   （main）·9/23（flash）拒答。**触碰 SEALED Claim Support 规则**。
2. **证据缺失叙述不可证（meta 杠杆）**:「证据未提及X[E1]」类诚实
   prose 词法不可证——豁免可再翻转 7/23·7/23。同上 SEALED。
3. **判定缺口（ws/锚元数据）**:微量（+1 翻转）;已定位可修
   （FIX1/FIX2 同族）。
4. **OD-H3 R4 路由**:MODE-B 的 R4 保护目前是 oracle 门（4/5 R4 问句
   现分类 insurance_qa）。
5. **残余真违规**:全杠杆后 4/6 例记录（每例 1-2 claim·meta 变体/
   推断句/监管定义改写）——需人工裁定语义或保持拒答。

## 4. Options（只描述·不选择）

### Option A — 保持 KB_ONLY（现状=修复已上线）

- 行为:引用纪律修复后的诚实全拒（0/30 grounded）;无泄漏·无
  false success;用户感知=「暂时无法回答」。
- 成本:零（已完成）;QA 可用性维持 0（保险通识/概念题全拒——
  G-1 语料外的 R0/R1 问题继续失语）。
- 何时合适:优先 Batch-2 UAT（拒答=安全正确·K.28-II-S2 窗口独立）、
  或 Owner 认为当前阶段可用性损失可接受。

### Option B — 进入 K.29-C Hybrid Shadow

- 行为:MODE-B/C 生成影子（不投递）·零 authority;量化 hybrid 在
  生产流量形态下的边界遵守/引用/违规分布。
- **前置**:Phase 3 §4.3——判定层杠杆未裁决时,shadow 的 claim
  级信号会混入校准噪声（strict 支持率 26-40% 主要是天花板而非
  模型行为）;建议先裁决 P/meta 杠杆（即 Option C 的一部分）再
  开 shadow,或接受噪声并只读 generation-side 指标。
- 成本:影子实现（qa_agent 组装层 policy 判定+生成·不投递）≈
  一个受控阶段;风险低（零 authority·零投递）。

### Option C — 模型/回答结构/判定层校准优化

- C-1 判定层三杠杆（全部触碰 SEALED Claim Support——需解封授权+
  金标语料回归 + FIX 系列流程）:
  - 接受 cited∧PARTIAL（或 cited-claim 支持语义放宽）→ 上界
    main 12/23·flash 9/23 翻转;
  - 证据缺失叙述豁免类（同 K.28-II taxonomy 语义·需金标裁定）→
    再 +7/+7;
  - ws 归一化 + 锚元数据入搜索域（FIX1/FIX2 同族小修）→ +1。
  - 合计上界:**19/23（main）·17/23（flash）翻转·残余 4/6 例**。
- C-2 回答结构约束（不动判定层）:hybrid 提示词的句帽效应
  （K.29-B §6.2:c5 甜点区引用 83-89%）——但 KB_ONLY 臂对句帽
  免疫（生产提示词形态主导）,收益限 hybrid 路径。
- C-3 模型选型:main 引用纪律优/invented 0;flash 边界遵守优·
  引用纪律弱（42%）+invented 3——K.30/K.35 槽位体系已支持切换。
- 成本:每杠杆=独立 FIX 阶段（审计→设计→实施→金标回归→灰度）;
  收益=直接解锁 grounded（最高 ~80% QA 例）。

## 5. 附注（不属于选项·状态事实）

- 修复对 :8123 生效需 Owner 重启（载入同时含 K.28-II P2-1/FIX2/
  OBS-1/本修复的全部累积变更）。
- .env 仍指按量端点（余额耗尽 429/1113）——重启前须先裁决端点
  （充值 vs 切 coding plan·benchmark 用的 api.z.ai 已验证可用）。
- 判定层三杠杆若授权实施,建议顺序:ws/锚元数据（最小·纯缺陷族）
  → meta 豁免（金标语料裁定）→ PARTIAL 政策（语义变化最大·
  OD-12 式门槛冻结先行）。

---

*本包不含推荐选项。Owner 裁决后按对应轨道立项。*
