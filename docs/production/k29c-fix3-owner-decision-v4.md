# K.29-C FIX-3 · Owner Decision Package v4 — 生产实施就绪性

Date: 2026-10-02 · 依据:Phase 1 离线验证 + Phase 1.5 就绪性审计
(全部 READ-ONLY 完成)。证据 JSON:tmp/obs/k29c_fix3_phase1_5_*.json(6 件)。

---

## 1. Executive Summary

**如果 Owner 决定推进 FIX-3,当前仓库已具备安全、最小、可回滚的
生产实施路径**:B+D 合计只触碰 1 个生产代码文件(claim_support.py
check() 内两处·约 +30 行)+1 个配置块;双独立默认 OFF 旋钮沿
CLAIM_SUPPORT_ENABLED 先例(OFF=字节级现行·可测);离线证据
(82 冻结语料+四臂+判定 S0)支持零新增逃逸;回滚矩阵覆盖 7 类
失败场景且两条不变量(判定失败≠不安全降级·影子失败≠影响生产答案)
结构性成立。**未授权任何实施**——六项 Owner 决策列于 §13。

## 2. Phase 1 证据摘要

- Benchmark v2 82 FROZEN·两审一致 97.6%;B/D/BD **零新增逃逸**
  (金标+v2);D 关闭 F-1(F4 逃逸 7→3);B 翻转 2/1·F3 4→6。
- Semantic Judge S0:F2 反转 **12/12**·F1 真改写 **10/10**·泛化/半真
  保持 11/11·**管线级 FALSE_UPGRADE=0**(唯一 judge 假升被硬类前置
  拦截——前置过滤为必要设计)·稳定性 90%·延迟 6.5s/20.7s。
- 组合管线投影翻转 main 6/23·flash 5/23(R3 两例待真实流量验证)。

## 3. 当前生产边界(未变)

Claim Support SEALED(D-08@24082d5+FIX2 层)·Production Shadow OFF·
Hybrid OFF(HYBRID_ANSWER 未设)·S2 OPEN-UNSTARTED·Batch-2 未分发·
全封印件 mtime 未动(Phase 7 审计零非预期变更)。

## 4. B+D 实施面(详见 implementation_surface.json)

- **B**:check() 内豁免过滤器(~12 行·护栏正则外置 rules);
  flag=claim_support.exemption_v2(默认 OFF)+env 覆盖。
- **D**:check() 循环内 REC/UNCERTAIN∧数字锚→按 C-FACT 全规重判
  (~15 行);flag=premise_scan(默认 OFF)。不拆句·不新增taxonomy。
- **OFF 字节等价**:可测(先例:CLAIM_SUPPORT_ENABLED 上线即此法)。

## 5. 基线债(v2 暴露 13 例 C1 逃逸)

F-1×7(D 关闭)·词法假支持×3·产品身份×1·范围扩展×1·时点×1。
FIX 级可修:区间/单位词表(FIX2 同族)·catalog 产品名覆盖。

## 6. 四类缺口判定

| 缺口 | 判定 | 最小补齐点 |
|---|---|---|
| 区间/单位(倍/%) | **MISSING** | _BARE_NUM_RE 词表(Stage B) |
| 范围扩展(重疾→轻症) | PARTIAL(词法部分捕捉) | 语义层+未来术语覆盖设计 |
| 产品文本 vs product_id | **PARTIAL**(机制在·覆盖缺) | _product_ok/catalog 覆盖(Stage B) |
| 时点限定(2023年的) | MISSING(by design) | R5 时态扩展=独立设计债 |

## 7. 测试影响(18 类·test_impact.json)

新 FIX-3 套件(T01-T18:行为/对抗/回归锁三类)+OFF 等价+65-check
逐位+全电池零新增;S0 六项离线测试;**反 gaming 规则**:实现期间
一切冻结 Golden 只读,标签修订=corpus-revision 独立阶段+二审+Owner。

## 8. 回滚设计(rollback_matrix.json)

七场景(A-G)×OFF/回 C1/禁升/保门/行为回滚全覆盖;两不变量成立:
判定任何失败坍缩 KEEP_BASELINE(永不 unsafe downgrade);影子任何
失败只影响记录(永不影响生产答案)。

## 9. S1' 影子就绪(shadow_readiness.json)

**有条件就绪**:设计/离线证据/回滚齐备;启动前置=B/D 底座(Stage A)
+loop 观测缝解封+资源与阈值 Owner 批准。指标三分:HARD STOP(3 项)
/OWNER_DECISION(5 项)/观察(其余)——**本包不设任何生产 authority
阈值**(OWNER_DECISION_REQUIRED 标注)。

## 10. 授权/解封地图(authorization_map.json)

A 无需解封(工具/语料/测试)·B 三处边界(claim_support/rules/loop
·可分批)·C ADR 动作(ADR-022 附裁决+新影子 ADR 候选)·D OD-12
更新点(框架零改·执行记录并入·BASELINE_v2 并存建议)·E 六项 Owner
显批·F 七项永不由 Claude Code 决定。

## 11. 分阶段实施路径(implementation-plan.md·全部未授权)

Stage A(B+D)→B(基线债)→C(回归验证=A/B DoD)→D(判定离线扩展·
可与 A/B 并行)→E(S1' 影子)→F(Owner 复核)→G(远期 authority
占位)。每 Stage 含 scope/files/tests/evidence/rollback/approval
gate/STOP condition。

## 12. Explicit Blockers(需 Owner 授权方可动)

```
BLOCKER-1: claim_support.py 任何修改(D-08 SEALED)——OD-FIX3-1/2/4
BLOCKER-2: qa-grounding-rules.yaml 配置块——同批 OD-FIX3-4
BLOCKER-3: loop.py 观测缝(S1')——OD-FIX3-3/4
BLOCKER-4: 影子启动资源/窗口/阈值——OD-FIX3-5/6
BLOCKER-5: Benchmark v2 标签修订(corpus-revision 独立阶段)
BLOCKER-6: 判定 authority 授予(远期·独立 ADR+门槛)
```

## 13. Owner Decisions Required

- **OD-FIX3-1**:是否授权 B+D 进入生产实现?
- **OD-FIX3-2**:是否授权 baseline debt hardening(区间单位+产品绑定)?
- **OD-FIX3-3**:是否授权 Semantic Judge S1' Shadow 准备/实施?
- **OD-FIX3-4**:批准哪些 SEALED boundary 解封(claim_support/rules/
  loop·可分批)?
- **OD-FIX3-5**:S1' 观察窗与资源(时长·judge 槽位·成本上限)?
- **OD-FIX3-6**:哪些指标属 HARD STOP·Owner 指标阈值冻结?

---

**Evidence supports the following candidate paths**(不构成推荐·
选项呈现见 owner-decision-v3.md §D 与本包 §11 依赖图):

- 路径甲:OD-FIX3-1+2+4(同批)→ A+B+C → 再议 D/E
- 路径乙:OD-FIX3-1+2+3+4+5+6(全批)→ A+B ∥ D → E(S1')
- 路径丙:仅 OD-FIX3-2(先债后候选)→ 再议 A
- 路径丁:不批准(维持现状·Option 4)

**最终状态:READY_FOR_OWNER_DECISION**
