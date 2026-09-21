# Insurance Agent — 证据接地的 Agent 运行时

> 语言：中文 | [English](README.md)

**一个证据接地的保险 Agent 运行时：把 LLM 推理与确定性的治理、
溯源和评估分离开来。**

```text
传统 LLM 应用：     用户 → LLM → 回答

本运行时：          用户 → Agent 运行时 → Skill → 知识
                    → 治理 → 证据 → 溯源
                    → 决策 → 报告
```

| | |
|---|---|
| 运行时测试 | 474 PASS |
| Benchmark | 42/42（无依据结论率 = 0） |
| 对抗性测试 | 42/42 |
| Live WeKnora 检索 | PASS（v0.8.0，真实 HTTP） |
| 全量回归 | 51 套件，0 FAIL |
| 变异测试 | 26/26（评估器能捕获注入缺陷） |

---

## 为什么做这个项目

单次 LLM 调用无法交付保险建议，因为它无法：

- **证明可追溯** —— 引用的是哪条法规？哪个版本？哪个来源？
- **执行治理** —— 来源是否权威？有授权？在有效期内？
- **Fail closed** —— LLM 永远会给答案，哪怕它不该答。
- **恢复** —— 局部失败会级联；没有检查点、没有重试。
- **被评估** —— 你无法对一个 Prompt 做回归测试。

本项目构建的是缺失的**执行层** —— Agent *运行时*，而不是又一个
Prompt。LLM 是受治理阶段内有界的工具调用者；由确定性规则决定
哪些证据可以参与决策。

---

## 架构

```text
                        用户
                         │
                         ▼
                ┌─────────────────┐
                │   Agent 运行时   │  (orchestrator、调度器、
                └────────┬────────┘   checkpoint、replan、HITL/HOTL)
                         │
                         ▼
                ┌─────────────────┐
                │     Skills      │  (8 个阶段，schema 契约，
                └────────┬────────┘   数据链不变量)
                         │
                         ▼
                ┌─────────────────┐
                │     知识层       │
                └────────┬────────┘
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
      Mock Provider             WeKnora v0.8.0
      (离线测试)              (live HTTP 检索)
             │                       │
             └───────────┬───────────┘
                         ▼
                ┌─────────────────┐
                │   KnowledgeHit   │  (document_id, chunk_id,
                └────────┬────────┘   content, score, hash)
                         ▼
                ┌─────────────────┐
                │      治理        │  (9 条规则：权威、授权、
                └────────┬────────┘   有效窗、管辖、hash……)
                         ▼
                ┌─────────────────┐
                │      证据        │  (引用元组：来源、版本、
                └────────┬────────┘   有效窗、权威、hash、时间)
                         ▼
                ┌─────────────────┐
                │      溯源        │  (P001–P010：从决策到来源
                └────────┬────────┘   的 4 跳链)
                         ▼
                ┌─────────────────┐
                │      决策        │  (建议、报告)
                └────────┬────────┘
                         ▼
                       报告
```

> **WeKnora 提供检索基础设施。** 治理、证据校验、溯源与决策约束
> 归 Agent 所有。

---

## 3 分钟 Demo

```bash
./scripts/portfolio/run_demo.sh
```

三个场景，全部运行**真实系统**：

| Demo | 展示内容 | 结果 |
|---|---|---|
| **A — 正常决策** | 完整链路：客户 → 需求 → 风险 → 缺口 → 方案 → 知识 → 治理 → 证据 → 建议 → 报告 | PASS |
| **B — 证据篡改** | 合法证据 → 1 字节 hash 突变 → 溯源 DENY（P007） | DENY |
| **C — 证据不足** | 无关查询 → Agent 侧弃权 → 不产生无依据结论 | ABSTAIN |

Live WeKnora 模式：
```bash
export INSURANCE_AGENT_KNOWLEDGE_PROVIDER=weknora
export INSURANCE_AGENT_WEKNORA_URL=http://127.0.0.1:8080
export INSURANCE_AGENT_WEKNORA_API_KEY=<your-key>
export INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID=<kb-id>
./scripts/portfolio/run_demo.sh
```

---

## 真实能力 vs Demo

