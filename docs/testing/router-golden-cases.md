# Router Golden Case Inventory — B4 等价门输入清单

Date: 2026-09-25 · 性质：**清单 only，不执行**（Phase 28.B3 Step 3）。
用途：B4 行为等价门（router-equivalence-gate-design.md）的 golden 输入
集合。等价类：**E1**=字节级（planning 类路径复用）；**E2**=契约级
（QA 类新路径）。全部 case 状态 **PENDING_CAPTURE**（基线采集=未来
授权项；本阶段零执行）。

夹具约定（全部 case 共用）：KNOWLEDGE_PROVIDER=mock（fixtures KB+治理）
· catalog=demo 12 产品 · scripted provider（FakeLLM/MockLLM）· 时钟与
目录注入 · 离线无网络。

## 1. insurance_qa（E2 · 契约级）

| id | 输入（message / context） | 期望意图（依据） | 期望路由 | 两侧期望 |
|---|---|---|---|---|
| GC-QA-01 | "百万医疗险是什么" | insurance_qa（rule:qa:百万医疗险） | registry_lookup→insurance-qa-agent | off：chat agent 自由答；on：grounded（fixtures 证据+引用）或诚实拒答 |
| GC-QA-02 | "重疾险和百万医疗险有什么区别" | insurance_qa（definition:区别） | 同上 | on 侧必须 cited⊆evidence；E2-C5 全不变量 |
| GC-QA-03 | "等待期是什么意思" | insurance_qa | 同上 | 概念题→知识证据 |
| GC-QA-04 | "给孩子买重疾险前应该先考虑什么" | insurance_qa（guidance≠plan，A-1 精化） | 同上 | 防 plan 误路由负向锚 |
| GC-QA-05 | "有个事儿想问下"（LLM candidate 关） | unknown→澄清 | fallback→conversation-agent | 无规则命中且无 candidate=澄清，不猜 |

## 2. product_qa（E2 · 契约级）

| id | 输入 | 期望意图 | 期望路由 | 两侧期望 |
|---|---|---|---|---|
| GC-PQ-01 | "demo-百万医疗险A的等待期多久" | product_qa（rule:product_qa_catalog_name:P001） | registry_lookup→insurance-qa-agent | on：E1 目录锚点+链接证据 grounded（"常见30天"框定+目录缺口明示） |
| GC-PQ-02 | "P001是什么产品" | product_qa（product_id_pattern） | 同上 | 目录记录转述 |
| GC-PQ-03 | "demo-百万医疗险A的免赔额是多少" | product_qa | 同上 | constraints 真值 10000元 转述（E1 锚点独证可 grounded） |
| GC-PQ-04 | "demo-综合意外险A的等待期多久" | product_qa | 同上 | **D6 负向**：双缺→catalog_missing_fact 拒答 |
| GC-PQ-05 | "长生不老保XYZ这个产品怎么样" | product_qa（evaluative+anchor） | 同上 | 解析失败→insufficient_evidence |
| GC-PQ-06 | "那款怎么样" / ctx=["我想了解demo-重疾险B（终身）"] | product_qa（ctx 锚点继承） | 同上 | product_ref.matched_by=context_product_name（P005） |
| GC-PQ-07 | "这款产品值得买吗" | product_qa（evaluative+产品锚） | 同上 | 事实转述；**不含推荐话术**（禁售边界负向锚：输出不得出现购买建议——脚本注入诱导亦须被 prompt+门拦） |

## 3. insurance_plan（E1 · 字节级——M3/28.D 生效后适用）

| id | 输入 / seeds | 期望意图 | 期望路由 | 两侧期望 |
|---|---|---|---|---|
| GC-PL-01 | "夫妻35岁，一个孩子，帮我规划保险" / 家庭 seeds（FakeLLM 全链脚本：profile→requirement→risk→gap→solution→recommend→report→finish） | insurance_plan | registry_lookup→insurance-planning-agent | **artifacts/evals 逐字节等价**；事件归一化序列等价；风险信号集合相等 |
| GC-PL-02 | "家里有房贷200万，年收入50万，怎么做保障方案" / 同上脚本族 | insurance_plan | 同上 | 同 GC-PL-01 |
| GC-PL-03 | "帮我给孩子买保险，预算一万以内" / 儿童 seeds | insurance_plan（plan signal+ctx） | 同上 | 同上；防 qa 误路由 |
| GC-PL-04 | "35岁买保险，预算1万，担心住院。" / bm-complete 式 | insurance_plan | 同上 | 与既有 agent-api 全链用例同形（复用其脚本资产） |
| GC-PL-05 | "给我演示一下完整分析流程" / bm-complete-001（管线 seeds 直跑） | insurance_plan | 同上 | orchestrator 脊柱不变性锚：on/off 两侧都须经同一 8 阶段 |

## 4. modify_existing_plan（E1·澄清承接段——ADR-024 continuation BLOCKED 期间）

| id | 输入 / context | 期望意图 | 期望路由 | 两侧期望 |
|---|---|---|---|---|
| GC-MD-01 | "把保额调整到30万"（无 case 上下文） | modify_existing_plan + clarification_required（M1） | fallback→conversation/planning 澄清 | on：澄清承接（不建新 case、不 continuation）；off：chat agent ask_user——E2 化比较（澄清形态），continuation 等价待 ADR-024 解封后补案 |
| GC-MD-02 | "方案里的医疗险换成另一款" / ctx 同 GC-MD-01 | 同上 | 同上 | 同上 |
| GC-MD-03 | "把刚才孩子的重疾险保额从50万改成30万" | 同上 | 同上 | 长句变体；M1 fail-closed 不变 |

