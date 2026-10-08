# Single-Case Diagnosis — 儿童重疾险配置前考虑事项（只诊断·零修改）

Date: 2026-09-30 · 真实用户消息：「给孩子配置重疾险前，我应该先考虑
什么？」· 用户可见回答：「知识库暂无可靠依据，暂时无法回答这个
问题。您可以换个说法再问，或稍后再试。」

## 1. Intent（真实 shadow 记录）

- **实际 Intent = `insurance_qa`**（conf 1.0·src=rule）
- 命中原因（deterministic）：`rule:qa:重疾险`（名词信号）
- **LLM candidate：未参与**（`INSURANCE_AGENT_INTENT_LLM`=OFF·
  confidence_source=rule）
- Authority label：deterministic resolver（唯一 authority）
- Planning↔QA 边界：无歧义残留——该消息含 plan 信号「配置」+问句
  形式「什么」，FIX-A 问句保护（e306118 封印）正确抑制 plan 名词
  （无 怎么/如何 邻接·无 帮我/请 祈使·无建议类词）→落规则 5 qa。
  **与封金黄标 S1-QA-14（「给孩子买重疾险前应该先考虑什么」=
  insurance_qa·"guidance example"）完全一致**。

## 2. Router

```
insurance_qa → route() registry_lookup → insurance-qa-agent
→ knowledge-qa slice（fired=True·reason=authority·灰度 full）
```

## 3. Retrieval（真实 WeKnora·live 复检）

- query=原文（qa_agent:95 直传）
- **raw provider 结果（治理前）：status=`insufficient_evidence`·
  hits=0·reason="No sufficiently relevant knowledge was retrieved"**
- 语义近邻对照（live）：「儿童重疾险怎么选」「少儿重疾险投保注意
  事项」「重疾险投保前注意事项」→ **全部 0 hits**
- 对照组（同库可命中）：「健康保险产品的等待期…」→ 3 hits ✓
  （检索机制正常——是内容不存在，不是检索坏了）
- **insurance-pilot-2 KB=10 部监管法规**（农业保险/医疗基金/交强
  /反欺诈/消费者保护/披露/健康险办法/医院/互联网保险/药房）——
  **无一覆盖儿童重疾配置考虑事项**

## 4. C2 Evidence Qualification

```
RetrievedEvidence = 0（raw provider 0 hits——治理层收到的就是空）
QualifiedEvidence = 0（C2 从未收到任何 item 可裁）
RejectedEvidence  = 0（无被拒项——非 C2 过滤所致）
```
governed_status=`insufficient_evidence`（service.py:353·检索层
即空）。**拒答发生在 C2 之前**。

## 5. Claim Support

**未进入**（generation_provenance=`(not-attempted)`·attempts=0·
gateway=false）——本次拒答发生在 Claim Support 之前。

## 6. Final Refusal 触发点

**Retrieval 层**（WeKnora 0 命中→build_evidence 空→qa_agent
`insufficient_evidence` 既有诚实拒答·run `run_4914b16944a44d88`
AnswerContext 全证）。

## 7. 判定：**A. 知识库覆盖不足**

（非 B/C/D/E/F/G/H/I——逐项排除：Intent=封金一致✓·Router=正确✓·
Retrieval=对**不存在的内容**零召回（对照组证明机制正常）✓·C2 未
参与✓·Claim Support 未参与✓·Generation/Gate 未参与✓）

## 8. Planning 边界判断

按冻结 taxonomy（ADR-019 + S1-QA-14 封金先例 + FIX-A 问句保护
设计注释「给孩子买重疾险前应该先考虑什么 is guidance」）：**=
insurance_qa**（guidance/概念问句·配置为名词性话题非动作请求）。
当前系统行为**符合**现有定义。（若 Owner 认为应入 planning=
既有 GOLD_UNCERTAIN 张力族 03/07/10 同域——非本 case 的实际行为
偏差。）注：K.12 首真人 run_50389328 同源问法曾判 plan
（rule:plan:保障 命中·彼消息含 保障）——FIX-A 上线后此类
「plan 名词+问句」已按封金语义稳定落 qa。

## 9. 结论

```
CASE = 儿童重疾险配置前考虑事项

ACTUAL PATH =
Intent:         insurance_qa（rule:qa:重疾险·conf1.0·LLM 未参与·=封金 S1-QA-14 语义）
Router:         registry_lookup → insurance-qa-agent
Agent:          knowledge-qa slice（fired·authority）
Workflow:       检索→C2→（空）→诚实拒答
Retrieval:      WeKnora raw 0 hits（insufficient_evidence·近邻全 0·对照组 3 hits 机制正常）
C2:             未收到任何 item（0 in/0 qualified/0 rejected）
Claim Support:  未进入（attempts=0）
Final Gate:     N/A（拒答于生成前）

ROOT CAUSE = A（知识库覆盖不足）

PRIMARY CAUSE   = KB 无儿童重疾/投保考虑事项内容（pilot KB=10 部法规·无一覆盖）
SECONDARY CAUSE = 仓库内既有权威语料未接入——domain/insurance/references/
                  7 篇（00 产品分类/01 百万医疗/**02 重疾**/03 意外/04 寿险/
                  05 健康核保…）在库未入 KB = 既有 28.C-3 BLOCKED@JWT
                  （runbook 就绪·待 INSURANCE_AGENT_WEKNORA_JWT env）

KNOWLEDGE GAP = YES（且修复材料已在仓库·卡在 28.C-3 解封）
INTENT GAP    = NO（行为=封金定义）
RETRIEVAL GAP = NO（对不存在内容零召回=正确；机制由对照组证明正常）

PRODUCTION BUG = NO（全链各层行为均符合冻结契约·拒答=正确 fail-closed）

RECOMMENDATION =
下一步（Owner 决策·零修改）：解封 28.C-3（在启动会话的终端设
INSURANCE_AGENT_WEKNORA_JWT 后执行既有 ingest runbook·将
domain/insurance/references/ 7 篇按既有治理管道入库）——该语料
含 02 重疾 专篇，预期直接覆盖本类问法；入库后以本 case 原文+
近邻三问复测（C-3 报告已附复测程序）。不解封则本类「儿童/配置
前考虑」问法将继续诚实拒答（安全方向·无误答风险）。
```

证据：`tmp/webui-runs/run_4914b16944a44d88/qa-answer-context.json`
+ shadow 记录×2 + live 复检（raw provider/近邻/对照组）+
`domain/insurance/references/` 目录清点。

**STOP**（零生产修改·零语料修改·零 fake evidence）。
