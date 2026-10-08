# K.29-B-FIX · Phase 1 — Minimal System-Prompt Delivery Fix

Date: 2026-10-02 · Mode: IMPLEMENTATION（最小修复+回归·按 Owner 授权）
前置:Phase 0 审计（k29-bfix-prompt-delivery-audit.md·根因已确证）
Status: **PASS — 修复生效·全回归绿·零新增失败**

---

## 1. 修改文件

| 文件 | 变更 | 性质 |
|---|---|---|
| `runtime/grounding/loop.py` | +2 处插入（generate / generate_stream 各 4 行代码 + 注释） | **唯一生产改动** |
| `tests/runtime/test_k29bfix_prompt_delivery.py` | 新增（5 测试） | 测试 |

## 2. Diff 摘要（生产代码全文变更）

```diff
--- a/runtime/grounding/loop.py   (_GatewayProviderAdapter)
+++ b/runtime/grounding/loop.py
@@ generate()  (msgs 构建后·线程派发前)
+        # K.29-B-FIX Phase 1: forward request.system_prompt as the
+        # leading system message — same translation as runtime/llm/
+        # glm.py::GLMProvider (this adapter's own docstring names it
+        # as the pattern). The previous translation dropped it, so the
+        # QA slice's qa_system_prompt never reached the provider.
+        if request.system_prompt:
+            msgs.insert(0, {"role": "system",
+                            "content": request.system_prompt})
@@ generate_stream()  (同位置)
+        # K.29-B-FIX Phase 1: identical system_prompt forwarding as
+        # generate() above (streaming and non-streaming must agree).
+        if request.system_prompt:
+            msgs.insert(0, {"role": "system",
+                            "content": request.system_prompt})
```

- 与 `runtime/llm/glm.py:39-41`（GLMProvider）逐语义一致（审计 §6 提案原样实施）。
- **未改**:prompt 内容（qa-answer-v3 逐字不动·仍由 rules yaml 供给）·
  user message 构建与顺序·max_tokens/timeout/reasoning_effort·重试/
  看门狗/错误规范化·ggate/claim_support/gateway/build_gateway 缓存·
  K.26 段级门与 on_text 语义（system 前置在线程派发前完成）。
- `git diff` 全量 = 上述两块,无其它 hunks。

## 3. 测试结果（before / after）

| 套件 | Before（基线） | After | 变化 |
|---|---|---|---|
| 新增 delivery 测试（本阶段） | —（不存在） | **5/5 passed** | +5 |
| QA 流式/校准（k22+k26+p28b51） | 绿 | **36/36 passed** | 0 |
| Claim Support（script 模式 65 检查） | 65/65 | **65/65** | 0 |
| C2/资格（-k c2/rv4c2/qualification） | 绿 | **38 passed** | 0 |
| Intent（-k intent/c1/obs1） | 绿 | **53 passed** | 0 |
| **全电池**（tests/runtime + tests/contract） | **865 passed / 2 skipped** | **870 passed / 2 skipped** | **+5 passed·0 新增失败** |

（+5 = 本阶段新增 5 测试;运行方式 `python -m pytest tests/runtime
tests/contract -q`·AGENT_PG_PASSWORD 由 tmp/hd2.pgpass 预置避免 p24
temp-凭据环境噪声。）

新增测试内容（test_k29bfix_prompt_delivery.py）:
1. **T1** system_prompt 存在 → provider 收到
   `[{system: TEST_SYSTEM}, {user}]`（system 严格领先·内容逐字节）;
2. **T2** system_prompt="" 或 None → payload 与修复前逐字节一致
   （`[{"role":"user","content":"U1"}]`）;
3. **T3** user messages 内容/顺序/数量不变（3 消息混合角色）;
4. **T4** generate_stream 同样送达 system;**且** content delta 行为
   与 K.26 契约不变（reasoning 仍被消费、仅 content 转发）;
5. **T5** 生产 QA 链级:run_qa_turn（真实 classifier IntentResult +
   build_gateway 生产组合）→ provider 收到的 messages[0] 逐字节等于
   `config/qa-grounding-rules.yaml` 的 `qa_system_prompt`
   （qa-answer-v3·CITATION FORMAT 段到达）。

## 4. 未影响组件确认

| 组件 | 状态 | 证据 |
|---|---|---|
| Intent / Router / C1 | 未触碰 | git diff 仅 loop.py 两块;intent 套件 53 绿 |
| C2（证据资格） | 未触碰 | 38 绿;`_qualified_evidence` 零改动 |
| Claim Support | 未触碰 | 65/65;claim_support.py mtime/内容零变化 |
| Citation Gate（ggate） | 未触碰 | k22/k26 契约测试绿;gate.py 零改动 |
| qa-answer-v3 prompt 内容 | 逐字不变 | T5 断言 prompt 从 rules yaml 原样到达 |
| 模型参数 / WeKnora / KB | 未触碰 | 无相关 diff |
| K.26 流式语义 | 不变 | T4 + test_k26 12 项绿 |
| retry/watchdog | 不变 | test_p28b51 watchdog 三测绿 |
| HYBRID_ANSWER_ENABLED | **OFF（未触碰）** | 零 env/配置改动 |

行为影响面（预期内·与 K.29-B A2 诊断一致）:QA/ProductQA 生成轮的
attempt 1 起将收到引用格式指令——引用完整度上升、no_citation 违规
下降、部分拒答原因向 claim_support 迁移（安全方向;量化待 Phase 3
benchmark 重跑）。

## 5. Rollback 方法

- 逐行:删除 loop.py 两处 `if request.system_prompt:` 块（各 4 行,
  注释一并）→ 行为逐字节回到修复前（T2 测试即旧形态断言）。
- git:`git checkout -- runtime/grounding/loop.py`（该文件修复前
  worktree == HEAD 24082d5·干净基线）。
- 新增测试文件独立,可保留（T2 在回滚后仍应通过——它锁定旧行为）。

## 6. Phase 1 STOP

按任务书:未重跑 K.29-B benchmark·未开 Hybrid·未开 Shadow·未修其它
债务（ws/metadata 判定债·OD-H3·B6 等全部不动）。**等待 Owner 决定
进入 Phase 2（=任务书的 Phase 3 benchmark 重跑——A 臂重测对照 A2）。**

---

```
PHASE 1: PASS — 4-line forwarding fix live; 5/5 new tests;
36+65+38+53 targeted suites green; full battery 870+2
(baseline 865+2 + 5 new, zero new failures). STOP.
```
