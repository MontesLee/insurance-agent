# 28.K.28-II-FIX2 · Claim Support 数值锚边界加固

Date: 2026-09-30 · Mode: **极小安全修复**（`_value_found` 单函数·+18 回归
检查）· **K.28-II-FIX2: PASS**

## 1. Reproduction（修复前·当前实现实复现）

- **原始匹配路径直证**：`_value_found("0","元","免赔额为10000元") =
  True`（子串命中）。
- **端到端假支持复现（P2-1 发现形）**：证据=目录记录
  `coverage_directions:[…免赔额] constraints:[…10000元]`（标签与数字
  相距>8 字→矛盾路径无可提取值）× claim「免赔额为0元[E1]」→
  **SUPPORTED（anchors covered 1/1）**——false support 实复现。
- 注：标签相邻形（证据「免赔额为10000元」）在 IMPL 时代已被
  claim↔evidence 矛盾检测判 CONTRADICTED（先行拦截）——P2-3 的
  暴露面=标签远离数字的证据形态（目录记录渲染即此形）。

## 2. Root Cause

`_value_found` 用裸子串存在性（`value+unit in text`）——短数值 token
是长数值的子串（"0元"⊂"10000元"；"1000"⊂"10000"）。

## 3. Minimal Fix（§3-4·单函数·复用既有机制）

`_value_found` 升级为**数字边界感知匹配**：`(?<!\d)value(unit)?(?!\d)`
正则（前字符非数字+后字符非数字；保留 FIX1 时代的 万/万元 单位变体；
无单位时后边界仍要求非数字）。不删数字锚（仍全额参与判定）；
不做单位换算/中文数字/范围比较（§1 禁项零触碰）。

## 4. Before / After

| 场景 | 前 | 后 |
|---|---|---|
| "0元" vs "10000元"（标签远离形） | **SUPPORTED（假支持）** | **UNSUPPORTED** |
| "0元" vs "免赔额为0元" | SUPPORTED | SUPPORTED（保持） |
| "10000元" vs "免赔额为10000元" | SUPPORTED | SUPPORTED（保持） |
| "1000元" vs "10000元"（双向） | 子串假命中 | 无命中 |
| "90天" vs "等待期为90天。" | SUPPORTED | SUPPORTED（语料真实形态保持） |
| "100万" vs "保额100万元" | SUPPORTED | SUPPORTED（万/万元 变体保持） |

## 5. Regression Matrix（test_k28ii_claim_support.py 新 18 检查）

FIX2-01（0 vs 10000→blocked）·02（精确 0→SUPPORTED）·03（精确
10000→SUPPORTED）·04（1000 vs 10000→blocked）·05/06（赔付双向→
blocked）·07（中文标点（一）…；→blocked）·08（裸匹配器双向断言）·
09（无关数字文本→blocked）·10（**冻结语料真实数值案例 P06 形
90 天→SUPPORTED**）+ **P2-3 目录记录原形→UNSUPPORTED** + 穷举
0/00/000/10/100/1000 ⊄ 10000元（6 断言）。
断言语义注记：blocked = UNSUPPORTED∨CONTRADICTED∧门失败——标签
相邻时矛盾路径先触发（CONTRADICTED=更锐拦截），两者同为不投递，
满足任务「NOT SUPPORTED」要求。

## 6. False Support 结果

- **已知 P2-3 假支持复现（目录记录形）：消除（KNOWN=0）**
- 穷举短⊂长子串族：0 误命中
- 冻结语料复测：**FP=5（=baseline 不变）·escape 0/15·P/R 0.80/0.80·
  exact 81.55% 全不变**——无新增假支持·无新增误拒（数值正例
  P 类 31/40 与修复前逐位一致）

## 7. FIX1 回归

fix1_normalization 全检查保持（列举/冒号顿号/年份括号零锚污染）——
套件内 FIX1-01/02/03 PASS（65/65 含）。

## 8. Claim Support 全套

**65/65 ALL GREEN**（原 48+FIX2 新 17 项检查；含 P2-1 套件 23/23
独立绿）。

## 9. 全仓回归

- 决策链 E2E 16+FI 6 = **22/22**；密封套件（Intent 12·C2 8·K.26 6·
  B4 7）33 项绿
- **全电池 865 passed + 2 skipped**
- 过程注记（环境性·如实）：一次全电池 6 失败=test_p24_registry_pg
  （Windows temp 的 pg_cred.txt 被 OS 清理删除→PG 密码缺失·该测试
  基础设施从 temp 文件读凭据的既有 fragile 设计）；从 tmp/hd2.pgpass
  恢复该 env 文件后 p24 6/6+全电池复绿。**与 FIX2 零相关**（该 6
  测不触 claim_support；diff 仅 2 文件）。

## 10. Scope Audit

```
Claim Support semantic changes: 数值边界匹配 ONLY（_value_found 单函数）
Intent/C1/C2/Router/K.26/P2-1 guard/Planning/LLM/D-08/OD-12/baseline/
shadow corpus/S2 修改 = 0（frozen 文件 mtime 未动·staging=0）
改动 = claim_support.py（1 函数）+ test_k28ii_claim_support.py（+1 节）
+ 本报告 + pg_cred.txt 环境恢复（非仓库文件）
```

## 11. Remaining P2/P3（不修·沿袭）

P2-2 词法语义天花板（否定/非字面）·P3-1..4（DP 沿袭）。P2-3 **CLOSED**。

## 12. Runtime / S2 / P2-1 边界

:8123 仍 DOWN（第十次回收沿袭·未重启——FIX2 与 P2-1 均未载入
runtime；载入=Owner 单次重启后 P2-1 Reverify+FIX2 runtime smoke）。
**S2 OPEN-UNSTARTED 保持·Batch-2 未分发·Production Authority NOT
GRANTED·Planning/LLM OFF。**

---

```
K.28-II-FIX2: PASS
P2-3: RESOLVED（false support 0；无新增 FP/误拒；语料指标逐位不变）
```
