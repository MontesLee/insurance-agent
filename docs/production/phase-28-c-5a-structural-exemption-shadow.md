# Phase 28.C-5A · Deterministic Structural Exemption Shadow

Date: 2026-09-28 · SHADOW EXPERIMENT（生产 gate/prompt/model/marker/
runtime/KB/ADR 零改动·分类器为独立工具·零 LLM·确定性可复现）。

## Status

**SHADOW_READY**（40/40 全绿·双红线守住·C-4 语料回放完成·零生产变更）。

## 1. Shadow Classifier 设计

`tools/qa_structural_exemption_shadow.py`：
```text
gate 句 → \n 行级预切（解粘连）→ 逐行结构外壳剥离
（#/-/*/1./**label**/label：·循环至稳定）
→ 行判定：空|纯名词短语(≤16字且零谓词信号)|过渡模板|元叙述模板
  → STRUCTURAL；含谓词信号（数字或谓词/情态词表~60 项）→ FACTUAL
→ 句级：全部行 STRUCTURAL 才 EXEMPT；任一行 FACTUAL 即 MUST_CITE
```
保守偏置：未知长文本（>16 字无谓词命中）= FACTUAL；谓词优先于模板。

## 2. 40-Case Results

| 组 | 结果 |
|---|---|
| Positive（纯事实→MUST_CITE） | **10/10** |
| Negative（纯结构/过渡/元叙述→EXEMPT） | **10/10** |
| Mixed（结构+事实→MUST_CITE）🔴红线 | **10/10** |
| Adversarial（格式伪装→MUST_CITE）🔴红线 | **10/10** |

- Structural exemption **recall = 100%**（10/10 真结构被豁免）
- Structural exemption **precision = 100%**（全部豁免均为真结构）
- Mixed safety **10/10** · Adversarial safety **10/10**

## 3. 开发中实证发现的两处分类器缺陷（已修·留档）

①bold 剥离曾把 `**label：**` 后的 claim 整段丢弃（豁免了 mixed）——
**证明"剥离必须保留外壳后文本"是安全命门**；②封闭谓词表漏否定式
（`不影响理赔` 逃逸直至补 `影响`）——**封闭词表天然不完备**（残余
风险类：否定式/生僻谓词/隐含断言），即 C-5 方案 A 的固有边界。

## 4. C-4 Corpus Replay（只读·197 违规句）

```text
shadow 标记 STRUCTURAL_ONLY = 26/197 = 13.2%
```
**关键修正**：C-4 的"63% 结构类"按结构模式统计；shadow 按命题判定
后发现纯结构句仅 **13.2%**——大头是 \n 粘连的"标题+断言"混合句
（正确地不可豁免）。**结构豁免在真实数据上的天花板 ≈13%，而非 63%；
B 型 G-1 的主导杠杆仍是证据深度（C-3）。**
（不声称"gate 拒答率将下降 X%"——本阶段为 shadow，未做受控 E2E。）

## 5. Production Safety

Citation Gate/Prompt/Model/Marker/Runtime/KB/.env/ADR-022：
**全部 unchanged**（shadow 仅 import 现有模块读取·独立工具·数据落
tmp/obs/c5a_shadow.json）。

## 6. Conclusion

确定性"外壳剥离+空命题豁免"在 40-case 上**安全可行**（双红线 10/10），
且实施代价已知（谓词表维护+两处缺陷类教训）；但其真实数据收益上限
~13%（粘连混合句主导），应与 C-3 证据深度正交推进、按比例预期。

## 7. Recommendation（供 C-5 实施裁决参考）

若 Owner 批准 ADR-022 附裁决实施豁免：①以本 shadow 逻辑为基线②40-case
为强制回归门③谓词表进 gate rules 外置配置④上线前受控 E2E 实测真实
拒答率变化（本阶段未做）。与 C-3 解封的叠加顺序：C-3 先行（主杠杆）。
