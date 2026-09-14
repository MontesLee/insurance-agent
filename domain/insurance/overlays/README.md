# overlays/ — 默认为空（intentionally empty）

按 AGENTS.md §8 与 `pack.yaml: overlays` 策略，**Domain Pack 默认不使用 overlay**。

## 何时才在这里放东西

仅当确证存在 **Context-specific modification**（地区监管细则 / 客群核保规则 / 公司业务规则），
且无法用 `references/` 基础模型直接覆盖时，才引入 overlay：

1. 新建 `overlays/<name>/` 子目录；
2. 在 `pack.yaml: overlays.available` 登记 `<name>`，并按需将 `overlays.enabled` 设为该范围；
3. overlay = Base（`../references/`）+ 增量覆盖，绝不修改 Base。

## 当前状态

本目录刻意只保留本说明与 `.gitkeep`。`validate_pack.py` 含「overlay 泄漏」不变量：
若检测到 `overlays/` 下出现非 README/非 .gitkeep 的内容而 `pack.yaml: overlays.enabled=false`，
校验将失败，提醒先登记策略。
