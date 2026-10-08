# K.29-C FIX-3 · Phase 0 Architecture Audit — Claim Support 管线与插入点

Date: 2026-10-02 · Mode: **AUDIT ONLY**（零代码改动·本文件为产出之一）

---

## 1. 当前 Claim Support Pipeline（代码锚点·2026-10-02 实读）

```
答案文本（generate_grounded 的 attempt 输出 / K.26 流式的句段）
  ↓
[1] split_claims()                    claim_support.py:132
    句切分（gate.split_sentences·同 K.26 分段符）+ 确定性子句拆分
    （_CLAUSE_SPLIT_RE:，,、；;而且/并且/…）+ 逐子句：
      classify_claim(bare)            claim_support.py:97
      ★类型序：UNCERTAIN > REC > CALC > DERIVED > FACT > USER
      ★[E#] 标记在 typing 前剥离（模型行为非 claim 内容）
      numeric_anchors(bare)           claim_support.py:119（数字锚）
  ↓
[2] judge_claim(text, type, anchors, items)   claim_support.py:263
    a. 类型豁免：type ≠ C-FACT → NOT_APPLICABLE【F-1 缺口所在：
       REC 标记句整体豁免·句内数字前提不检查】
    b. 证据可用集：_in_window（时间窗 R5）+ _product_ok（产品身份
       product_id 绑定）                    claim_support.py:166/175
    c. 产品名剥离后重锚（数字入产品名不算断言）
    d. CONTRADICTED：标注锚在证据内取值冲突（≥2 值=证据矛盾；
       1 值≠claim 值=矛盾）            【仅数字锚·无否定语义】
    e. 有数字锚 → 逐锚 _value_found（FIX2 边界正则）全/部分/无
       = SUPPORTED / PARTIAL / UNSUPPORTED
    f. 无数字锚 → 定性 bigram 覆盖（_cjk_norm 双侧归一·FIX1）
       全覆盖=SUPPORTED·≥半=PARTIAL·<半=UNSUPPORTED
  ↓
[3] check(text, evidence, rules)      claim_support.py:343
    逐 claim 判定聚合：任一 C-FACT ≠ SUPPORTED → violations
    （enabled(rules)=false 时恒 ok——env CLAIM_SUPPORT_ENABLED/规则旗）
  ↓
[4] merge_verdict(citation_verdict, support_verdict)  :375
    与 ggate（引用存在性）合并——support 只收紧不放宽
  ↓
[5] 挂接点：loop.py _full_gate（终门+K.26 句段门共用）→ 拒/重生成
```

规则面:`config/qa-grounding-rules.yaml` `claim_support.enabled`
（**shipped OFF**·env CLAIM_SUPPORT_ENABLED=1 开启=生产 CURRENT_GRAY
S1 语义）;`gate.*`（引用存在性·fact-marker 词汇表）。

**封印谱系**（审计事实）：claim_support.py @ D-08-K28-II-CLAIM-SUPPORT
（24082d5·OD-12 基线 sha c28957d8）→ 其后 FIX2（数字边界·09-30·
授权+复验·工作树 sha add2cb71·待 span 续封）;loop.py @ 46dbe0f+
24082d5 → Phase-1 prompt 修复（10-02·未提交）。**当前工作树 = 封印
+FIX2+Phase-1 三层·全部已验证。**

## 2. 插入点分析（B/D·若 Owner 批准实施）

### Option B（C3v2 护栏豁免）

| 候选插入位 | 位置 | 评估 |
|---|---|---|
| **B-i（推荐）** | `check()` 聚合处：judge 后、violations 聚合前，对护栏命中的 claim 过滤违规 | **最小 diff**·不动 judge 语义·政策层实现（豁免本就是政策不是判定）;规则驱动（豁免清单外置 rules） |
| B-ii | `judge_claim()` 早期返回 EXEMPT | 改判定语义·影响 shadow/金标复用·不推荐 |
| B-iii | `loop.py _full_gate` 包装 | 触第二封印文件·不必要 |

B-i 细节：豁免判定 = 双护栏正则（META/GUIDE）∧ 零数字锚 ∧ NUM_RE
零命中 ∧（GUIDE 类加 HIGH_RISK 零命中）——与 K.29-C C3v2 重放实现
逐语义一致;`enabled` 之外新增独立规则旗（沿 staged 惯例默认 OFF）。

