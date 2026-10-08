# 28.C-3 · WeKnora Unified Knowledge Base + Admin UI Verification（COMPLETE 版）

Date: 2026-10-01（三轮：审计 09-30 → BLOCKED×2 → 本轮 COMPLETE）·
**28.C-3: COMPLETE**（零生产代码修改·全部 SEALED 组件零触碰）

## 1. Status

**COMPLETE**（7/7 域文档 ACTIVE；儿童案例复测合格；全电池 865+2 零回归）

## 2. WeKnora Environment

```
Admin frontend:  http://localhost:80（WeKnora-frontend docker·200）
Backend:         WeKnora-app :8080（healthy）
Dataset:         insurance-pilot-2（54d7b757…·tenant 10001）= Agent env 同一 KB
Credential:      runtime retrieve-only key（不变）+ admin access token
                 （Owner 授权：项目自有 tenant-10001 refresh token 经
                 /api/v1/auth/refresh 换新·tmp/weknora-admin.jwt·不打印）
Embedding:       全新 weknora-ollama 容器（weknora-ollama:11434·
                 nomic-embed-text 274MB·数据卷 D:\Workspace\ollama）
```

## 3. Knowledge Inventory（终态）

| Document | Source | WeKnora | Chunks | Version | Authority |
|---|---|---|---:|---|---|
| 10 部 pilot 法规（cn-*） | knowledge/pilot/documents/ | ✅ 已在（304 chunks） | 304 | 各年版 | S/A |
| 00-product-taxonomy | domain/insurance/references/ | ✅ **ACTIVE** | 3 | 1.0 | B |
| 01_medical_insurance | 同上 | ✅ **ACTIVE** | 2 | 1.0 | B |
| **02_critical_illness** | 同上 | ✅ **ACTIVE** | 2 | 1.0 | B |
| 03_accident_insurance | 同上 | ✅ **ACTIVE** | 2 | 1.0 | B |
| 04_life_insurance | 同上 | ✅ **ACTIVE** | 2 | 1.0 | B |
| 05_health_underwriting | 同上 | ✅ **ACTIVE** | 2 | 1.0 | B |
| 06_claims | 同上 | ✅ **ACTIVE** | 2 | 1.0 | B |

**KB 终态**：insurance-pilot-2 = **17 docs 全部 completed+enabled**。

## 4. Retrieval Verification（Step 9 回归·修复后）

| Query | Hits | Qualified | Top Sources | Result |
|---|---:|---:|---|---|
| Q1 等待期是什么 | 1 | 1 | 人身保险产品信息披露管理办法 | 证据→生成 |
| Q2 什么是重疾险 | 1 | 1 | **领域包重疾险** | 证据→生成 |
| Q3 少儿重疾险应该关注什么 | 1 | 1 | **领域包重疾险** | 证据→生成 |
| **Q4 给孩子配置重疾险前考虑什么** | **1** | **1** | **领域包重疾险** | **证据→生成** |
| Q5 无关（餐厅） | 0 | 0 | — | 正确空（fail-closed） |

## 5. Child Critical Illness Case（核心回归）

```
Before: WeKnora 0 hits → C2 0 输入 → insufficient_evidence 拒答
After:  WeKnora 1 hit（领域包重疾险 02_critical_illness）
        C2 qualified = 1（governed_status=success）
        全链 E2E（in-process·:8123 DOWN 期间）：intent=insurance_qa →
        insurance-qa-agent → retrieval allowed=1 → 生成 → 引用门拒答
        （citation_gate_rejected——stub 答案故意的引用违规形态；
        真实 glm 下将由 K.26/B5.1 prompt 决定）
Final: 知识库覆盖缺口已消除；检索/资格链恢复。Claim Support 行为
       保持在门内（SEALED 不动）——拒答与否取决于真实生成内容。
```

## 6. Architecture Audit（终验）

```
WeKnora is the only Runtime Knowledge Base:   YES
Agent directly reads repo insurance docs:     NO
Second Runtime KB exists:                     NO
WeKnora Admin frontend exposes KB management: YES（:80·API 级验证：
  KB 列表/文档列表/parse 状态/chunk 详情均经 admin API 实证——与前端
  同源数据；浏览器点选验证待 Owner 登录确认）
```

## 7. 治理操作台账（全部 Owner 授权+框架自身 API/最小 SQL）

| 操作 | 授权 | 机制 |
|---|---|---|
| tenant-10001 refresh→access token | Owner 显式 | WeKnora 自身 /auth/refresh |
| 7 篇上传+守护生命周期 | 任务书 | 既有 ingest_document（幂等） |
| WeKnora .env 旧 IP→weknora-ollama + app 容器重建 | 任务书（修复基础设施） | compose .env + up -d app |
| 6×fixtures ACTIVE→SUPERSEDED | Owner 显式 | 框架 krs.supersede |
| 6×fixtures source scope GLOBAL→FIXTURES | Owner 显式 | §43 scope 机制（1 条 UPDATE） |
| models 表 base_url 更新 | 基础设施修复 | jsonb_set |

## 8. Remaining Gaps（如实）

1. **浏览器级 Admin UI 点选验证未做**（admin API 全证+前端 200；Owner
   登录 :80 目验为收尾可选项）。
2. **chunk 粒度粗**：域文档每篇仅 2-3 chunks（WeKnora 默认分块）——
   检索命中但定位精度受限；细化分块=WeKnora 配置项（后续可选）。
3. **fixtures 语料 KB 内仍在**（agent-fixtures KB 13 chunks 物理未删；
   registry 层已隔离 SUPERSEDED+FIXTURES scope——运行时不可见）。
4. :8123 重启后真实 glm 端到端（儿童案例真实回答）待 Owner 重启验证。
5. ollama 容器无 restart policy（docker restart 不自动拉起；建议
   --restart unless-added 后续补）。

## DoD 核对

全部 ✅（Admin 认证✓·dataset 确认✓·盘点✓·7/7 ACTIVE✓·无第二 KB✓·
文档可见+解析 verified✓·检索 smoke 5/5✓·儿童案例复测✓·运行时链路
in-process 复测✓·Agent 不直读 Markdown✓·SEALED 全保持✓·K.29 DESIGN
未动✓·S2 OPEN-UNSTARTED✓·报告更新✓）。

---

**28.C-3: COMPLETE** — WeKnora 现为具备 17 文档（10 法规+7 域知识）
的唯一 Runtime Knowledge Base；儿童重疾类问题从 0-hit 拒答恢复为
qualified evidence 通路。