## 5. unknown（E2 · 兜底安全）

| id | 输入 | 期望意图 | 期望路由 | 两侧期望 |
|---|---|---|---|---|
| GC-UN-01 | "今天天气怎么样，适合出去玩吗" | unknown（无锚 evaluative 降级） | fallback→conversation-agent | 澄清/礼貌拒答；**绝不**业务 agent |
| GC-UN-02 | "帮我写一首诗" | unknown | 同上 | 同上 |
| GC-UN-03 | "你好" | unknown | 同上 | 寒暄承接 |
| GC-UN-04 | "asdfghjkl zxcvbn" | unknown | 同上 | 噪声输入安全降级 |
| GC-UN-05 | "1+1等于几" | unknown（A-1 用例） | 同上 | 非保险域拒答 |

## 6. 汇总与覆盖矩阵

- 共 **25 案**：insurance_qa 5 · product_qa 7 · insurance_plan 5 ·
  modify 3 · unknown 5。
- 覆盖矩阵（路由目标×等价类）：qa-agent(E2) 12 · planning-agent(E1) 5 ·
  澄清承接(E2/澄清段) 3 · conversation 兜底(E2) 5。
- 负向锚（安全门）：D6 双缺（PQ-04）· 无证据拒答（QA 类各案 E2-C5）·
  幻觉注入（B4 设计 §3 C-5：scripted 无引/伪引答案必拒——套用到 QA/PQ
  全部 on-side 案）· 禁售边界（PQ-07）· 兜底不落业务（UN 全）·
  fail-closed 澄清（MD 全）。
- 与语料关系：13/22 corpus 消息已映射入本清单（分类期望经 28.A-1
  语料验证）；plan 族新增 seeds/脚本维度（E1 需要）。

## 7. 采集与维护纪律（未来执行时）

1. 采集前自等价双跑（工具自检）；2. E1 基线落盘快照（sha256 指纹）+
   prompts.py planning 段冻结；3. 清单变更走 git review（新增/修改
   case = 代码级变更）；4. 每阶段 B4 报告引用本清单版本（git sha）。

---

## 8. Implemented runnable set（Phase 28.B4 · 已实现并纳入 CI）

`tests/golden/router_cases.json`（受 `schema/router-golden-case.schema.json`
契约校验）承载 **14 个可执行案**，由 `runtime/evaluation/router_equivalence`
B4 门双跑（legacy=全切片 OFF vs candidate=案载 flags）判定，pytest 常驻
（`tests/runtime/test_p28b4_gate.py::test_b4_gate_all_cases_pass`）。等价
报告：`docs/production/reports/router-equivalence-report.md`（当前
**14/14 PASS, 0 RED**）。

| case id | intent | 等价类/型 | 期望行为 | fixture source |
|---|---|---|---|---|
| GC-QA-G01 | insurance_qa | E2 grounded_answer | grounded（引用闭环） | fixtures KB 02 + 脚本引用答案 |
| GC-QA-G02 | insurance_qa | E2 insufficient_evidence | refused/insufficient | 无命中问题 |
| GC-QA-G03 | insurance_qa | E2 kb_unavailable | refused/kb_unavailable | 注入 dead provider |
| GC-QA-G04 | insurance_qa | E2 llm_unavailable | refused/llm_unavailable | 脚本 provider 故障（经网关） |
| GC-QA-G05 | insurance_qa | E2 hallucinated_citation | refused/citation_gate_rejected（安全探针） | 无据事实+伪引 [E9]×2 次尝试 |
| GC-PQ-G01 | product_qa | E2 product_existing | grounded+P001 | 目录 P001+链接文档 01 |
| GC-PQ-G02 | product_qa | E2 product_missing | refused/insufficient | 不可解析产品 |
| GC-PQ-G03 | product_qa | E2 d6_missing_fact | refused/catalog_missing_fact+P009 | 目录 P009（参数双缺） |
| GC-PQ-G04 | product_qa | E2 context_reference | grounded+P005（ctx 解析） | 上下文 P005+链接文档 02 |
| GC-PQ-G05 | product_qa | E2 forbidden_recommendation | refused/citation_gate_rejected（安全探针） | 无据推销话术 |
| GC-PL-G01 | insurance_plan | E1 plan_artifact_equality | 归一化逐字节等价（9 artifacts/事件链） | agent-api 全链脚本资产 |
| GC-PL-G02 | insurance_plan | E1 plan_preserve | 双 QA flag 开仍走 legacy（隔离） | ask_user 脚本 |
| GC-MD-G01 | modify | E2 clarification | M1 澄清（无 case） | A-1 语料用例 |
| GC-UN-G01 | unknown | E2 safe_fallback | conversation 兜底，绝不业务 agent | A-1 语料用例 |

设计清单 §1-7 中其余 11 案保留为 **M3 扩充位**（planning 切片落地后
E1 实义化）。已知纪律：脚本耗尽后 FakeLLM 返回中性文本——安全探针案
必须显式提供两次失败脚本；B4 runner 强制 `INSURANCE_AGENT_NO_DOTENV=1`
（hermetic，防 .env 的 LLM_FAST_MODEL 以 live 模型替换脚本）。
