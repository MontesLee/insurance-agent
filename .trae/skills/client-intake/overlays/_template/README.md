# 新险种 Overlay 模板

复制本目录为新险种目录，然后逐项填写：

```
cp -r _template/ <new-id>/     # Windows: Copy-Item _template <new-id> -Recurse
```

## 需要动的文件

| 文件 | 动作 |
|---|---|
| `overlay.yaml` | 替换所有 `<...>` 占位符 |
| `intake-dimensions.md` | 改写 A-F 六个小节 |

## 填写注意

1. **`id` 必须与目录名完全一致** —— `check-overlay-integrity.ps1` 的 A4 会检查，不一致直接 FAIL。
2. **`keywords` 取客户会说的口语词**，不是行业术语。
   客户说"大病"，不太说"重大疾病保险"；说"报销"，不太说"医疗费用补偿"。
3. **`contamination_terms` 只放本险种真正独有的词**。
   - 放太宽 → 误报通用层污染
   - 放太窄 → 守不住架构边界
   - 判断标准：这个词出现在通用层，你会不会觉得"不对，这应该是某险种的事"？会，就放进来。
   - 反例：`职业类别` 不该放进意外险 —— 它是跨险种的核保通用概念，通用层 H3 已用。
4. **`status` 一律 `draft` 起步**，只有补了 `evals/cases/` 用例后才改 `active`。
   draft 不会被 `resolve-overlays.ps1` 自动激活（需显式 `-IncludeDraft`）。
5. **`must_not` 不要重复通用层已有禁令**（产品推荐、保额计算、医学评价已全局禁止），
   只写本险种特有的风险点。

## 上线前自检

```
scripts/check-overlay-integrity.ps1
scripts/resolve-overlays.ps1 -List
scripts/resolve-overlays.ps1 -InputText "<一句客户原话>" -IncludeDraft
```

三项都要看：

- 守卫 FAIL = 0
- 清单里能看到新险种，状态为 `DRAFT`
- 用真实客户口语能命中它（命中不到说明 keywords 取错了）

## 最重要的约束

> **Overlay 决定"多问什么"，不决定"怎么判断"。**

只写采集维度与记录口径。任何"这个客户应该买多少""这个病严不严重""这个能不能投保"
都属于判断，一律禁止 —— 它们会破坏 client-intake 的边界（HF01）。
