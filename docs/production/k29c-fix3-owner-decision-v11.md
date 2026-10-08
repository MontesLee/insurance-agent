# K.29-C FIX-3 · Owner Decision Package v11

Date: 2026-10-03 · 输入:Phase 10 Controlled Authority Contract(
零生产改动·零新 LLM·零 corpus 扩张)。详报:k29c-fix3-phase10-
controlled-authority-contract.md;证据:tmp/obs/k29c_fix3_phase10_*
(4 件)。**只提交证据·不代决策·任何内容 ≠ AUTHORITY_GRANTED。**

---

## 证据核心

- **Authority Contract 成文**(机器可读·六前置合取·禁止清单·版本
  绑定):scope 唯一候选类=FACTUAL_PARAPHRASE·八类 HARD-BLOCKED·
  ambiguous=0。
- **Kill-switch/回滚验证**:OFF=基线(判定等价+judge 零调用·
  ROLLBACK_CONTRACT_VERIFIED);ON 仅存在于隔离模拟。
- **16 项 contract 注入全过**(fail→ALLOW=0)+负控 ALLOW(utility
  契约成立)+七影子隔离对抗全过(零 SHADOW→PRODUCTION 路径)。
- **全仓 authority 路径审计**:八检查 PASS·implicit paths=0。
- 治理状态机固定:当前=CANDIDATE;禁止跳级与自动 promotion。

## Owner Decisions

**OD-FIX3-42 是否接受 Independent Post-Gate = VERIFIED?**
证据:Phase-9 I1-I4 7/7+两项独立否决+fail-closed 4/4;Phase-10
契约注入复证。

**OD-FIX3-43 是否接受 Candidate-C = PIPELINE AUTHORITY CANDIDATE?**
(=状态机 CANDIDATE 位确认)。证据:Phase-8 零逃逸+Phase-9 live
零升级+Phase-10 契约固化。注:候选=完整管线·**≠判定层候选**。

**OD-FIX3-44 是否批准 FACTUAL_PARAPHRASE 进入未来 Controlled
Authority Scope?**(**不是当前 Production Authority**)
证据:唯一 eligible 类·Phase-4/5 E 类恢复信号+零逃逸;scope 定义
含十项否定条件(无新增数字/产品/时间/监管/支付/个性化/全称/矛盾/
R4)。

**OD-FIX3-45 是否批准八类(NUMERIC/PRODUCT/REGULATORY/PAYMENT/
DATE_TIME/CONTRADICTION/UNIVERSAL_GENERALIZATION/R4)继续
HARD-BLOCKED?**
证据:Phase-5/6 判定单独 FU 全落此类·前置拦截 0 绕过·加固零损失。

**OD-FIX3-46 是否接受 Shadow→Production 必须经过 Owner-controlled
state transition?**
证据:Phase-10 审计证明当前无隐式路径;状态机把「未来任何接通」
锁定为 Owner 显式迁移(who/when/scope/version/evidence/rollback
记录)。

**OD-FIX3-47 是否批准下一阶段=Controlled Authority Preflight?**
(**而非直接 Production Authority**)。前置(已列):生产化设计
(loop 缝挂接+同步超时坍缩)·kill-switch 实弹演练·观察窗/资源/
成本预算·OD-12 式门槛冻结·真实措辞采样策略(Batch-2 Mode A 联动
或 Owner 豁免)。

**OD-FIX3-48 是否维持 Batch-2 Mode B = NOT STARTED·Hybrid = OFF·
taxonomy = FROZEN·τ = FROZEN?**
本阶段四项全部保持;Mode A 独立推进议题沿 OD-FIX3-40/34。

## 强制终态

Authority = NOT GRANTED · Batch-2 Mode B = NOT STARTED ·
Hybrid = OFF · taxonomy = FROZEN · τ = FROZEN ·
生产代码改动 = **0**。
