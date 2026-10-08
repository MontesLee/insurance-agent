# 28.K.28-II-DP · Production Decision Path Audit

Date: 2026-09-29 · Mode: **AUDIT ONLY**（零生产修改·新增仅测试代码
`tools/decision_path_e2e_audit.py`+observation JSON）·
**K.28-II-DP: PASS_WITH_FINDINGS（P0=0·P1=0·P2=2·P3=4）**

## 1. Actual Production Decision Graph（代码反建·file:line 锚定）

```
User Message（server.py:636 _recent 8 条上下文）
 ↓ C1 信号派生（server.py:645-660 同 chat 上 run WAITING_USER+plan）
 ↓ Intent 分类（classifier.py 规则 1-7+FIX A/B/C·SEALED）
 ↓ Router（router.py route·registry_lookup/fallback）
 ↓ Authority Staging Seam（server.py:700-760 authority_mode→
   _qa_slice/_pq_slice/_plan_slice/_unknown_governed 四路分发）
 ↓ [QA 路] Retrieval（build_evidence→治理 R1-R9）
 ↓        C2 Qualification（qa_agent/agent.py:177·SEALED）
 ↓        Conflict 分支（loop.py:212 conflict_answer 确定性 both-sides）
 ↓        Generation（generate_grounded·regen≤1）
 ↓        Segment Gate（loop.py _full_gate=citation∧claim_support·逐段）
 ↓        Final Gate（同判定·终局）
 ↓        [Claim Support（claim_support.py·SEALED@24082d5·S2 gray）]
 ↓ Streaming Delta（sanitize_consumer_text 逐 delta·K.26）
 ↓ Delivery/Refusal（_finish_run 卫生边界+固定拒答模板）
 ↓ [Legacy Agent 环]（slices 未 fired 时：tools→ask_user/finish/
   needs_review·K.24 deadline L1/L2 看门狗）
```

**UNDOCUMENTED_DECISION_POINT（在码不在任务清单·均已见于阶段
报告但非架构图正典）**：①Authority Staging 四路缝（28.C-1/M4/ADR-025）
②unknown_governed 治理接管缝（K.7）③conflict_answer 分支 ④per-segment
stream gate（K.26）⑤_finish_run 卫生边界（K.27-S1）⑥K.24 deadline
看门狗 ⑦legacy agent 环 STEP_LIMIT/needs_review 终态族。

## 2. Decision Point Inventory（§4 D1-D8 判据对照）

| 决策点 | D 判据 | 状态 | 证据 |
|---|---|---|---|
| Intent 分类 | D1 | SEALED | e306118·金标 95.9%·live |
| C1 信号派生+延续 | D1/D2 | SEALED | C1 12/12+live |
| Router lookup/fallback | D1 | SEALED（结构守卫） | E2E-02 |
| Authority/Slice 缝 | D1 | TESTED（部署模式相关·见 P2-1） | 代码+28.C/M4 |
| 治理 R1-R9（检索资格） | D4 | SEALED | Phase24+RV4-A |
| **C2 Qualification** | D4 | SEALED | k27rv4c2 8/8+live |
| Conflict 分支 | D5/D8 | TESTED | conflict_answer 确定性 |
| Claim Typing | D8 | TESTED | 48 检查·typing 94.2% |
| **Claim Support** | D8 | SEALED+FROZEN@S1 | 24082d5·gray |
| Citation Gate | D8 | SEALED（28.C-1） | gate.py+k22 |
| Regen 决策 | D5/D6 | TESTED | E2E-07（attempts=2 重过门） |
| Streaming Gate | D7 | SEALED（K.26） | E2E-15/16 |
| 拒答/交付 | D7 | TESTED | 固定模板+卫生层 |
| Legacy 环终态 | D5 | TESTED（K.24/K.1） | deadline+needs_review |
| Evidence→Context 映射 | D4 | TESTED | E2E-01（LLM-seen≡C2-set） |

## 3-4. Test Coverage + Production Results

- 既有：Intent 金标 224/电池 865+2/C2 8 节/K.26 6 节/Claim 48 检查
- **新增 E2E 决策链 16 类 + 故障注入 6 类（`tools/
  decision_path_e2e_audit.py`·零生产修改）→ 22/22 PASS**
  （E2E-01 全链 happy+**上下文一致性实证**·02 Router 风险+fallback·
  03 C1 失信号·04 错题检索→C2 拒·05 混合检索→支持层拒·06 C2 过→
  支持层拒（RV4-B 形）·07 regen 重过门后拒·08-10 切换/延续/歧义·
  11 错产品·12 过期·13 矛盾·14 空检索·15 支持流式 T_first=0.000s·
  16 未支持流式 **leak=0**；FI-1 无效 intent→invalid_input·FI-2
  clarify→fallback·FI-3 农业条例→C2 拒·FI-4 OFF 开关→旧路径·
  FI-5 regen 不可弱化·FI-6 拒答文案零内部件）

