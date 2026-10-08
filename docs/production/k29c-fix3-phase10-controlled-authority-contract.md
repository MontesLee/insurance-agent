FINAL STATUS: CONTROLLED_AUTHORITY_CANDIDATE_READY_FOR_OWNER_DECISION

# K.29-C FIX-3 Phase 10 · Controlled Authority Contract Review & Rollout Readiness

Date: 2026-10-03 · Mode: **CONTRACT/GOVERNANCE ONLY**(零生产改动·
零新 LLM·零 corpus 扩张)——本阶段价值=把 Phase 8/9 安全证据固化为
可执行·可回滚·scope 封闭·fail-closed 的 Authority Contract。

---

## 1. Production Changes

**零**。git 44=既有稳定计数;新增仅 tools/×2 + docs + tmp/obs(4 件)
+ checkpoint。`AuthorityContract` 为 tools-only 治理件,零 runtime
import(grep 证·见 §11)。

## 2. Frozen Components(全部逐项核对·零触碰)

Intent/C1/C2/K.26/K.25/Consumer 栈/D-08/OD-12 全 SEALED-FROZEN·
Semantic Judge=SHADOW ONLY·Candidate-C=shadow candidate·Hybrid=OFF·
S2=UNCHANGED·Batch-2 未分发·Mode B 未启动·taxonomy/τ FROZEN·
production authority NOT GRANTED。

## 3. Authority Scope(机器可读矩阵·`k29c_fix3_phase10_scope_matrix.json`)

**AUTHORIZED/CANDIDATE 仅一类**:`FACTUAL_PARAPHRASE`(证据已支持
核心事实·输出为语义改写·无新增数字/产品/时间/监管/支付/个性化/
全称/矛盾裁决/R4)。
**HARD-BLOCKED 八类**:NUMERIC/PRODUCT/REGULATORY/PAYMENT/DATE_TIME/
CONTRADICTION/UNIVERSAL_GENERALIZATION/R4_PERSONALIZATION——
Candidate-C 最多 observation·**永不产生 production authority
upgrade**·fallback=baseline。**每类单一明确结论·ambiguous=0。**

## 4. Authority Contract(`k29c_fix3_phase10_authority_contract.json`)

六前置合取(baseline=PARTIAL∧citation 有效∧硬类前置 PASS∧风险边界
PASS∧judge ALLOW∧**独立 post-gate PASS**)→ ALLOW;任一
false/timeout/malformed/unavailable/uncertain → **KEEP_BASELINE**。
禁止清单成文:fallback-to-Judge-ALLOW/fallback-to-candidate/fail-open
——contract 代码中不存在这些路径。**Candidate-C ≠ Semantic Judge
Authority:候选对象仅是完整管线。**

## 5. Kill Switch & 6. Rollback

默认 **authority=OFF**(kill_switch=ON)。验证(§Task 3):
OFF→基线(三形态案例 contract 输出==确定性基线**且 judge_invoked=
False**·判定等价+零调用面);ON→仅模拟(本阶段从未置真·审计完整性
保留);OFF-again→基线。**verdict=ROLLBACK_CONTRACT_VERIFIED**。

## 7. Shadow Isolation(§Task 4·七对抗案例全过)

shadow ALLOW/KEEP/timeout/malformed/unavailable/exception +
production exception——contract OFF 模式**从不读取 shadow 输出·从不
调用 judge**(7/7 judge_invoked=False·final≠ALLOW);机制:shadow
ledger 为独立文件·生产路径零消费者。**Shadow→Production 路径
不存在。**

## 8. Failure Injection(§Task 6·A-N+V=16 注入全过·fail→ALLOW=0)

baseline/evidence/citation/硬类/风险边界变异·judge ALLOW/REJECT/
UNCERTAIN·post-gate FAIL/TIMEOUT/MALFORMED/UNAVAILABLE·kill-switch
OFF·shadow 隔离破坏模拟——**全部返回确定性基线·judge 从未被调用**
(fail_to_allow=0)。

