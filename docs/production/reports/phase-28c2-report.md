# Phase 28.C-2 Report — Product QA Agent 最小生产闭环 + 28.B Readiness

Date: 2026-09-25 · 状态：COMPLETE（自主模式；STOP 规则零触发——ADR/
PRODUCT_VISION/Router 全局权威/orchestrator/artifact contracts/approval/
WeKnora 核心全部零改动，git 复核）。deliverables：
phase-28c2-pre-audit.md · phase-28b-readiness-audit.md · 本报告。

## 1. Completed work

### Step 0 Pre-audit（先于代码，phase-28c2-pre-audit.md）
五项检查 + 一处前置缺口发现（意图规则不识别目录产品名）+ STOP 规则
核验表（零触发）+ GO 判定。关键审计发现：目录 12 产品自带
`evidence_refs` 产品→知识链接（P001→01_medical_insurance.md）；
fixtures KB 为品类级知识（无产品条款文档）；"健康满分"不存在于 demo
目录（场景 A 以真实 P001 同形实现）。

### Step 1 共享模块抽取（>30% 重复触发）
- **NEW `runtime/grounding/`**：`gate.py`（引用闭环门，逐字搬移）·
  `context.py`（AnswerContext 构建+校验；增公共 `retrieval()` 包装与
  `product_ref` 透传）· `loop.py`（网关适配器/build_gateway 进程级
  单例/证据块/冲突并陈模板/**generate_grounded 共享尝试循环**：
  网关生成→门→一次再生成→拒答）。
- `runtime/qa_agent/{gate,context}.py` → **兼容 shim**（原 import 路径
  全保留）；`qa_agent/agent.py` 改调用共享 loop。**行为等价门**：
  C-1 的 16 测试原样全绿（未修改一行）。
- 非大规模重构：搬移+抽取，无行为变更。

### Step 2 Product QA Agent（NEW `runtime/product_qa_agent/`）
- `resolution.py`：产品解析（runtime/catalog_refs.py——确定性最长匹配，
  消息→上下文扫描；fail-quiet）+ **确定性目录记录锚点 E1**（版本钉死
  catalog_version@product_version、rendered_fields 只渲染存在字段、
  sha256 记录哈希、source_type=catalog）+ `qualifies()`（治理证据归属
  判定：evidence_refs 链接文档 **或** 内容点名产品——品类级泛知识不
  为具体产品补位）。
- `agent.py::run_product_qa_turn`：验证 IntentResult(product_qa) → 产品
  解析 → **KnowledgeService 必查**（不可用即 kb_unavailable，目录锚点
  不得绕行——K003）→ 证据组装（resolved: E1 目录+E2.. 合格治理证据；
  unresolved: 普通知识路径）→ **参数守卫（D6）**：所问参数在目录记录
  与合格证据中均无 → `catalog_missing_fact` 拒答 → 冲突并陈 → 共享
  loop。系统提示词硬禁：推荐/方案设计/保额计算/销售建议（结构上亦无
  任何工具可产出）。
- AnswerContext 全分支 schema-valid（闭合契约）；失败必 refused。

### Step 3 Router slice（spec 逐字执行）
`INSURANCE_AGENT_PRODUCT_QA_SLICE` **默认 OFF**（与 D4 的 knowledge-QA
slice 默认 ON 区分）；同缝接线（server.py `_pq_slice`）；全局 Router
权威未切换；`qa_answered` 事件 data 增 `slice: product-qa|knowledge-qa`；
shadow `actual_execution=insurance-qa-agent`（两行为同属 registry 条目
insurance-qa-agent——路由表不变）。

### 意图层信号演进（pre-audit §6 缺口修复）
classifier 增**目录名信号**：消息含目录产品全名/去括号基础名/P0xx →
specific-product 分支（reason `rule:product_qa_catalog_name:P0xx`）；
目录不可读→无信号→行为如旧。语料回归 22/22 不变；"百万医疗险是什么"
仍 insurance_qa（品类词非产品名，无假阳）。

### Step 4 测试（tests/runtime/test_p28c2_product_qa.py，15/15）
六强制场景 + 扩展（详见 §3）。

### Step 5 28.B readiness audit（phase-28b-readiness-audit.md，只读）
**NOT READY**：5 硬阻塞（web event contract 同步 / B4 行为等价门 /
ADR-025 / live shadow 校准 / planning 目标行为 28.D）+ 2 顺序依赖
（28.E card 键控、ADR-024 数据政策）。建议序：web 同步→B4→ADR-025→
切片流量校准→28.D→28.B 分段切换。零代码。

## 2. Architecture impact

- **Intent→Router→Agent 权威面扩至 product_qa**（flag 默认 OFF：灰度
  待授权开启）；其余意图路径逐字节不变；One Runtime（无新引擎/存储/
  注册表；Product QA 为 insurance-qa-agent 的行为单元，路由表零改动）。
- **Catalog 首次成为生产证据源**：确定性版本钉死记录作为 E1 证据锚点
  （查表事实 LLM 只转述；参数双缺即拒——D6）。
- **ADR-022 边界的实现解释**（pre-audit §7 记录）：产品参数问题
  catalog-first；缺口由**合格**条款证据（链接文档/点名产品）补足并须
  以"常见/一般"框定；泛知识不得为具体产品补位；双缺 fail-closed。
  未修改 ADR 文件。
- 事件契约：qa_answered data 增量字段（additive）；EVENT_TYPES 无新词。
- 意图层：新增确定性数据信号（版本化目录，只读缓存）——规则可回归。

## 3. Tests

- **Before：662 passed / 0 failed · After：677 passed / 0 failed
  （345.6s）**（662 + 新 15；`pytest tests/runtime tests/contract`）。
- 六强制场景：**A** 产品存在（P001 等待期）→ grounded（E1=catalog
  P001 版本钉死锚点 + E2=链接治理证据 + product_ref resolved）✅ ·
  **B** 产品不存在 → insufficient_evidence（resolved=False）✅ ·
  **C** WeKnora 不可用 → kb_unavailable（**目录锚点不得绕行**）✅ ·
  **D** LLM 不可用（timeout/500/429）→ llm_unavailable ✅ · **E** 无
  引用生成 → 门拒→再生成→citation_gate_rejected（attempts=2）+ 再生
  成成功路径 ✅ · **F** 产品问题不进 plan workflow（意图分类不落
  insurance_plan + 服务器 e2e：无 stage/planner/agent_step/tool 事件，
  qa_answered.slice=product-qa，run_dir 记录 schema-valid）✅。
- 扩展：目录参数转述 grounded（免赔额 10000元 constraints 真数据）；
  D6 参数双缺 fail-closed（P009 真数据）；指代后继上下文解析（P005
  via context）；flag 默认 OFF + OFF 时既有路径；shim 等价断言
  （qa_agent.gate.load_rules is grounding.gate.load_rules）；classifier
  目录名信号 + 语料 22/22；schema product_ref 契约（bogus matched_by
  拒、knowledge 记录无 product_ref 仍 valid）。
- 全离线（真实 demo 目录 + fixtures KB + MockLLM/FakeLLM）。

## 4. Changed files（28.C-2 增量）

**新增**：`runtime/grounding/{__init__,gate,context,loop}.py` ·
`runtime/product_qa_agent/{__init__,agent,resolution}.py` ·
`runtime/catalog_refs.py` · `config/product-qa-rules.yaml` ·
`tests/runtime/test_p28c2_product_qa.py` ·
`docs/production/reports/{phase-28c2-pre-audit,phase-28b-readiness-audit,
phase-28c2-report}.md`

**修改**：`runtime/qa_agent/{gate,context}.py`（→shim）·
`runtime/qa_agent/agent.py`（改用共享 loop，行为等价）·
`schema/qa-answer-context.schema.json`（additive optional：
anchor.source_type + 顶层 product_ref）·
`runtime/intent/classifier.py`（目录名信号）· `runtime/server.py`
（product_qa 切片分支 + slice 标识）· shadow 记录 actual_execution
两态

**git diff scope 复核**：tracked-modified = 会话起点既有 7 文件（本
阶段增量仅 events.py 无、server.py 切片段、无 test_agent_api 改动）；
knowledge/ · contracts/ · orchestrator/repair/eval_engine/evaluation/
**零改动**（git status 空确认）；web/** 零改动。

## 5. Known limitations

1. product_qa 切片默认 OFF——开启（灰度）需运营决策；开启后真实流量
   才积累 product-qa AnswerContext 审计数据。
2. 目录三缺依旧（waiting_period/exclusions/health_declaration 数据+
   schema，B3）：真实目录下多数专项参数问题将诚实 catalog_missing_
   fact；KB 需产品条款文档上传（运营项）才有专项可答。
3. 产品名匹配为全名/基础名/P0xx——短别名（"满分"）不识别（确定性
   优先，无模糊）。
4. unresolved 产品的指代追问依赖上下文扫描（8 轮窗口）。
5. 合格证据判定是确定性字符串规则——英文文档/改写名称不命中。
6. web 契约仍不同步（28.B 阻塞 B-1，决策记录在案）。

## 6. Next recommended phase

按 28.B readiness 建议序：**① web event contract 同步（小授权，含
web/**）→ ② B4 行为等价门 → ③ ADR-025 立案 → ④ 灰度开
INSURANCE_AGENT_PRODUCT_QA_SLICE=1 + 服务器重启积累切片流量与 HD-1
校准 → ⑤ 28.D planning 切片 → ⑥ 28.B 分段全量权威**。或按兵不动观察
QA 切片真实流量。

**STOP — 全部完成（C-2 实施+测试+28.B 审计）；未继续开发；等待人工
批准。**
