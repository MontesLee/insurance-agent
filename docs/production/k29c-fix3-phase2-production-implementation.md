# K.29-C FIX-3 Phase 2 · Deterministic Production Implementation — 终报

Date: 2026-10-02 · Status: **PRODUCTION_IMPLEMENTATION_PASS**
授权:OD-FIX3-1(B+D)/ OD-FIX3-2(基线债)/ OD-FIX3-3 GATE(仅准备)/
OD-FIX3-4 PARTIAL(claim_support+rules 解封;loop 仅缝)

---

## 1. Owner Authorization（执行范围核对）

按冻结决策书执行:B+D 生产实现 + 基线债硬化(区间/单位/产品身份/
日期·全部确定性层) + 回归/冻结验证 + S1' 仅准备(未启动 Shadow)。
未越界:Intent/Router/C2/WeKnora/Citation Gate/K.26 流式/OD-12
authority/Hybrid/S2/Batch-2/冻结语料 全部零触碰(§9 diff 审计)。

## 2. Implemented Scope & Files Changed

| 文件 | 变更 | 性质 |
|---|---|---|
| `runtime/grounding/claim_support.py` | B 豁免过滤器 + D 前提扫描(双默认 OFF 旗)+ 无条件债硬化(单位词表 倍/月/年/次/折·区间关系双向·产品名渐进变体身份·日期整串感知·标注锚区间容忍) | 生产代码(解封授权内) |
| `config/qa-grounding-rules.yaml` | `claim_support.exemption_v2` / `premise_scan` 配置块(默认 OFF) | 配置(授权内) |
| `runtime/grounding/loop.py` | `shadow_observer=None` 观测缝(默认无操作)+ Phase-1 修复(既有) | 缝(OD-FIX3-3 准备·零行为) |
| `runtime/grounding/shadow_judge.py` | **新**·S1' 判定客户端+观测/指标 schema(不被生产门 import) | 准备件 |
| `tests/runtime/test_fix3_bd.py` | **新**·25 测试(18 类×4 臂+OFF 等价+回滚+缝+坍缩) | 测试 |
| `tools/k29c_fix3_validate.py` | **新**·Phase 5 验证器 | 工具 |

## 3. B 实现要点

check() 内 C-FACT 类豁免过滤器:白名单=证据缺失叙述(零锚零数字)+
纯程序建议(另需零高危词);护栏正则外置 rules(默认=K.29-C 冻结版);
旗=`exemption_v2`(env EXEMPTION_V2_ENABLED>rules·默认 OFF)。PARTIAL
不能自动变 SUPPORTED(豁免只作用于白名单类);否定/矛盾/数字/产品/
监管/赔付/日期全部保持 C-FACT 终局路径。

## 4. D 实现要点

check() 循环内·类型豁免生效前:C-RECOMMENDATION/C-UNCERTAIN 带数字
锚(或裸数字)→整句按 C-FACT 全规重判(前提必须 SUPPORTED·失败关门)
+ C-CALCULATION 的「典型值断言」(通常/一般/常见/普遍)同规;用户
输入计算式 CALC 不受影响(设计边界)。普通无数字建议零触碰(N9/F3
回归锁)。

## 5. 基线债实现(全部确定性·无条件)

- **A 区间**:claim 区间→证据区间包含判定(共边值永不支持:5-10⊄3-5)
  ;单值↔证据区间双向(4∈3-5 ✓;8∉ ✗);标注锚冲突容忍证据区间。
- **B 单位**:锚词表 +倍/%/月/年/次/折;单位不匹配即不支持(10万≠10倍)。
- **C 产品身份**:渐进前缀变体名称匹配(后缀起重疾险/医疗险等 8 类·
  k=0..6 前缀)对 product_id 绑定证据;回指(该产品/这款)不受约束;
  **金标唯一行为 delta=N4-3 假支持被关闭**(SUPPORTED→UNSUPPORTED ✓)。
- **D 日期**:Y年M月D日整串感知(修 FIX2 边界正则对「年」后随月数字
  的误拒);日期任一分量交换→UNSUPPORTED;时点限定 claim(2023年的)
  =既有 as-of 设计边界(未实现脆弱启发·如实记录)。

## 6. product identity / date-time 处理边界

产品身份用现有 contract(product_id 元数据+catalog 解析+新名称变体)
——未重设计 catalog·未伪造 id(证据缺 product_id 时名称约束不启用=
fail-open 于「无绑定可验」·与现状一致)。日期:值交换全保护;元数据
日期入搜索域=**未实现**(C4 已否决域·防跨词界假阳性)——R5 时态扩展
另裁。

