# Execution Trace (Step 4 · Phase 2)

> 统一执行轨迹：把 Agent 的每一次行为落成**结构化、可查询**的记录，
> 让「这个 Case 为什么最后没推荐产品？」这类问题**看一眼 trace 就能回答**（spec §6）。

代码：`workflow/trace.py`（记录器）· `workflow/orchestrator.py`（发射点）· `workflow/checkpoint.py`
测试：`tests/workflow/test_step4_phase2_trace.py`（17 项，全绿）

---

## 1. 为什么需要它

Step 3 已有 `state["events"]`（append-only 文本日志）与 `CaseState`/`Task`/Eval。
但文本日志回答不了「为什么」——它只有 "ERROR"。Phase 2 在其上加一层结构化 trace：

```
Customer → Orchestrator → CaseState → Skill Graph → Artifacts → Eval → Repair → Checkpoint → Report
                                   ▲
                              Execution Trace（贯穿每一跳）
```

**定位原则**：trace 是**观测层**，不做任何业务判断，也不改变控制流。任何 Skill / 编排逻辑都不读 trace 做决策。

---

## 2. 事件词汇表（spec §5，15 个）

| 事件 | 触发点 |
|---|---|
| `CASE_STARTED` | `orchestrator.seed_case()` 建立 CaseState |
| `TASK_CREATED` | `workflow/tasks.py::init_tasks()` 每个 stage 建任务 |
| `TASK_STARTED` | `_execute_stage()` 每轮 attempt 开始 |
| `SKILL_STARTED` | 同上（含 `input_artifacts` 的 ART-ID 列表） |
| `SKILL_COMPLETED` | stage 通过 Eval 并落 artifact 后；**seeded（executor=provided）阶段在 `seed_case()` 内也发一条** |
| `EVAL_STARTED` / `EVAL_COMPLETED` | `eval_engine.evaluate()` 前后，`EVAL_COMPLETED` 带 `eval_status` |
| `REPAIR_STARTED` / `REPAIR_COMPLETED` | `repair.plan/apply` 前后 |
| `CHECKPOINT_SAVED` | `checkpoint.save()` |
| `CHECKPOINT_LOADED` | `checkpoint.load()` 校验通过后 |
| `TASK_FAILED` | 任一轮 attempt 失败（Eval FAIL 或执行/服务异常），`detail` 带**根因全文** |
| `CASE_WAITING` | 信息不足/冲突，停在 `WAITING_FOR_USER` |
| `CASE_NEEDS_REVIEW` | 人工闸门暂停 **或** Repair 耗尽转人工 |
| `CASE_COMPLETED` | `next_runnable()` 返回 None，case 正常收尾 |

---

## 3. 记录结构（spec §4）

每条记录都带全部字段（缺省为 `null` / `[]`）：

```json
{
  "trace_id": "TRACE-9F3A2C1B",
  "case_id": "case-004-trace",
  "task_id": "TASK-006",
  "skill": "product-candidate-provider",
  "event": "TASK_FAILED",
  "attempt": 1,
  "input_artifacts": ["ART-004", "ART-005"],
  "output_artifact": null,
  "eval_status": "ERROR",
  "duration_ms": null,
  "timestamp": "2026-09-15T02:15:57.077+00:00",
  "detail": "knowledge-search: EVIDENCE_EVAL_FAIL[EVAL-006]: required_non_empty(empty: payload.evidence); ..."
}
```

- `duration_ms`：`SKILL_COMPLETED` 记录一定带**数值**。本地执行的 stage 为真实耗时；
  seeded（provided）阶段为 `0.0` 并在 `detail` 标注 `not executed locally`（如实表示"本地未执行"，不伪造耗时）。
- `trace_id`：每条独立（`TRACE-<8hex>`），用于跨系统关联。

---

## 4. 存储与镜像

| 位置 | 用途 |
|---|---|
| `state["trace"]` | 随 CaseState **一起 checkpoint**（快照/恢复天然带上 trace） |
| `<checkpoint_root>/<case_id>/trace.jsonl` | 逐行 JSONL 外置镜像，供离线分析/Phase 9 性能统计 |

