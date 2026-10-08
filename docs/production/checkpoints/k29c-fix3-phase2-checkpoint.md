# K.29-C FIX-3 Phase 2 — Deterministic Production Implementation · Checkpoint

## Phase 0 (2026-10-02) — 授权边界冻结

### OWNER_AUTHORIZED_SCOPE（OD-FIX3 决策书 2026-10-02）
1. **B**（C3v2 guarded exemption）生产实现——deterministic·fail-closed·
   默认 OFF 旗·硬类终局不变
2. **D**（recommendation+numeric premise defense）生产实现——前提
   拆解判定·纯数字建议不误伤
3. **baseline safety debt hardening**（OD-FIX3-2·全部 deterministic）:
   range/interval 边界关系·unit/multiplier(元/万元/%/倍/天/月/年+业务
   单位)·product identity binding(用现有 contract·不重设计 catalog·
   缺 product_id 即 STOP 记 BLOCKER·不伪造)·date/time constraint
   (元数据不足即 STOP·不用脆弱 heuristic)
4. 必要 regression/benchmark validation(冻结 v2 只读)
5. S1' **仅准备**（judge interface/schema/logging/timeout/UNCERTAIN/
   cost 契约);loop.py 仅最小非行为 observation seam(无 judge
   authority·不改 K.26)
6. 解封范围(OD-FIX3-4 PARTIAL):claim_support.py+必需 rules/config;
   loop.py 仅 seam

### NOT_AUTHORIZED_SCOPE
- Semantic Judge production authority/改变生产答案/改变 Claim Support
  decision·真实 Shadow 启动（OD-FIX3-3 GATE:须 B+D+债+回归+冻结
  验证全过后另批）·观察窗/资源（OD-FIX3-5 NOT YET）
- Hybrid/S2/Batch-2/OD-12 authority 变更
- Intent/Router/C2/WeKnora/Citation Gate/K.26 streaming 修改
- 冻结 Benchmark/Golden 任何修改（含为通过测试）
- CLAIM_SUPPORT authority 语义超出 B+D+债 的任何变化

### HARD STOP（OD-FIX3-6 冻结）
HIGH_RISK_FALSE_UPGRADE>0 ∨ R3 escape>0 ∨ R4 escape>0 ∨ numeric
escape>0 ∨ contradiction escape>0 → 立即 STOP/NO PROMOTION·不得
放宽规则消失败

### 实施顺序
P1 B → P2 D → P3 债(A 区间/B 单位/C 产品身份/D 日期) → P4 测试
(18 类×4 臂+OFF 等价) → P5 冻结 v2 验证 → P6 全回归 → P7 judge
准备+loop seam → P8 S1' 就绪文档 → P9 diff 审计 → P10 回滚验证 →
P11 终报

- blockers: 无

## Phase 1-11 (2026-10-02) — ALL COMPLETE
- **PRODUCTION_IMPLEMENTATION_PASS**(终报 k29c-fix3-phase2-production-
  implementation.md)
- 实施:claim_support.py(B 豁免+D 前提扫描双默认 OFF 旗+无条件债硬化:
  单位词表/区间双向关系/产品名渐进变体/日期整串)+rules 双块+loop 缝
  (observer=None)+shadow_judge.py(准备件)+test_fix3_bd.py(25)+validate 工具。
- 调试修正史(如实):区间边检测需放宽单位匹配·产品名贪婪前缀误捕
  (因为重疾险)改渐进变体·标注锚冲突容忍证据区间(保额4∈3-5)·
  FIX2 边界正则挡日期内部数字→Y年M月D日整串·倍在 CALC 词表→D 扩
  典型值断言·建议句 F-1 形态在 C1/B 的放行=按臂断言(文档化)。
- Phase5 验证(生产 check()·v2 82):三臂候选新增逃逸 **0**;债硬化使
  C1 基线 13→11(F5-08+F6-08 关闭);D 再关 5(F4 7→2)。
- Phase6 全电池 **895+2 零失败**(=870+25 新);65-check 65/65 不变;
  金标 104 HEAD-vs-新 **103 同/1 异=N4-3 修复**(Layer A 假支持-1)。
- Phase9 diff 审计:生产变更恰=授权三文件+新准备件。
- Phase10 回滚:自动化证明(旗关等价/env kill-switch/缝双恒定/坍缩)。
- Phase11 S1' readiness=READY(未启动)。
- **STOP——等 Owner:B/D 灰度开启+S1' 启动与资源+span 续封。**
