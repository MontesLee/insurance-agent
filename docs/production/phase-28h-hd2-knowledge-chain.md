# Phase 28.H — HD-2 Production Knowledge Chain / WeKnora Enablement 报告

Date: 2026-09-26 · 目标：解 B-01——生产知识链切换为**治理真实 WeKnora**，
并以自动化+隔离实时证据证明 QA/Product-QA 不回退 mock。

## Status

```text
28.H STATUS: PASS（B-01 = RESOLVED——见 Gate 矩阵与证据；残留非阻塞
技术债见 §Remaining）
```

## B-01

```text
B-01 = RESOLVED（production knowledge = governed WeKnora；strict 模式
        mock 禁止+启动 fail-closed+断网零回退；真实检索与全链消费者
        证据在案）
```

## Production Knowledge

```text
provider = weknora（隔离生产级实例 :8123 实证 controlled_pilot）
WeKnora  = Phase-24 既有栈复用（WeKnora-app :8080；未重建任何知识后端）
mock     = strict 禁止（HG-24-03 既有；startup 拒绝=新增 H-6 预检）
strict   = controlled_pilot/production ⇒ weknora-only + PG registry 必需
corpus   = insurance-pilot-2 KB（10 份真实监管文档·304 chunks·194 嵌入；
           A/S 级监管源；与 agent PG registry（16 源/16 版/200 chunks
           投影）构成治理链——stamps→authority→governance 复用既有）
```

## Configuration（变量/注入/secret）

```text
INSURANCE_AGENT_KNOWLEDGE_PROVIDER=weknora
INSURANCE_AGENT_WEKNORA_URL=http://127.0.0.1:8080
INSURANCE_AGENT_WEKNORA_API_KEY=<secret — 运行注入（tmp/ 文件），
  本阶段新签发 retrieve-only、仅限治理 KB 的 WeKnora API key
  （sha256 入库；原始值不落 git/日志/报告）>
INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID=54d7b757-…（真实监管语料）
INSURANCE_AGENT_WEKNORA_SEARCH_METHOD=vector_search（部署属性旋钮：
  该部署 hybrid/keyword 无 CJK 分词——vector 实证可用；env 驱动，
  未设置保持历史默认行为）
AGENT_PG_PASSWORD / INSURANCE_AGENT_DATA_KEY=<secret — 运行注入>
（隔离实例临时 API keys：CONSUMER/OPERATOR 测试凭据，已清理）
```

## Real Retrieval（经 KnowledgeService 治理路径）

```text
H-R1 续保/费率规定 → success·allowed=2·pilot_reg_health_ins_2019（A）✓
H-R2 等待期       → success·allowed=2·健康保险办法(A)+交强险条例(S) ✓
H-R3 责任免除     → success·allowed=3·农业险/交强险条例（S） ✓
H-R4 无意义查询   → 向量语义近邻 allowed=2（如实记录——冻结打分策略下
                    检索层不拒绝语义近邻；安全防线在答案层：E-7 式
                    拒答，见下 H-N2/全链证据）
```

## Negative / Fail-Closed Tests（自动化）

```text
H-N1 WeKnora 断网 → ProviderUnavailable 传播（零 mock 回退）✓
H-N2 语料无据     → 全链实测：4s 诚实拒答「知识库暂无可靠依据」
                    （零幻觉）✓
H-N3 引用缺失     → citation gate 拒（全链实测 QA 探针：检索成功
                    [A 级证据]→生成未过引用门→安全拒答）✓
H-N4 仅目录       → Product-QA 实测：catalog 锚点确认 P001 + 知识
                    证据经真实 WeKnora（knowledge-evidence artifact）
                    + 对目录外条款诚实声明知识库边界 ✓（无绕过）
H-N5 mock 强制    → strict 构造即拒（ProviderConfigError FORBIDDEN）
                    + startup 预检 RuntimeError PRODUCTION_KNOWLEDGE_
                    REQUIRED ✓
H-6 startup       → strict 启动：weknora 配置不全/不可达 → 拒绝启动
                    （_validate_production_defaults 扩展）✓
```

## 全链实时证据（隔离生产级实例 :8123，REAL_USER=0，探针）