| 领域 | 状态 |
|---|---|
| Agent 运行时（orchestrator、调度器、checkpoint） | **真实** |
| Skills（9 个，带 schema 契约） | **真实** |
| 知识治理（9 条规则，registry 为权威） | **真实** |
| 证据 + 溯源（P001–P010，hash 锚定） | **真实** |
| WeKnora 检索（v0.8.0，live HTTP，Docker） | **真实** |
| 评估（6 套件，300+ 用例，变异测试） | **真实** |
| 安全（认证、RBAC、PII、加密、保留） | **真实** |
| 产品目录 | **Demo**（12 个虚构产品） |
| LLM provider | **未验证**（R-05 门 BLOCKED） |
| 生产数据库 | **未实现**（JSON/JSONL） |
| 多租户 / 公网部署 | **未实现** |

→ 完整审计：[docs/portfolio/REAL_VS_DEMO.md](docs/portfolio/REAL_VS_DEMO.md)

---

## 关键设计决策

| 决策 | 原因 |
|---|---|
| **Skills，而不是一个大 Prompt** | 数据链不变量（FACT→REQ→RISK→GAP→SOL→PRODUCT）；逐阶段契约、评估与修复 |
| **确定性规则，不用 LLM 裁判** | 可复现、可测试、可审计；外置 `*.rules.json`；AGENTS.md §5 |
| **Provider 抽象** | Mock ↔ WeKnora 在 KnowledgeHit 边界之下互换；治理/证据/溯源不变 |
| **治理 registry** | 权威/授权/有效窗/管辖归 Agent 所有，而不是归后端 |
| **证据 ≠ LLM 回答** | 只有引擎检索到的逐字 chunk 才能成为证据；LLM 文本绝不进入链路 |
| **溯源（P001–P010）** | hash 锚定的 4 跳链：决策 → 证据 → chunk → 来源 |
| **处处 fail-closed** | 保险领域："我不知道" > 错误答案 |
| **WeKnora ≠ Agent 大脑** | WeKnora 负责找文档；Agent 决定什么可以参与建议 |

→ 完整理由：[docs/portfolio/ARCHITECTURE_DECISIONS.md](docs/portfolio/ARCHITECTURE_DECISIONS.md)

---

## 评估

```text
测试金字塔：
Unit → Contract → Integration → Business E2E → Mutation → Security → Live WeKnora

运行时测试：             474 PASS
Benchmark：              42/42（无依据结论率 = 0）
对抗性：                 42/42（知识 + agent + 安全 + 评估攻击）
Phase 14–18 回归：       PASS（全部套件，mock + live 模式）
变异测试：               26/26（评估器能捕获注入缺陷）
安全评估：               98/98（认证、RBAC、PII、审批、provider）
Live WeKnora：           48/48（检索、治理、溯源、故障）
```

> 以上是项目级验证结果，不是生产 SLA，也不是行业基准结果。

→ 详情：[docs/portfolio/EVALUATION.md](docs/portfolio/EVALUATION.md)

---

## 溯源链

每条建议都可回溯到真实来源：

```text
决策
  → 证据 (evidence_id)
    → KnowledgeHit (chunk_id, content_hash)
      → WeKnora Chunk (live 检索)
        → 文档 (document_id)
          → 版本 (source_id@version, 有效窗)
            → 来源 (权威、授权、管辖、canonical_uri)
```

篡改任何字节 → hash 不匹配 → DENY。法规过期 → 有效窗检查 →
DENY。授权未知 → DENY。管辖错误 → DENY。

→ 3 条人工验证链路：[docs/portfolio/PROVENANCE_WALKTHROUGH.md](docs/portfolio/PROVENANCE_WALKTHROUGH.md)

---

## 诚实的限制

- 产品目录是 **demo**（12 个虚构产品）
- 没有真实客户部署
- 没有生产数据库（JSON/JSONL + FileLock）
- 没有生产规模 benchmark（单台开发机）
- LLM 成本未度量（确定性路径：0 次 LLM 调用）
- WeKnora 缺少治理元数据 → 需要 Agent 侧 registry
- 事件日志缺少密码学链（P2 技术债）
- 当前模型没有 life/R4 的方案方向
- R-05 provider 政策仍 BLOCKED（等待运维验证）
- 7 项 P2 + 4 项 P3 发现已记录，均不阻塞

