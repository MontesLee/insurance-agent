# Phase 28.M4 — Router Authority Staging 报告（停在 production gate）

Date: 2026-09-25 · 授权：Owner M4 Staging（禁止直接提升 production
authority=full；全绿后停在 production authorization gate——**本报告即停
在该门**）。依据：ADR-025 §5（APPROVED）staged authority 契约。

## 1. Status

```text
PHASE STATUS: COMPLETE — 全部 staging/equivalence/rollback/observation
gates GREEN；PRODUCTION AUTHORITY NOT RAISED（未在任何持久环境设置
authority；隔离实例已全部关闭；代码默认=slices）
```

## 2. Staging 实现（单一解析器，fail-closed）

**NEW `runtime/router_authority.py`**：`INSURANCE_AGENT_ROUTER_AUTHORITY`
三档——`slices`（默认/未设=现状，逐切片 flag 治理）· `no-plan`（
insurance_qa + product_qa = Router 权威，旁路切片 flag）· `full`（三
路径全权威）。**非法值 raise**（服务器 fail-quiet 块吞掉=什么都不触发
——authority 绝不可能因 typo 而授予）。unknown 永不 staging（无
conversation 行为单元）。单一读取者纪律：git grep 证明唯一 RESOLVER
=router_authority.py（B4 runner 的引用=hermetic 钉扎，非读取）。

**server.py**：切片条件增 authority 支路（governs(intent) OR flag）；
slice_decision 新 reason=**authority**（遥测诚实：权威路径触发与 flag
触发可区分）；其余零改动（缝/事件/产物不动）。

## 3. Unified Router Candidate 验证（三路径统一 dual-run）

golden 候选侧改为 **staged authority**（QA/PQ→no-plan；PL/MD→full）：
**B4 = GREEN 17/17，0 RED**（E1/E2 全维；触发非平凡性沿用 M3 验证）。
M4 staging 套件 9/9：解析矩阵/非法值 fail-closed/**authority 模式 ≡
flag 模式**（同输入同执行身份同结果，reason 可区分）/no-plan 不越界
planning/full 覆盖 planning/modify 澄清永远不入/full 下 QA 无 flag 触发
/回滚到 slices 全 legacy/单读取者纪律。

## 4. Rollback（三态验证 + 真实演练）

- **代码态**：authority 未设=slices=现状（flag 治理）——生产环境未做
  任何持久设置。
- **测试**：回滚 slices+全 flag off → 全 legacy ✓；非法值→拒授 ✓。
- **真实演练**：no-plan→full→**unset+重启**→同组重放：QA 类回到
  knowledge-QA 默认 flag（D4 裁决默认 ON——如实记录：authority 回滚
  不改变切片 flag 默认值，两者独立）；planning/modify 回 flag_off；
  unknown 不变 ✓。

## 5. Isolated Gray Observation（隔离实例；INSUFFICIENT LIVE SAMPLE——
脚本注入流量，live glm-5.3 + mock 治理知识）

| 场景 | no-plan | full | rollback(unset) |
|---|---|---|---|
| 知识问答 | **authority 触发** knowledge-qa（27.8s） | authority 触发 | 默认 flag（D4 ON）触发 |
| 产品问答 | **authority 触发** product-qa（56.1s） | authority 触发 | 默认 flag OFF→legacy |
| 规划 | flag_off→legacy ✓不越界 | **authority 触发** planning（12.6s，正确追问） | flag_off→legacy |
| 无case修改 | flag_off（legacy 澄清） | clarification_required（不入） | flag_off |
| 未知域 | legacy | legacy | legacy |

QA 拒答（citation gate）为 B5.1 已知 live 模型合规现象（非 staging 缺陷
——门 fail-closed 工作正常）。零 slice_error；零异常。

## 6. Full Regression

```text
Backend: 720 → 729 passed / 0 failed（+9 M4 staging 测试）
Web:     148 passed / 2 skipped / 0 failed · tsc clean
B4:      GREEN（17/17，staged candidates）
```

## 7. Architecture / Governance

- Router=唯一分发点（staging 使其权威化可分级）✓；LLM 零参与 ✓；
  Registry/Intent/Agent 所有权不变 ✓；One Runtime（无新执行面）✓。
- 遗留面（M5 清理项，未动）：demo 关键词映射、legacy chat 工具自选
  路径（full 权威下的 unknown/兜底仍由其承载）、prompt 意图条款。
- git 范围：NEW router_authority.py + test_p28m4_staging.py；
  MODIFIED server.py（authority 支路+reason）、runner.py（BASE_OFF 钉
  扎）、golden JSON（候选 flags）、B6/M3 测试断言按 M4 现实更新。

## 8. Final Gate

```text
所有 staging/equivalence/rollback/observation gates: GREEN
Production Router Authority: NOT RAISED（代码默认 slices；无持久设置）
>>> 停在 PRODUCTION AUTHORITY AUTHORIZATION GATE <<<
```

**Owner 决策项（不代决）**：是否将生产环境 authority 提升至 no-plan/
full（建议路径：先 no-plan 灰度观察真实流量 → 再 full + M5 清理授权）；
提升时机的流量样本要求（当前 INSUFFICIENT LIVE SAMPLE）。
