# Phase 28.C-4A · Answer-Shape Prompt Shadow

Date: 2026-09-28 · SHADOW EXPERIMENT（10 次生成·生产零改动·prompt 文件
未动——变体仅存在于请求层·同问同 evidence 双臂）。

## Status

**28.C-4A PROMPT_EFFECT_NOT_ESTABLISHED**（实测为**负向**：形态约束使
违规不降反升——比"无变化"更强的反证）。

## 1. Hypothesis

仅约束答案形态（禁 markdown 标题/分节/元叙述·引用规则不变）可显著
减少结构句违规（C-4 测得 63% 结构句）。

## 2. Experimental Design

C-4 同一 5 问；每问检索**一次**、同一 evidence 双臂复用（检索方差归零）；
唯一变量=system prompt 尾部追加形态约束（tools/qa_answer_shape_shadow.py）。

## 3. Controlled Variables

同 question/evidence/model（glm-5.3-flash 固定）/effort/gateway/gate
（原样委托）/retry/max output ✓。模型采样方差仍在（n=1/臂/问·工程影子
非统计结论）。

## 4-5. Arm A（现行 prompt） vs Arm B（+形态约束）

```text
Arm A: total=158  structural=128  拒答 4/5（1 问 grounded）
Arm B: total=204  structural=168  拒答 5/5
逐问：5/5 问 Arm B 违规数均 ≥ Arm A（40→54·30→42·32→35·28→35·28→38）
```

## 6. Per-Question Results

见 tmp/obs/c4a_shadow.json（每问双臂全指标）。注意 Arm A Q1（免赔额题）
本轮 grounded 而 C-4 轮 refused——跨轮采样方差实证（本轮检索与 C-4 轮
独立；臂内对照仍有效）。

## 7. V2 Structural Violations

128→168（**+31%·反向**）。模型未遵守负向形态指令，且约束文本疑似诱发
更多元叙述（"按照要求…"类自述本身落入结构/元句域）。

## 8. Total Citation Violations

158→204（+29%）。

## 9. Gate Results

拒答率 80%→100%。Gate 原样执行（包装委托·结果逐字节一致）——B 的恶化
不可能来自 gate 变化。

## 10. Evidence-Depth Interaction

ev≤1 的 3 问在两臂都贡献最高违规（与 C-4 一致）——证据深度仍是主耦合
因子；形态约束未改善该维度。

## 11. Tradeoffs

无正向权衡可言：结构违规、总违规、拒答率三项全恶化；grounded 通过
（A 臂 Q1）在 B 臂消失。

## 12. Conclusion

**朴素追加式形态约束在 glm-5.3-flash 上无效且有害**（负向证据·n=5）。
C-4 决策候选①的"prompt 禁结构"路径被本实验削弱；"gate 结构句豁免
（markdown 非散文事实句）"路径成为候选①的更强形态（仍需 Owner +
ADR-022 裁决）。证据深度（28.C-3 解封）权重进一步上升。

## 13. Production Impact

**NONE**（prompt/gate/markers/runtime/KB/模型零改动；实验仅
tools/qa_answer_shape_shadow.py + tmp/obs/c4a_shadow.json）。

## 14. Recommendation

①优先推进 28.C-3 KB 解封（ev 深度=两实验共证主因子）②若仍需消解结构
句：走 gate 结构句豁免设计评审（ADR-022 语义裁决·不再尝试朴素 prompt
约束）③QA 模型档位对比（flashx 对指令遵循度可能不同·独立实验）。