→ 完整清单：[docs/portfolio/LIMITATIONS.md](docs/portfolio/LIMITATIONS.md)

---

## Portfolio 包

| 文档 | 用途 |
|---|---|
| [PORTFOLIO_STORY.md](docs/portfolio/PORTFOLIO_STORY.md) | 10 分钟叙事 |
| [ARCHITECTURE_DECISIONS.md](docs/portfolio/ARCHITECTURE_DECISIONS.md) | 8 个关键"为什么" |
| [PROVENANCE_WALKTHROUGH.md](docs/portfolio/PROVENANCE_WALKTHROUGH.md) | 3 条真实链路（合法/篡改/弃权） |
| [EVALUATION.md](docs/portfolio/EVALUATION.md) | 测试金字塔 + 指标 |
| [REAL_VS_DEMO.md](docs/portfolio/REAL_VS_DEMO.md) | 能力分类 |
| [LIMITATIONS.md](docs/portfolio/LIMITATIONS.md) | 全部 P2/P3 发现 |
| [INTERVIEW_SCRIPT_10MIN.md](docs/portfolio/INTERVIEW_SCRIPT_10MIN.md) | 计时演示脚本 |
| [INTERVIEW_QA.md](docs/portfolio/INTERVIEW_QA.md) | 30 道面试 Q&A |
| [INTERVIEW_ATTACK_SURFACE.md](docs/portfolio/INTERVIEW_ATTACK_SURFACE.md) | 30 道攻击性问题 |
| [ADVERSARIAL_FINDINGS.md](docs/portfolio/ADVERSARIAL_FINDINGS.md) | 42 次攻击，全部 PASS |
| [OVER_ENGINEERING_REVIEW.md](docs/portfolio/OVER_ENGINEERING_REVIEW.md) | 哪些是必要的、哪些是展示 |
| [PROJECT_FACT_BASELINE.md](docs/portfolio/PROJECT_FACT_BASELINE.md) | REAL/MOCK/DEMO 分类 |
| [PHASE_19_FINAL_AUDIT.md](docs/portfolio/PHASE_19_FINAL_AUDIT.md) | 独立审计报告 |

---

## 快速开始

```bash
# 运行 demo（离线模式 —— 无需 WeKnora）
python demo/portfolio_demo/run_all.py

# 运行完整测试电池
python -m pytest tests/runtime -q
python -m pytest tests/portfolio -q

# 运行 benchmark
python tests/runtime/test_benchmark.py

# 全量回归（52 套件）
python tmp/run_regression.py
```

---

## 仓库结构

```text
insurance-agent/
├── README.md                  ← 本文件
├── AGENTS.md                  ← 项目约定（确定性优先）
├── runtime/                   ← Agent 运行时（orchestrator、harness、tools）
├── knowledge/                 ← 知识层（provider、治理、
│                                  证据、溯源、试点语料）
├── adapters/                  ← 规范化 artifact 适配器
├── contracts/                 ← 11 个 schema 文件（skill 契约）
├── .trae/skills/              ← 9 个 skill 定义
├── catalog/                   ← demo 产品目录
├── evals/                     ← 6 个评估器套件
├── tests/                     ← 80 个测试文件
├── demos/                     ← 10 个 demo 脚本
├── demo/portfolio_demo/       ← 3 场景 portfolio demo
├── scripts/portfolio/         ← demo 运行器
├── docs/
│   ├── architecture/          ← 架构文档
│   ├── production/            ← 38 份阶段报告
│   └── portfolio/             ← 19 份 portfolio 文档
└── tmp/                       ← 运行时产物（gitignored）
```

---

## 我的贡献

架构与语义：skill 边界、规范化客户状态、provider 抽象、治理规则、
溯源校验器、评估策略、HITL/HOTL 控制设计、checkpoint/恢复、
benchmark 与红队设计、WeKnora 集成。

AI 编码工具仅作为开发工具使用；系统设计及其证明才是核心。