镜像在 `orchestrator.run()` 开始时 `register_case()` + `dump_jsonl()`（重写全量，天然幂等，
resume 重复调用不会产生重复行），之后每条 emit 追加。

> case 目录与 `case_state.json` 同级（`state/store.py::case_dir`），便于打包一个 case 的完整证据。

---

## 5. 关键能力：让"为什么"可见（spec §6）

最初的实现只在失败时记录 `failed=execution`，**根因不可见** —— 这正是 trace 存在的意义所在，属于真实缺陷，已修：

1. 失败路径新增 `TASK_FAILED`，`detail` 携带**完整 reason**；
   `eval_status` 区分 `FAIL`（Eval 判负）与 `ERROR`（执行/服务异常）。
2. `REPAIR_STARTED.detail` 由 `failed=<check_id>` 扩展为 `action=…; failed=…; reason=<全文截断>`。

### 展品：case-004（空知识库 → 证据不足）

```
CASE_STARTED        workflow=insurance-analysis
TASK_CREATED   ×8
SKILL_COMPLETED  client-intake / requirement-analysis / risk-analysis   (seeded, 0.0ms)
SKILL_STARTED  coverage-gap-analysis
EVAL_COMPLETED coverage-gap-analysis  eval_status=PASS
CHECKPOINT_SAVED  CP-001
...
TASK_FAILED    product-candidate-provider  ERROR
  knowledge-search: EVIDENCE_EVAL_FAIL[EVAL-006]: required_non_empty(empty: payload.evidence);
                    provenance_evidence_document_chunk(no nodes at payload.evidence[])
REPAIR_STARTED product-candidate-provider  action=RERUN_FROM_UPSTREAM; reason=knowledge-search: ...
TASK_FAILED    #2 … (EVAL-007)
REPAIR_STARTED #2
TASK_FAILED    #3 … (EVAL-008)
CASE_NEEDS_REVIEW  repair_exhausted: product-candidate-provider
```

一眼可读的事实链：
**知识检索无证据 → 局部 Repair 重跑上游 2 次仍无证据 → Repair 耗尽 → 转人工**，
且**没有**任何用模型记忆补知识的痕迹（Artifact 未产出）。这正是 spec §6 想要的效果。

---

## 6. 与其它层的关系

- **不改控制流**：trace 全部是旁路写入；`trace.py::emit` 内部 try/except，写失败也绝不影响 Case 运行。
- **不改已有事件日志**：`cs.record_event()`（`state["events"]`）保留，兼容既有测试；
  trace 是叠加的更强结构化视图。
- **服务 Phase 9（Observability）**：`duration_ms` + `SKILL_STARTED/COMPLETED` 计数即可回答
  「一个 Case 跑完多少次 Skill 调用」、每 Skill 延迟、Repair 次数。
- **服务 Phase 11（Trace Viewer）**：JSONL 直接渲染时间线。

---

## 7. 验证

`tests/workflow/test_step4_phase2_trace.py`（**17/17**）：

- 结构完整性：每条记录含全部 spec §4 字段；
- 时序：`SKILL_COMPLETED.duration_ms` 为数值、`output_artifact` 已设置；
- 镜像：`trace.jsonl` 存在、是合法 JSONL、行数 ≥ `state["trace"]`；
- 终局语义：happy path 以 `CASE_COMPLETED` 收尾；证据不足 case 以 `CASE_NEEDS_REVIEW` 收尾；
- **可解释性**：失败 case 存在 `TASK_FAILED` 且 `detail` 命名根因，且根因可归因到 evidence / knowledge-search。

该测试**复用** `test-cases/e2e/full-agent/run_full_agent_e2e.py` 的 seed / mutation / gate-approval
辅助函数（按路径 import），确保 trace 由与 Full-Agent E2E **完全相同**的执行产生，避免测试与真实链路漂移。
