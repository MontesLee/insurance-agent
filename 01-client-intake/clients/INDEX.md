# Client Intake 客户索引（INDEX）

> 本文件由 Skill 的 Step 0-A（新客户创建）/ Step 9（写回轮次）自动维护，禁止手动改内容。
> 只有这 3 种情况会写 INDEX：新客户创建 / 每轮状态写回后轮次 +1 / Completion Gate true 时标记已完成。

| 行号 | 客户编号 | 客户别名            | 档案目录（相对路径）           | 创建时间   | 当前轮次 | Intake 完成状态 | 最近更新   | 备注 |
|------|----------|---------------------|--------------------------------|------------|----------|-----------------|------------|------|
| 1    | C001     | CASE_001 回归隔离　　　　　　　 | clients/CASE_001-Regression/ | 2026-09-07 | R0       | ❌ 未完成       | 2026-09-07 | Regression Script Init |
| 2    | C002     | CASE_002 回归隔离　　　　　　　 | clients/CASE_002-Regression/ | 2026-09-07 | R0       | ❌ 未完成       | 2026-09-07 | Regression Script Init |
| 3    | C003     | CASE_003 回归隔离　　　　　　　 | clients/CASE_003-Regression/ | 2026-09-07 | R0       | ❌ 未完成       | 2026-09-07 | Regression Script Init |
| 4    | C004     | CASE_004 回归隔离　　　　　　　 | clients/CASE_004-Regression/ | 2026-09-07 | R0       | ❌ 未完成       | 2026-09-07 | Regression Script Init |
| 5    | C005     | CASE_005 回归隔离　　　　　　　 | clients/CASE_005-Regression/ | 2026-09-07 | R0       | ❌ 未完成       | 2026-09-07 | Regression Script Init |
| 6    | C006     | CASE_006 回归隔离　　　　　　　 | clients/CASE_006-Regression/ | 2026-09-07 | R0       | ❌ 未完成       | 2026-09-07 | Regression Script Init |
| 7    | C007     | CASE_007 回归隔离　　　　　　　 | clients/CASE_007-Regression/ | 2026-09-07 | R0       | ❌ 未完成       | 2026-09-07 | Regression Script Init |
| 8    | C008     | CASE_008 回归隔离　　　　　　　 | clients/CASE_008-Regression/ | 2026-09-07 | R0       | ❌ 未完成       | 2026-09-07 | Regression Script Init |
| 9    | C009     | 张先生三口之家 | clients/C009-张先生三口之家/ | 2026-09-07 | **R4**       | **✅ 已完成**   | 2026-09-09 | **R4 Intake 完成 ✅（H1-H6 全满足）**；补 Confirmed 城市=北京 + 家庭年支出约35万 → P0 阻塞全部清空；新增 Inferred I007 保费占收入 2.5%（保额有上浮空间）+ I008 北京一线城市效应（教育/医疗成本上浮）；Pending P001 下次正式提醒 R5；Handoff Notes 已交接模板可直接交 Needs Analysis |
| 10    | C010     | C010-李女士单亲妈妈　　　　　　　　 | clients/C010-李女士单亲妈妈/ | 2026-09-07 | R0       | ❌ 未完成       | 2026-09-07 | Regression Script Init |
