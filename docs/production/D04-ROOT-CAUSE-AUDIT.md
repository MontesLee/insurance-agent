# D-04 拒答根因审计 + 离线 Replay（DESIGN ONLY）

Date: 2026-10-05 · baseline: insurance-kb-v1 + BGE-M3（PRODUCTION_SWITCHED_AND_VERIFIED）·
Phase16 ARMED+OPEN（本审计零接触：authority 计数 0/0 未动·judge 调用全部离线·
ledger 独立路径 tmp/obs/d04_replay_ledger.jsonl）· 生产/安全层零改动

---

## 1. Executive Summary

**D-04（知识问答 ~9/10 拒答）的根因不是检索层——是答案侧的「词法支持天花板 ×
全有或全无门」合取**。BGE-M3 已把检索修到 R@10=100%，但最终答案的每一句都要过
确定性的词法 Claim Support；模型的多句答案几乎必然含有改写句（13 个全链 case 中
PARTIAL 违规 66 条 vs UNSUPPORTED 8 条），任一句失败 → 整题拒答。
**关键发现：13/13 个被拒草稿都含有可通过全门的「已验证子集」**——而该机制
（verified-subset delivery，FIX-3 Phase-14）**已在当前武装的生产 :8123 上启用**
（武装探针已实证交付）。「9/10 拒答」描述的是 sealed 基线/离线配置的形态；
**武装配置下该族群预期从全拒转为子集交付**（离线确定性模拟 13/13），真实值待
Phase16 真实流量测量。

## 2. 语料（31 case·30 拒答·≥20 达标）

- 来源: qa_slice_bgem3-migration（19·全链含草稿+逐句违规）+ prod_shadow_kb1
  （30·治理链·去重 18）· 全部 kb-v1+bge 2026-10-05
- 标记: **REAL 0 / PRODUCTION-LIKE 31 / SYNTHETIC 0**（窗口真实流量=0 如实；
  benchmark 冻结查询+自然措辞探针过完整生产链）
- CORPUS_ISSUE: 无（benchmark 锚点逐字在库）

## 3-4. 失败层分布（30 拒答）

| 类 | n | % | 说明 |
|---|---:|---:|---|
| R1 检索 | 3 | 10% | 全部=个性化口语问句（R01/R02/R04）·治理路径词法相关性地板放行 0；§8 口径下属正确拒答 |
| R2 资格 | 0 | 0% | C2 无失败（benchmark 语料） |
| R3 引用 | 2 | 6.7% | GEN-01/04：模型漏引（fact_sentence:no_citation）·证据在 |
| **R4 支持** | **19** | **63.3%** | **主因**——全链 13 case 违规构成 PARTIAL 66 / UNSUPPORTED 8 |
| R5 粒度 | 0 | 0% | — |
| R6 构造 | 0 | 0% | （R6 形态并入 R4 判定：hedged 元描述句本身也是 PARTIAL 被拒） |
| R7 正确拒答 | 5 | 16.7% | 5 负例（RB-N 族） |
| R8 未知 | 1 | 3.3% | llm_unavailable 供应商瞬态（不计 D-04 基数） |

## 5. BGE-M3 vs Nomic（同 query 双臂）

8 个 benchmark 同题双臂：期望文档 nomic rank 1-7 → bge rank 1-3（如 RB-L1-001
7→1），**终态除 RB-L1-019（门方差）外全部不变（双臂拒答）**；57-case 管线层
R@10 80%→100% 而 QA 终态不变。**§5 答案：存在「nomic 检索差/bge 检索好/仍拒答」
的形态，且它就是主导形态——证明拒答层在检索下游、与嵌入无关**。唯一双臂 ANSWER
= RB-L1-007（犹豫期）：恰好是草稿全句逐字可锚的短答案（旁证根因）。

## 6. Sufficiency Matrix

| Case 族 | Retrieval | C2 | Citation | Claim Support | Final | Root |
|---|---|---|---|---|---|---|
| benchmark 7 拒（L1-001/017/L2-001/L1-009/027/019/023） | ✓(rank1-3) | ✓ | ✓ | ✗ PARTIAL | REFUSAL | **R4** |
| GEN 5 拒 | ✓ | ✓ | 3✓/2✗ | ✗ PARTIAL 主 | REFUSAL | R4(3)/R3(2) |
| PROBE-CHILD-CI | ✓ | ✓ | ✓ | ✗ | REFUSAL | R4 |
| shadow R4 12 拒（治理链） | ✓ | ✓ | ✓ | ✗ | REFUSAL | R4 |
| shadow R1 3 拒（个性化） | ✗(allowed=0) | – | – | – | REFUSAL | R1（§8 正确拒答） |
| 负例 5 | ✗(无关) | 0 | – | – | REFUSAL | R7 |

## 7. SAFE vs UTILITY_FALSE_REFUSAL（30 拒答）