### Option D（建议句前提防御·F-1）

| 候选插入位 | 位置 | 评估 |
|---|---|---|
| **D-i（推荐）** | `check()` 循环内：type ∈ {C-RECOMMENDATION, C-UNCERTAIN} ∧ numeric_anchors(bare) 非空 → 该 claim 按 C-FACT 全规重判（前提即全句数字断言） | 最小 diff·**不拆文本**（拆分引入新边界面）·语义=「豁免失效于数字前提」 |
| D-ii | `classify_claim()` 改类型序（REC 前查锚） | 改全局 typing·波及 K.28-II 金标 114 例复用·不推荐 |

D-i 细节：重判失败（≠SUPPORTED）→ 该 claim 违规（fail-closed
方向保持）;纯建议句（零锚）不受影响（N9 族回归必须不变）。

### Option C（semantic shadow）——无生产插入点

Phase 0/C-shadow 全程**离线工具**（tools/·复用 K.29-C 重放机制）;
未来若 S1' in-process 影子才需 loop.py 观测缝（另行授权·本阶段
不存在）。见 k29c-semantic-shadow-design.md。

## 3. SEALED Boundary 清单

| 组件 | 封印 | B/D/C 触碰 | 需要什么 |
|---|---|---|---|
| `runtime/grounding/claim_support.py` | D-08 @24082d5（+FIX2 已验证层） | **B-i/D-i 修改** | **Owner 解封授权**（FIX-3-IMPL 立项） |
| `runtime/grounding/loop.py` | 46dbe0f+24082d5（+Phase-1 已验证层） | 不触碰（B-iii 已排除） | — |
| `runtime/grounding/gate.py`（ggate） | 引用存在性层 | **零触碰**（B/D 均不动引用门） | — |
| `config/qa-grounding-rules.yaml` | OD-12 基线件（sha 258950b5） | 新增 claim_support 子旗（B/D 各一） | 随 FIX-3-IMPL 授权·默认 OFF |
| Intent/C1/C2/Router/WeKnora | 各自 SEALED | 零触碰 | — |
| `tests/golden/claim-evidence-shadow.v1.json` | 冻结语料 | **只读**（重放） | — |
| Hybrid/S2 | OFF/OPEN-UNSTARTED | 零触碰 | — |

## 4. OD-12 授权路径（B/D 若实施）

任何 claim_support 行为变更须走 OD-12 三层 Gate（已冻结框架）：

- **Layer A 硬安全**：A1-A6 任一触发=BLOCK（FR/Escape 分级冻结值
  =OD12_BASELINE：FP=5·Escape=0·P/R 0.80/0.80·流式契约·泄漏 0）。
  B/D 的验收硬门：金标攻击面（含 v2 六族）新逃逸=0;F2/F4/F5/F6
  100% 拒;R3/R4 benchmark 面 0 数字/产品逃逸。
- **Layer B 质量**：金标 P/R 不降（C-FACT 判定不变·预期逐位一致）;
  E 类接受增量=would-flip 报告。
- **Layer C 运营**：env/规则旗默认 OFF·回滚=关旗逐字节回 C1
  （FIX1/FIX2 先例）·per-run 审计可区分旧行为。
- 状态机：S0 离线重放 → S1 in-process 灰度 → S2 Owner 复验 →
  S3（数值不自定·Owner 批准）。
- **封印簿记**：FIX-3-IMPL 完成后 claim_support.py 进 D-08 续封
  span（与 FIX2/Phase-1 同批或分批=Owner 选择）。

## 5. 结论

- B/D 各有一个**最小插入点**（均在 claim_support.py `check()` 内·
  政策层·不动 judge 语义·不动 ggate·不动 loop.py）。
- 两者都触碰 SEALED 文件 → **实施前必须 Owner 解封授权**
  （=Owner Decision v2 的 Decision 1）。
- C-shadow Phase 0 无生产接触面（纯工具）——但其 S1' in-process
  形态将来需要 loop.py 观测缝=独立授权（Decision 2 只授权「准备」）。
- 无任何发现迫使本阶段修改生产——**Phase 0 维持零改动。**