## 5. P1-P6 核心问题回答（§15）

| 问 | 回答 | 依据 |
|---|---|---|
| P1 Intent 对→错 Agent？ | **结构不可能**（registry 冻结表+启动校验+fallback；注入未声明 intent→conversation-agent） | E2E-02/FI-2 |
| P2 Intent+Agent 对→检索致错答？ | **两道后续防线**（C2 拒错题；支持层拒错主张）；残余=语义级（词法天花板·P2-2） | E2E-04/05/06 |
| P3 检索错→C2 未拦？ | 未观察到（agri live 0 qualified；错题全拒） | FI-3/E2E-04 |
| P4 C2 过→支持层未拦？ | 未观察到（RV4-B 形/E2E-06 live+offline） | E2E-06 |
| P5 Gate FAIL→regen 绕过？ | **不可能**（attempt-2 全门重判；attempts=2 实证；held 段仅在终门 PASS 后 flush） | E2E-07/FI-5 |
| P6 内部对→流式/交付泄漏？ | 未观察到（unsafe delta=0·sanitize 逐 delta·拒答模板固定·FI-6） | E2E-16/FI-6 |

## 6. Fault Injection 矩阵（§14）

| Injected Fault | First Detection | Containment | User-visible |
|---|---|---|---|
| 无效 intent | run_qa_turn 入口契约 | invalid_input 拒答 | 诚实拒答 ✓ |
| clarify intent | Router | fallback conversation-agent | 澄清 ✓ |
| 农业条例（RV4 查询） | C2 | 0 qualified | 诚实拒答 ✓ |
| 无关主张+[E1] | Claim Support | refused·delta=0 | 拒答 ✓ |
| 支持层 OFF | 开关 | 旧路径（授权回滚态） | 旧行为 ✓ |
| regen 同错 | Final Gate | 二次全门→拒 | 拒答 ✓ |

## 7. Findings

### P2-1（部署模式相关治理缝）
slices 模式（默认部署）下 `product_qa` 切片 DEFAULT OFF（28.C-2 设计
决策）→ product_qa intent 正确+Router 正确，但走 **legacy agent 环**
（工具路径·无 citation gate/claim support）。当前 pilot=full
authority（切片 fired·受治）；**部署模式回退到 slices 时该路暴露**。
→ Owner 决策项（启用 product-qa 切片或接受 legacy 环路径）。

### P2-2（语义支持天花板·已知沿袭）
词法支持层无法判定非字面语义支持/否定（shadow N8 族 67%）——
fail-closed 方向（误拒不逃逸）。沿 K.28-II 冻结限制。

### P3-1 per-claim support 行不持久化（S2-READINESS 已记）
### P3-2 拒答路径 gate_violations 不落（K.34 既有）
### P3-3 attempt-1 违规明细 [UNKNOWN]（RV4-B 时代记录）
### P3-4 legacy 环 LLM 调用不经网关（F2 观测缺口·K.12 记录沿袭）

**P0=0 · P1=0**：无「内部全对但用户见错」路径；无 regen 弱化；无
Intent-对-Agent-错结构缝。

## 8. Observability Gaps = P3-1..4（上）

## 9. Sealed Components Verification

Intent/C1/C2/K.26/Claim Support（24082d5）/D-08/OD-12——**零修改**
（HEAD=24082d5·staging 清零·本阶段新增仅 tools/ 测试+docs/报告+
tmp/obs 证据）。Planning=OFF·LLM Judge=OFF·Authority NOT GRANTED·
**S2 状态 UNCHANGED**（窗口仍待 Owner 分发起算）。

## 10. Recommended Next Actions（Owner·不自行执行）

① P2-1 部署模式裁决（slices 下 product_qa 路径）②P3-1 per-claim
持久化立项（与 S2 深审计协同）③P3-2/3 拒答可观测性 1-2 行项
④P3-4 legacy 环 F2 网关覆盖（沿 K.12 建议）⑤将本 E2E 22 项纳入
常规回归。

---

```
K.28-II-DP: PASS_WITH_FINDINGS
P0: 0 · P1: 0 · P2: 2 · P3: 4
No production logic changed. STOP.
```