```text
QA（知识）：intent=insurance_qa(conf1.0,rule)→knowledge-qa slice→
  WeKnora 治理检索（A 级）→生成→引用门→安全拒答（3.5 分钟含再生成；
  检索成功/LLM 引用失败/门拒绝三层已区分——model-fit 非 WeKnora 失败）
Product-QA：intent=product_qa→目录锚点 P001→knowledge_search 工具→
  knowledge-evidence artifact（真实 WeKnora 证据）→目录事实+知识边界
  诚实交付 ✓（Catalog≠WeKnora 替代；锚点+qualifying 双轨如 ADR-022）
```

## Acceptance Gates

```text
G-HD2-1  生产配置齐备（三变量+PG registry）PASS
G-HD2-2  WeKnora 可达（:8080 live；启动预检含 health）PASS
G-HD2-3  治理语料在位（10 真实监管文档·304 chunks·provenance
         source/version/effective/license 全字段）PASS
G-HD2-4  生产 provider=weknora（diagnostics 实证）PASS
G-HD2-5  生产禁 mock（构造拒绝+启动拒绝+断网零回退）PASS
G-HD2-6  启动校验 fail-closed（H-6 双路径）PASS
G-HD2-7  QA 真实检索路径（全链探针+H-R2）PASS
G-HD2-8  Product-QA 真实检索路径（全链探针）PASS
G-HD2-9  缺据 fail-closed（H-N2/H-N3 全链拒答零幻觉）PASS
G-HD2-10 WeKnora 断网零 mock（H-N1 自动化）PASS
G-HD2-11 provenance 可用（registry stamps→A/S 级标注于证据；16 源
         元数据全字段）PASS
G-HD2-12 消费者交付保持证据锚定（目录锚点+引用门+E-7 语义未动）PASS
```

## Regression

```text
backend: **755 passed + 2 skipped**（CI 口径=28.G 749 + HD-2 6 hermetic；
         live-env 复跑=**8/8 全过**[含 2 live]；零失败）·
web: 219 passed + 2 skipped（未触碰）· tsc clean
B4/M4/M3/E2-E7/B-02 T1-T10：含于全量全绿
未触碰：Intent/Router/Authority/Grounding 语义/QA·Product-QA workflow/
        Catalog 所有权/Consumer 身份与所有权/Event 词汇/Artifact
```

## Git Scope

```text
M knowledge/provider/weknora.py（transport search_method 部署旋钮——
  默认行为不变） · runtime/server.py（strict 启动知识预检——H-6）
A tests/runtime/test_hd2_production_knowledge.py（8）
M tests/runtime/test_p0_r06.py 之外零触碰；无 QA/grounding/router/
  intent/agent/consumer 文件改动（git diff 审计）
运维侧（非 git）：WeKnora 新签发 1 把 retrieve-only API key（DB 行
  hd2-production-retrieval，限治理 KB，可随时 revoked_at 撤销）；
  隔离实例/临时凭据已全部清理
```

## Production State

```text
REAL_USER = OFF · Router Authority UNCHANGED（默认 slices；:8000 保持
停止） · Consumer ownership UNCHANGED · 正式生产未触碰（全程隔离
:8123，已清理） · WeKnora 栈零重建（复用 Phase-24 容器）
```

## Remaining（本阶段后如实区分）

```text
B-01 = RESOLVED（生产知识链本体）
B-04 数据治理 = Owner Decision（不变）
model-fit citation = 独立已知问题（全链再次实证：检索成功+引用失败
  →安全拒答；与知识链可用性无关，不混同）
非阻塞技术债：①110/304 chunks 无嵌入（3 份核心法规各半）→ 检索
  覆盖不完整（WeKnora 侧 re-embed 待运维；未越权代做）②该部署
  keyword/hybrid 无 CJK 分词（已用 vector 旋钮规避并记录）③registry
  投影 200 chunks vs WeKnora 实际 chunk 切分不一致（re-anchor 依赖
  content_map，多 chunk 窗口 HASH_MISMATCH 为文档化行为）④正式
  :8000 升级到生产知识链=Owner 部署决策（本阶段仅隔离实例实证）
```

## STOP

不进入 28.I（B-04 Data Governance = Owner 决策阶段）。