## 9. Negative Control(§Task 7)

全健康链(隔离模拟·authority ON 从未上真机):**ALLOW_UPGRADE ✓**——
非 blanket refusal·utility 契约成立(UTILITY_CONTRACT_FAILED 未触发)。

## 10. Version Binding(§Task 11)

绑定 contract/pipeline/postgate 三版本;**mismatch/unknown/missing →
KEEP_BASELINE**(三注入实证);禁止「最新代码自动成为 Authority」。

## 11. Authority Path Audit(§Task 9·`k29c_fix3_phase10_path_audit.json`)

八项检查全 PASS:shadow 旗不可覆写生产结果·无环境变量可意外开
authority·异常路径无 Judge 回退·unavailable 无 candidate 回退·
配置默认全 OFF·test 旗零生产 import·ops 启动器不能改变生产决定
(观察者仅写 tmp 文件)·**零 SHADOW→PRODUCTION 路径**。
**implicit_authority_paths_found = 0。**(非 loop 的 runtime 命中=
shadow_judge.py 自身——Phase-2 已建立的隔离准备件·零门路径。)

## 12. Governance State Machine(§Task 10·正式固定)

`SHADOW_ONLY → CANDIDATE → OWNER_REVIEW → CONTROLLED_AUTHORITY →
FULL_AUTHORITY`;禁止跳级(SHADOW_ONLY→FULL/CANDIDATE→FULL)·禁止
runtime 自动 promotion;**任何 promotion=Owner Decision**(记录
who/when/scope/version/evidence/rollback)。当前状态=**CANDIDATE**
(Phase-8/9 证据+本 contract)。

## 13. Production Equivalence(§Task 8·Phase-9 ledger 复用·零新调用)

82 ledger:upgrade=0·unexpected=0·高危=0;答案文本=与腿前栈逐字
一致;无 Candidate-C artifact·无运行时副作用。

## 14. Safety Gates(§十七)

HIGH_RISK/R3/R4/NUMERIC/PRODUCT/REGULATORY/PAYMENT/DATE_TIME/
CONTRADICTION/UNIVERSAL_GENERALIZATION_ESCAPE=0·SHADOW_TO_PRODUCTION_
LEAK=0·**FAIL_OPEN=0**·ROLLBACK_FAILURE=0·VERSION_MISMATCH_ALLOW=0
——**全零·NOT_READY 未触发**。

## 15. Remaining Risks

①真实用户措辞分布仍未采样(fixture 为主——Batch-2 Mode A 依赖)·
②严格 C3 效用边界(E 类 UNSUPPORTED 不可升=C3 修订议题·Phase-8
发现)·③Controlled Authority 真形态需生产化设计(缝挂接+同步超时
坍缩+kill-switch 实弹演练——状态机 OWNER_REVIEW 前置已列)·
④coding plan 端点配额面持续观察。

## 16. Owner Decisions OD-FIX3-42..48

见 `k29c-fix3-owner-decision-v11.md`(§OD-42 独立 PG 验证接受/
OD-43 Candidate-C 管线候选认定/OD-44 FACTUAL_PARAPHRASE 入未来
scope(**非当前授权**)/OD-45 八类 HARD-BLOCKED 维持/OD-46 影子→
生产必须 Owner 状态迁移/OD-47 下一阶段=Controlled Authority
Preflight(**非直接授权**)/OD-48 Mode B 未启动+Hybrid OFF+taxonomy/
τ 冻结维持)。

## 17. Exact Next Step

Owner 裁决 OD-FIX3-42..48 → 若 47 批准:**Controlled Authority
Preflight**(生产化设计+kill-switch 实弹演练+观察窗/预算+OD-12 式
门槛冻结——全部为新的 Owner-gated 阶段)。

---

**Authority = NOT GRANTED · Batch-2 Mode B = NOT STARTED ·
Hybrid = OFF · taxonomy = FROZEN · τ = FROZEN**
