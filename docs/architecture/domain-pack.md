# 保险领域包（Domain Pack）— V2.1

> Phase 8 交付物。把原本散落在各 Specialist Skill 核心、knowledge-search 测试夹具、evidence-request 规则里的
> **险种分类与证据类型**下沉到一个版本化、可审计、可被 `rag` 摄取的共享层。
> 对应 Phase 0 审计基线第 159 行的规划：`domain/insurance/`（pack / playbook / references / overlays）。
>
> **位置**：`domain/insurance/`
> **原则**：基础领域模型直接写 `references/` 并带 version；overlay 默认不使用（见 AGENTS.md §8）。
> **边界**：本包是「知识提供层」，不修改任何 8 个 Specialist Skill 的逻辑。

---

## 1. 目录结构

```text
domain/insurance/
├── pack.yaml                       # 领域包清单（唯一事实源：taxonomy / evidence_types / source_levels / overlay 策略 / rag_seed）
├── playbook.md                     # 领域推理手册（险种→证据查询映射、冲突/时效策略、扩展流程）
├── references/                     # 权威领域知识（带 version / effective_date，可作 rag 生产语料）
│   ├── 00-product-taxonomy.md      # 险种分类唯一真相来源（code / alias / 展名）
│   ├── 01_medical_insurance.md     # 百万医疗险
│   ├── 02_critical_illness.md      # 重大疾病保险（code=critical）
│   ├── 03_accident_insurance.md    # 意外险
│   ├── 04_life_insurance.md        # 定期寿险
│   ├── 05_health_underwriting.md   # 核保 / 健康告知 / 既往症
│   └── 06_claims.md                # 理赔
├── overlays/                       # 默认空（intentionally empty）
│   ├── README.md
│   └── .gitkeep
├── scripts/
│   ├── build_domain_engine.py      # 装配 KnowledgeSearchEngine（只读消费 knowledge-search 的 rules）
│   ├── seed_rag.py                 # 把 references 摄成 SQLite 生产知识库
│   └── validate_pack.py            # 领域包不变量 + 门禁（59 项断言）
└── kb/                             # 运行产物（seed_rag 生成，已 .gitignore）
    └── insurance_kb.sqlite
```

---

## 2. 它解决了什么

| 问题（Phase 0 之前） | Domain Pack 的解法 |
|---|---|
| evidence 层用 `critical_illness`、rag 层用 `critical`，命名漂移 | `pack.yaml: product_types` + `alias_to_code` 声明唯一映射，validate 强制对齐 |
| 险种知识散落在 knowledge-search 测试夹具（TEST DATA）里 | `references/` 成为权威生产语料，夹具仍是该 Skill 自有测试数据 |
| 各 Skill 各自脑内维护证据类型 | `evidence_types` 成为权威注册表，与 `evidence-request.rules.json` 对齐 |
| 新增险种/事实无统一入口 | `playbook.md` 第 4 节给出扩展流程 + `validate_pack.py` 门禁 |

---

## 3. 如何被消费（纯只读、不改 Skill）

- **knowledge-search**：运行时可通过 `--kb <domain/insurance/references>` 指向本包作为生产语料；其默认仍用自有 `evals/fixtures/kb` 测试夹具，互不影响。
- **evidence provider**：`evidence/` 回环检索时可指向本包语料（`build_domain_engine` 只读消费 knowledge-search 的 rules 装配引擎）。
- **各 Specialist Skill**：自己的 `references/NN-*.md` 描述「怎么做判断」；本包描述「判断依据的事实」。前者可引用本包 taxonomy/evidence_types 作为规范，但不应重抄事实。

---

## 4. 验证

```bash
# 领域包不变量 + 门禁（59/59）
python domain/insurance/scripts/validate_pack.py

# 生成生产知识库（可选，产物在 kb/）
python domain/insurance/scripts/seed_rag.py

# 试检索
python domain/insurance/scripts/build_domain_engine.py --query "重疾险 等待期" --product-type critical
```

`validate_pack.py` 覆盖：pack.yaml 合法性、references 版本化、taxonomy 与 `rag.PRODUCT_BY_PREFIX` / `evidence-request` 对齐、evidence_types 合法、source_levels 完整、overlay 不泄漏、references 可被 `rag.store` 摄取、代表性 domain 检索冒烟。

---

## 5. 与 V2.0 的关系

`domain/insurance/` 是 V2.1 新增的**横切共享层**，挂在 V2.0 的 `contracts/` · `adapters/` · `evidence/` · `state/` · `workflow/` 之上：

```text
                 ┌───────────────────────────────┐
                 │   domain/insurance/ (V2.1)    │  共享领域知识包
                 │   pack · playbook · references │
                 └───────────────┬───────────────┘
                                 │ 只读消费
   Client Intake ──► Requirement ──► Risk ──► Gap ──► Solution ──► Product ──► Report
                                 ▲                                      │
                                 └────────── Knowledge Search ◄──────────┘
                                           (共享 Evidence Provider，检索本包语料)
```