## 7. Tests（25/25 绿·覆盖 18 类×4 臂)

18 必含类全数落地;另含:OFF 等价(旗关=无新代码路径·行级标记零出现)
·env 覆盖与 kill-switch·缝双恒定(None 无路径/异常不改答案·run_qa_turn
实测)·判定客户端五类错误坍缩(provider/malformed/低置信→UNCERTAIN/
矛盾→KEEP_BASELINE)。**既有 Golden 全部只读**;F-1 基线在 C1/B 的
放行按臂如实断言(文档化·非放宽)。

## 8. Frozen Benchmark v2（经真实生产 check())

| 臂 | 逃逸 | 候选新增 | 关闭 | HARD_GATE |
|---|---|---:|---:|---|
| C1(含无条件债硬化) | 11(基线债使 13→11:F5-08+F6-08 关闭) | — | — | 基线 |
| B | 11 | **0** | 0 | **PASS** |
| D | 6 | **0** | **5**(F4 7→2) | **PASS** |
| BD | 6 | **0** | 5(B 收益 F3 4→6 叠加) | **PASS** |

残余 11/6(词法假支持 F1×2·方向 F2×1·F4×2[前提在证据·判定正确而
标签严]·F5×1[范围扩展])=语义层范围(S1' 轨道)·如实记录。

## 9. Full Regression（before/after/delta)

| 套件 | before | after | delta |
|---|---|---|---|
| FIX-3 新套件 | — | 25/25 | +25 |
| Claim Support 65-check | 65/65 | 65/65 | **0** |
| QA 流式/校准/送达(k22/k26/p28b51/delivery) | 36 | 36 | 0 |
| **全电池** | 870+2 | **895+2** | **+25·0 失败** |
| 金标 104(生产判定·HEAD vs 新) | — | **103 同/1 异=N4-3 修复** | Layer A 假支持 **-1**·Layer B 零附带移动 |

diff 审计(Phase 9):生产变更恰=授权三文件+新准备件;Intent/Router/
C2/WeKnora/Gate/K.26/server 零触碰(其余 M 文件=会话起始既有 span)。

## 10. Rollback Verification（自动化证明·非理论)

- 双旗 OFF→行级零新标记+判定逐位=C1(test_off_equivalence)
- env kill-switch 压 rules(test_rollback_env_off_beats_rules_on)
- B OFF=D OFF=C1;D OFF=B 保持(test 矩阵按臂断言)
- Judge 不可用→生产零影响(shadow_judge 不被生产 import·结构性)
- Shadow 不可用→生产零影响(observer=None 默认+异常吞噬·run_qa_turn
  实测答案不变)

## 11. S1' Readiness

**READY**(激活前置 1-9 全 DONE·10/11=Owner 批准与资源——见
k29c-fix3-s1-shadow-activation-readiness.md)。**本阶段未启动 Shadow。**

## 12. Remaining Blockers（全部 Owner 级·无工程 blocker)

1. OD-FIX3-5:judge 模型槽位/观察窗/每 run 预算/成本上限
2. S1' 启动批准(前置已绿·等待决策)
3. 范围扩展(F5-13 重疾→轻症)与元数据日期=语义层/R5 设计债(S1'
   观察范围·非本阶段)
4. 残余 F4×2(前提在证据·标签从严)=corpus-revision 候选议题
5. R4 路由面(OD-H3)与 F-1 的 C1 基线残留(未开 D 前)=灰度开启决策

## 13. Exact Next Owner Decision

**是否开启 B/D 生产灰度**(env EXEMPTION_V2_ENABLED/PREMISE_SCAN_
ENABLED·沿 CLAIM_SUPPORT_ENABLED S1 惯例·建议与 :8123 重启决策合并)
+ **S1' Shadow 启动与资源**(OD-FIX3-5) + span 续封(本阶段生产变更
  入 D-08 续封批次)。附注::8123 仍跑修复前码;.env 端点裁决(按量
  余额 0)仍在队列。

---

```
FINAL STATUS: PRODUCTION_IMPLEMENTATION_PASS
B+D production implementation = PASS
baseline debt                = PASS(金标唯一 delta=关闭 N4-3 假支持)
Frozen Benchmark             = PASS(三臂 HARD_GATE·候选新增逃逸 0)
full regression              = PASS(895+2·零新增失败)
rollback                     = PASS(自动化证明)
S1' Shadow readiness         = READY(未启动·待 Owner+资源)
Semantic Judge production authority = NOT GRANTED
Hybrid = OFF · S2 = unchanged · Batch-2 = not distributed
```