- **SAFE_REFUSAL = 8**：负例 5（R7）+ 个性化 3（§8「个性化推荐缺乏用户信息」；
  机制恰为相关性地板，结果正确）
- **UTILITY_FALSE_REFUSAL = 9（实证）**：benchmark 7 —— **最小引用答案测试
  7/7 双门全过**（「«fact»[E1]。」对真实证据可交付）+ R3 2（证据在·模型漏引）
- UTILITY_FALSE_REFUSAL（高度可能）= 12：其余 R4（证据在·PARTIAL 主导·GEN 宽问
  不适用最小测试）
- 供应商瞬态 1（R8）
- **§8 红线全守**：精确数字无法证实/医疗定义/法律结论缺原文等情形无一被计入
  false refusal（UNSUPPORTED 8 条全部维持拒答）

## 8. Root Cause（定论）

1. **主因 = D04-R4**：确定性词法支持判定无法验证「证据有据的改写句」（PARTIAL
   天花板·与 K.29-C 分类学 E=61% 一致）× **全有或全无整题门** → 整题拒答，
   尽管 13/13 草稿含已验证子集。
2. 次因：R3 模型漏引（2）· R1 治理相关性地板对口语/个性化措辞（3）。
3. 排除：检索（bge 已修·嵌入无关）·C2（0）·R5 粒度（0）·语料（0）。

## 9. 离线 Replay（D04-EVAL·13 D-04 case·全离线）

| Arm | 交付 | 说明 |
|---|---:|---|
| P0 现行政策（对照） | 0/13 | 复现生产拒答 ✓ |
| CA Phase16 authority 链（严格 v2 语义） | **0/13** | hard-class 墙（`\d` 正则覆盖一切数字/法规句）+ judge 保守 → 无法解锁数字-法规族；（宽松诊断口径 4/13 非真实策略） |
| CB 仅 prompt v5 模拟 | 1/13 | 生成已接近逐字+全引，仍被个别句拖垮 |
| **SD verified-subset（确定性）** | **13/13** | 原草稿逐句过滤+重组+重门全过（kept 1-4 句）·**= 当前武装运行时已启用的机制** |
| SD∘CB 组合 | 11/13 | 短答案反而偶尔整体失败（kept=0×2） |

**Unsafe answer（全部 arm）= 0**：SD 只保留逐句过门文本且重组后再过门；CA 的
judge/postgate 全部拦截；P0 拒答。安全面无任何放宽。

## 10-11. Candidate Fixes（不实现·Owner 决策）

### Candidate A（最小·实质=零新变更）
**保持武装配置的 verified-subset delivery（已 live·武装探针已实证）**，以
Phase16 真实流量测量真实 D-04 率。
- Expected utility: 全拒 → 子集交付主导（离线 13/13；信息量 1-4 句/题）
- Safety: 不变（只交付逐句过门内容·fail-closed·无规则放宽）
- Component: 无（env 已 on）；Regression: 无新增（Phase16 观察即回归）
- Rollback: env off；Risk: 低
### Candidate B（中等）prompt v5（逐字贴近+逐句引用）
- Replay: 单独 1/13；**与 SD 组合 11/13 < SD 单独 13/13** → 不建议单独立项
  （可能反降子集命中率；C-4A 负效先例）
- 若做: rules generation.qa_system_prompt（Owner 门）+ benchmark v2 复跑
### Candidate C（架构级）语义支持层（K.29-C Option C 线）/ 句级答案政策
- CA replay 证明对数字-法规族 +0（hard-class 墙=设计）→ 价值在非数字改写族
  （10-03 探针族）与长期句级政策统一；已有 OD 轨道（FIX-3 authority/k29c）
- Component: grounding 层·SEALED 面变更需专门 Owner Decision

**建议：A（现状测量）优先——Phase16 数据到手后再裁决 B/C。**

## 12. Production Change Proposal

无（本审计 DESIGN ONLY）。唯一隐含变更=维持武装配置（已有授权）。

## 13. Owner Decision

```
OWNER DECISION
[ ] A: 维持武装子集交付·以 Phase16 真实流量测量 D-04（推荐·零新变更）
[ ] B: 立项 prompt v5（弱证据·可能负效·需 benchmark v2）
[ ] C: 语义支持层/句级政策立项（架构级·SEALED 面）
[ ] 暂不决策（Phase16 结束后再议）
```

## 证据

`docs/knowledge-base/evidence/eval/{d04_corpus,d04_replay,d04_replay_cb,
d04_replay_sd}.json` + `tmp/obs/d04_replay_ledger.jsonl`（31 离线 judge 调用·
独立于 Phase16 配额）· 工具 `tools/embed_eval/d04_{build_corpus,replay,
cb_only,sd_sim}.py` · Phase16 隔离实证: authority 计数 0/0·kill ABSENT·
:8123 零接触·git tracked 基线不变

```text
FINAL STATUS: D04_ROOT_CAUSE_IDENTIFIED
```
