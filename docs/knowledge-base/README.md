# Insurance KB v1.0 — WeKnora Knowledge Base Standard

**WeKnora = 唯一 Runtime Knowledge Base**(架构不变更)。本目录是
KB v1.0 的文档治理层:Registry/规范/导入规格/验收。Repo Markdown
仅作为 source/ingestion material,永不成为 Runtime Knowledge Source。

## 文件

| 文件 | 用途 |
|---|---|
| `document-registry.yaml` | 30 份核心文档正式注册表(状态/来源/映射) |
| `metadata-schema.yaml` | metadata 字段与枚举规范 |
| `import-spec.md` | WeKnora 导入规格与环境 |
| `authority-policy.md` | 层级权威边界(不可自动跨层升级) |
| `chunk-policy.md` | 分层 chunk 规范 |
| `retrieval-benchmark.md` | 50 问 benchmark 定义与结果 |
| `acceptance-checklist.md` | Owner 验收 checklist |
| `KB-V1-OWNER-ACCEPTANCE.md` | Owner 人工验收文档 |

## 状态机

```
KB_BUILDING → IMPORT_READY → IMPORTED → AUTO_VALIDATED → OWNER_REVIEW_READY
                                                              ↓ (Owner only)
                                                        OWNER_APPROVED
```
当前状态:**OWNER_REVIEW_READY**(Owner 确认前不得视为生产可用)。
