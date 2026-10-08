# S-N5 Runtime Error Audit — agent 环 RuntimeError→needs_review 签名（只定位·不修）

Date: 2026-10-05 · 范围: AUDIT ONLY（零代码/配置改动·Phase16 零接触·探针均 ops 身份
且标注 SN5-AUDIT-PROBE·authority 计数不变）

---

## 1. 签名

```text
intent: unknown_insurance_intent（无保险锚→conversation-agent 路径）
step 1: glm-5.3 主模型决策 OK（8.7s·373 tok·call_tool 意图=GENERAL_KNOWLEDGE）
step 2: glm-5.3-flashx 快档 3×RuntimeError（各 ~0.6s·零 LLM 调用计数）
→ finish(llm_invalid_output_or_provider_error) → NEEDS_REVIEW（固定模板文案）
```

现场: ①cutover smoke S-N5（10-05 02:28Z·sealed 基线）②复现探针×2（11:52 本地·
武装运行时·`tmp/obs/sn5_audit_probe_events.json`）——**确定性复现**（与
Authority/KB/嵌入无关）。

## 2. 根因（实证）

```text
glm-5.3-flashx → HTTP 429 code 1311:
"Your current subscription plan does not yet include access to GLM-5.3-FlashX"
glm-5.3-flash → 200 OK（1.2s）· glm-5.3 主模型 → 200 OK
```

- 自 K.35（2026-09-28）起 `LLM_FAST_MODEL=glm-5.3-flashx`（.env Stage-1 配置；
  当时金丝雀 23/23 实证可用）；**当前 z.ai coding 订阅已不含 FlashX 访问权**
  （权利回收/计划变更——具体时点 UNKNOWN·obs 可见 10-04 以来 flashx agent 调用
  5/5 EXHAUSTED·0 OK）。
- 链路: agent 环 step2+ 用快档（`runtime/agent/agent.py` 分层）→
  `model.py` httpx 非 200 → `RuntimeError("LLM provider error 429:…")` →
  `_generate_with_retry` 3 attempts 全灭 → needs_review（fail-closed 正确·
  无不安全输出）。

## 3. 影响面

| 路径 | 影响 |
|---|---|
| conversation-agent（无锚 unknown）/规划链 step2+ | **100% needs_review**（每次第二步骤起必 429） |
| knowledge-qa 切片 | 不受影响（qa=glm-5.3-flash ✓） |
| Phase16 authority judge | 不受影响（judge=qa 槽 flash ✓） |
| 主模型步骤 | 不受影响（glm-5.3 ✓） |

**Phase16 提示（重要）**: cohort 真实用户凡路由进会话 agent/规划（非 QA 切片）
的问题将全部 needs_review——会污染窗口 utility 观察。修复=Owner 决策（见 §5）。

## 4. 溯源澄清

- K.12 首真用户 run_50389328（09-27）签名为「2×tool_failed」（工具失败·
  flash 时代）≠ 本签名（step2 模型 429）——**不同根因，勿合并**。
- 观测缺口（记录不修）: `agent_step_error` 事件只留 `error_type`（RuntimeError），
  HTTP 状态/错误体被丢弃——本次须经 obs `agent.llm_call EXHAUSTED` + 直接探针
  才能定位。建议（Owner 门控）: 事件负载附带 `str(e)[:120]`。

## 5. 修复选项（不执行·Owner 决策）

1. **Ops 单值（推荐）**: `LLM_FAST_MODEL=glm-5.3-flash`（有权利·=K.35 前配置；
   回滚件 `tmp/env.rollback.k35` 正是为此留的）→ 重启。影响: 快档延迟回升
   （K.31-A flashx -20s 收益失效直至权利恢复）。
2. 恢复 z.ai 订阅 FlashX 权利（Owner 侧·恢复后零改动自愈）。
3. （可选+2）补观测: agent_step_error 载荷带错误消息（代码变更·Owner 门控）。

## 6. 终态

```text
FINAL STATUS: SN5_ROOT_CAUSE_IDENTIFIED
（provider 权利回归·非代码/非 KB/非 Authority；fail-closed 行为正确；
  修复=Owner 单选 §5）
```

---

## 7. Remediation（2026-10-05·Owner 选定 Option 1·已执行）

```text
Option Selected: 1 — glm-5.3-flash
Old Model:      glm-5.3-flashx
New Model:      glm-5.3-flash
Config:         .env line 18（changed variables = 1·sha 4e3b8c47… → cb72f29e…）
Rollback point: tmp/obs/sn5_remediation_rollback_point.json（单行还原 flashx；
                k35 工件=K.35 时代历史快照·非本次回滚件——如实区分）
Restart:        无需（load_llm_config 按请求读 .env·进程 env 未导出该变量
                → 改动即时生效·运行时进程零扰动）
```

**Smoke（S-N5 原查询·武装运行时·无重启）**:

| 项 | 结果 |
|---|---|
| step 1 | glm-5.3 OK（决策 call_tool·知识库检索） |
| **step 2** | **glm-5.3-flash OK（PASS）**——tool_calls=1（检索真实执行）·finish·**COMPLETED** |
| HTTP 429 / code1311 | **0**（obs 修复后仅 2 条 agent.llm_call 且全 OK） |
| needs_review（provider 类） | 0 |
| Provider Actually Used | **glm-5.3-flash**（obs `agent.llm_call` model 字段直证·非 flashx·无隐藏 fallback） |
| 交付 | 真实有据回答（引《保险公司偿付能力管理规定》三项条件——kb-v1 L1-11 检索命中） |
| 延迟 | step1 8.7s + step2 ~15.5s（flash 档·24.2s/轮·预期内） |

**观察（既有架构边界·与本次修复无关）**: 会话 agent 路径交付不经引用门/Claim
Support（K.28.6 S-1 已知边界·本次答案内容有据但路径治理与 QA 切片不同——
仅记录）。

**Phase16 隔离**（修复后核验）: authority 计数 0/0 不变 · kill ABSENT · 窗口/
标记/G11 不变（连进程都未重启——零扰动）· real traffic = 0 · Hybrid OFF ·
S2 OFF · Batch-2 NOT STARTED。

**Safety Layer 静态等价**: 8/8 组件 sha 与 PHASE16-BGE-M3-START 标记逐一相同
（claim_support/gate/loop/qa_agent/classifier/rules/authority/postgate）·
τ/taxonomy 冻结未动。

```text
FINAL STATUS: SN5_REMEDIATED
（Flash 正常 · 429=0 · step2 PASS · Phase16 未污染 · Safety Layer 未变 ·
  KB/BGE-M3 未动 · Rollback READY——不回滚）
```

证据: `tmp/obs/sn5_audit_probe_events.json`（11 事件全链）·
`tmp/obs/agent.jsonl`（flashx 5/5 EXHAUSTED + step1 OK 对照）·
直接探针（429 错误体全文）· 复现脚本 `tmp/sn5_probe.py` + `tmp/probe_flashx.py`
