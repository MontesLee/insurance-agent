# K.25-RV Final Report — Real User Verification

Date: 2026-09-27 · 验证主体：probe-alpha（SCRIPTED_PROBE 类——真实
pilot 栈·真实流量·如实标注非 REAL_USER 人类样本；真正人类用户复核
仍待自然流量）。

## Result

```text
FAIL（一项 FAIL 条件触发：Consumer 可见文本中出现内部 artifact ID
"ART-009"——规划路径 LLM 生成内容所含，非 K.25 引入的回归；
其余全部 PASS。按本阶段规则：记录不修复，STOP）
```

## Deployment

```text
Old code: backend startup 2026-09-27T03:34:43Z（K.24/K.25 前）
New code: 重启后 startup 2026-09-27T11:10:49Z（PID 38560·K.7+F1+
  F2+K.22+K.24+K.25 全载）·frontend :5273 vite 持续服务最新前端
  （served activity.ts 含 composing×6 实证）
Restart: Owner 授权执行（隔离/WeKnora/PG/auth/identities 全保持）
Verification: K.24 deadline 模块在·K.25 tool_* 事件实发（R1/R3
  事件链实证）·K.17/K.20/K.22 前端代码为 served 版本
```

## R1 QA（"我的百万医疗险和重疾险有什么区别？"）

```text
Result: PASS（含 R4 语义——语料缺口诚实拒答）
Event chain（5.0s）：run_started → intent_classified{insurance_qa}
  → tool_started{knowledge_search} → +4.8s tool_completed →
  qa_answered → run_completed{QA_REFUSED}
Consumer progress（投影）：✓已理解你的问题 → ●正在核实相关资料
  (4.8s) → ✓已完成资料核对 → ●正在整理回答(0ms 即闭合) →
  ✓已整理回答 + 拒答文案
Terminal: completed/QA_REFUSED · Safety: 拒答文案零内部信息 ✓
发现（记录不修）：拒答轮 composing 0ms 闪现（qa_answered 同毫秒
  关闭）——语义可接受（答复已整理=拒答文案已产出）措辞可未来校准
```

## R2 Planning（两轮家庭规划·289s+265s）

```text
Result: PASS（进度机制）+ **安全发现（见 Result）**
Event chain（turn2，80 事件）：run_started → intent → 11×
  agent_step/9×agent_decision → 10×tool（1×tool_failed 后步内
  稳定）→ 8×stage_started[全 8 阶段真实顺序] → 9×eval_passed →
  9×artifact_created → run_completed{COMPLETED}
Consumer progress：✓/● 阶段行真实推进 + ○ pending（真实
  stage_order——未启阶段空心显示·首 stage_started 前零模板）·
  verify 行（eval）·report 行
Artifacts: 9/9 VALID 含 insurance-report ✓ · ref 发行+解析
  47,825B ✓ · terminal: completed/COMPLETED
Safety: **发现——最终答复含"（ART-009）"**（详见 Finding）
```

## R3 Long Generation（"重疾险的等待期一般是多久？"·70s）

```text
Result: PASS
Event chain：run_started → intent → tool_started → +4.5s
  tool_completed → **+63.7s** qa_answered{citation_gate_rejected}
  → run_completed{QA_REFUSED}
Consumer progress：✓已理解 → ●正在核实相关资料(4.5s) → ✓已完成
  资料核对 → ●正在整理回答(63.7s 生成期) → [12s 起心跳共存=
  正确：该窗口无事件无 delta，心跳为 liveness fallback] → 拒答
K.22 validated streaming: **未过门零 delta**（durable 事件零
  agent_stream_delta + failure=citation_gate_rejected——构造保证
  实证：门拒内容从未到达 Consumer）✓
Terminal: completed/QA_REFUSED · Safety ✓
```

## R4 Refusal/Failure

```text
Result: PASS（R1 即真实拒答场景）
Generation correctly suppressed: retrieval allowed=0 → 生成未尝试
  → 零 delta·零"正在生成回答"伪造（qa_answered 与 tool_completed
  同毫秒——无可伪造窗口）✓
```

## Heartbeat

```text
PASS——R3 的 63.7s 生成静默窗：真实阶段行（●正在整理回答）在位；
  >12s 无事件无 delta → 心跳共存（liveness fallback 语义正确）；
  事件到达即重置（K.17 测试+本链时间戳一致）
```

## Terminal Freeze

```text
PASS——四场景全部到达 terminal 后零后续事件（后端 _finish_run 幂等
  +前端折叠 terminal 冻结——U7/I10 测试+live 事件链尾部一致）
```

## Safety

```text
CoT: 0 · Reasoning: 0 · Internal ID: **1 处（ART-009·R2 生成内容）**
Tool: 0 · Skill: 0 · Agent: 0 · Raw Event: 0 · Exception: 0
（K.25 自身载荷/事件/投影标签全清洁；泄漏源自规划路径 LLM 答案文本）
```

## Finding（记录·不修复）

```text
Finding: R2 最终答复含"（ART-009）"——内部 artifact ID 进入消费者
  可见聊天文本
Root cause: 规划脊柱的 tool 结果（含 ART-xxx 标识）进入 LLM 上下文
  → glm 生成答案时引用了该标识（K.7 时代即存在的内容级路径；
  非本次 K.25 事件/投影/载荷引入——K.25 各载荷扫描全清洁）
Impact: 内部 ID 可见性（非机密/非跨用户/非 CoT）；违反 Consumer
  Surface"无 artifact_id"规则
Recommended fix（未来 Owner 授权）: ①tool→LLM 内容投喂层剥离
  ART-xxx 标识（源头）；或 ②交付层对 artifact-id 模式做 E-2 式
  投影净化（需谨慎不误伤正文）——属提示词/内容卫生轨道
```

## Regression

```text
K.17: PASS（活性行+心跳语义 live 一致）· K.20: PASS（流式气泡代码
  served；本轮 QA 门拒/规划无 delta 场景不触发——机制由测试锁定）
K.22: PASS（门拒零 delta 实证）· K.24: PASS（模块加载+运行在
  deadline 内正常完成；battery 808+2）
```

## Limitations

```text
①验证主体为 probe（SCRIPTED_PROBE）——真实人类用户 R1-R4 复核
  仍待自然流量（不冒充）
②composing 为派生粒度（已知·不优化）
③拒答轮 composing 0ms 闪现（措辞校准=未来小项）
④ART-xxx 泄漏（上述 Finding——修复需授权）
```

## Conclusion

```text
K.25 技术实现：闭环（事件链/投影/心跳/终态冻结/K.22 抑制全部 live
  实证）。K.25 real-user verification：进度与安全机制层面闭环；
  但安全扫描发现一项【既有】内容级内部 ID 泄漏（ART-009）——按
  本阶段 FAIL 条件判定 FAIL，如实归因（非 K.25 回归），修复留待
  Owner 授权。
```

## Owner Decision

```text
①ART-xxx 内容卫生修复轨道授权（源头剥离 vs 交付净化）
②真实人类用户 R1-R4 复核窗口（自然流量）
③拒答轮 composing 措辞校准（可选小项）
```

STOP
