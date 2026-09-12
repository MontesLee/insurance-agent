# client-intake-data（运行时客户数据根）

本目录是 `client-intake` Skill 在**真实使用**时写入客户会话数据的运行时根目录，**不属于 skill 分发内容**（不进 `.trae/skills/client-intake`，建议版本库忽略）。

- 客户档案落在 `client-intake-data/clients/C00{nn}-{客户别名}/` 下，每个客户独立目录。
- `INDEX.md` 由 Skill Step 0-A / Step 9 在运行时自动维护，禁止手动编辑。
- 与 skill 内的 `evals/clients/`（冻结测试夹具）和 `examples/`（演示样例）严格区分——**真实数据只写在这里，绝不写进 skill 目录**。
