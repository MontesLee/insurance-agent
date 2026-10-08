# D-04 Citation Calibration：儿童重疾险案例引用校准

Date: 2026-10-01 · Mode: 自主执行 Phase A-G · **Verdict:
D04_MODEL_LIMITATION**（含真实 C6 安全成分——拒答正确·不得放宽）
· 净变更=零（prompt 试改已回退·sealed 工件逐字节复原）

## 1. Verdict

**D04_MODEL_LIMITATION**——「Qualified Evidence → 正确引用 → Gate
PASS → 正常回答」链的当前阻断层=**模型能力**：glm-5.3 与
glm-5.3-flash 在长篇中文消费答案上均持续产出 1-5 句/次的未引用句，
其中部分句**确属证据外的通用建议**（拒答=正确安全行为）。

## 2. Root Cause（多类复合·证据在案）

| 类 | 判定 | 证据 |
|---|---|---|
| **C5 模型能力（主）** | 确认 | 同问同证据双模型 N=3：flash 拒 3/3（未引用 3/3/4）·**主模型 glm-5.3 拒 3/3（5/1/1）**——主模型也不达标；且两模型最佳 run 均只差 1 句 |
| **C6 正确安全拒答（次）** | 确认 | 残余单句阻断解剖：主模型 run3 唯一未引用句=「**先保障家庭经济支柱、再保障孩子，是常见的配置思路**」——**不在任何证据中**（模型自行补充的行业常识）→ 拒答正确 |
| C1 prompt（微） | 确认但不可修 | 主导残余形态=「因此…」推导句复述已引用事实但不重复 [E#]；prompt v4 加法式补丁（碎片/小结/因此句必须引用+删句规则）实测 **3/3 仍拒（3/1/5 vs 基线 3/3/4）**——N=3 无显著效益 → 已回退 |
| C4 门校准（边际） | 量化否决 | 纯结构壳（「## 3. 保额怎么定」类）仅占残余少数，且 C-5A 影子已证豁免天花板 13.2%；本日残余主形态=内容句非结构壳；即使实施 C-5A 豁免（Owner 未选型）也翻不了任何一 run |
| C3 parser | 排除 | 逐句解剖证明 [E1] 提取正确；违规句确无引用 |
| C2 evidence presentation | 排除 | 证据块格式正常·模型大量正确引用（多数事实句带 [E1]） |

**分层验证**（架构按设计工作）：引用门=存在性层（cited-but-
unsupported「分红率百分之十[E1]」过门 ✓ 按设计）；**Claim Support=
支持性层**（同句判 UNSUPPORTED→拒 ✓）。Citation ≠ Claim Support
边界保持。

## 3. Before / After（Case 7 儿童重疾）

```
Before（28.C-3 复验封存）:  Qualified=1 · GLM generated · Citation 缺失 · Gate REFUSE
本日基线（flash N=3）:      3/3 REFUSED · 终稿未引用 3/3/4 句
Prompt v4 后（flash N=3）:   3/3 REFUSED · 3/1/5 句（无显著改善→已回退）
主模型（glm-5.3 N=3）:       3/3 REFUSED · 5/1/1 句
After（净零变更·live 终验）:  Qualified=1 ✓ · hits=1 ✓ · attempts=2 ✓
                             · no_citation×4 · QA_REFUSED（诚实拒答）
结论: 知识链已恢复（C-3 成果）；回答产出被引用纪律正确阻断 =
     G-2/D-04 债的真实形态=模型引用纪律 × 长篇答案形态
```

## 4. Code Changes

**零净变更**。试改 `config/qa-grounding-rules.yaml` qa_system_prompt
（+4 行加法式）→ 无效益 → 回退；**sealed 工件逐字节复原**（工作树
sha 258950b5 == 24082d5 blob CRLF 归一后逐字节相等·实证）。未触碰
gate.py/loop.py/claim_support/任何代码。

## 5. Regression

```
D-04 tests:          确定性安全校准 6/6（门层：数字引用✓未引用拒✓多证映射✓
                     错标拒✓无引用拒✓；cited-but-unsupported 按分层设计
                     由 Claim Support 拒——支持层验证 UNSUPPORTED→拒 ✓）
Claim Support:       65/65（电池内）· C2: 8/8 · Intent: 12/12 · K.26: 6/6
Full regression:    865 passed / 0 failed / 2 skipped（零净变更确认）
```

## 6. Production Impact

安全边界**零变化**·Claim Support authority 零变化·C2/Intent/K.29/
S2/WeKnora 架构零变化。拒答行为=既有 fail-closed 语义。

## 7. Next Step（按 D04_MODEL_LIMITATION 路线）

- **保留安全拒答，不放宽任何门**（本任务红线）。
- 问题转入 **K.29-B benchmark / model-capability track**：引用纪律应
  作为 benchmark 维度（G 类幻觉专项）；可能的 Owner 杠杆=①QA 生成
  模型选型（主/flash 均未达标——需更强模型或更短答案形态约束的
  受控实验）②28.C-5 结构豁免轨道（Owner 选型悬置中·对本案增益
  ≤13%）③K.29 MODE-B 混合回答（general 段免引用+边界声明——正
  是该设计的用例）④B4/B5.1 式影子再校准（投入产出比待 Owner 评估）。
- **推荐主序**：Batch-2 UAT 可行（拒答=安全正确行为·用户感知为
  诚实拒答）；K.29-B 保持未启动（Owner 决策）。
