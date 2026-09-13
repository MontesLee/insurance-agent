# Usage Guide — report-generation

## 1. CLI 入口

```bash
# 从文件读取输入（5 路上游结构化的 JSON）
python scripts/invoke-report-generation.py --input input.json

# 从 stdin 读取
echo '<json>' | python scripts/invoke-report-generation.py --stdin

# 指定规则文件 / 跳过校验
python scripts/invoke-report-generation.py --input input.json --rules resources/config/report.rules.json
python scripts/invoke-report-generation.py --input input.json --no-validate
```

- 成功输出：完整 `ReportGenerationResult` JSON（含 `rendered_report`），exit 0。
- 校验失败输出：`<result>` + stderr `OUTPUT_INVALID` + 错误项，exit 1。

## 2. 模块调用

```python
from scripts.report_generation_engine import generate_report, load_rules
from scripts.validate_report import validate_output

rules = load_rules()
result = generate_report(input_dict, rules)          # 生成
ok, errors = validate_output(result)                 # 校验
print(result["rendered_report"])                      # 成稿
```

`scripts/upstream_results_adapter.normalize_input(input_dict, rules)` 可单独用于把 5 路上游归一化为 `{client_state, requirement_analysis, risk_analysis, knowledge_search, recommendation, missing_core, all_core_missing}`。

## 3. 输入组装

`input_dict` 五块：
- `client_profile`：CanonicalClientState（client-intake 产出的规范化客户状态）。
- `requirement_analysis`：requirement-analysis 输出。
- `risk_analysis`：risk-analysis 输出（接受 `risk_analysis[]` 或 `risks[]`）。
- `knowledge_search` / `recommendation`：可选；缺失传 `null`。

## 4. 不做什么（Don't）

- 不要修改上游 Skill 文件。
- 不要给上游缺字段「补值」——缺失让 adapter 标 `missing`，成稿渲染「待确认」。
- 不要在报告中写具体保险产品名或推销语（会触发 HALLUCINATION）。
- 不要重排/重算上游的优先级、风险等级、推荐结论。
- 不要因上游冲突而自行裁决（只 surface `UPSTREAM_CONFLICT`）。

## 5. 运行测试

```bash
python scripts/run_report_dataset.py        # 全量回归，8 用例断言 expect
python scripts/test-report-generation.py    # 8 用例 + 2 条负向自愈
```

两者均输出 `ALL GREEN`（exit 0）即视为通过。
