# K.29-B-FIX · Phase 0 Audit — QA Chain System-Prompt Delivery

Date: 2026-10-02 · Mode: **AUDIT ONLY**（零代码改动·本文件为唯一产出）
Status: **ROOT CAUSE CONFIRMED — minimal fix proposal ready（待 Owner
确认后进 Phase 1）**

Architecture Impact Detected: 本修复将触碰 `runtime/grounding/loop.py`
（Runtime 生成链·46dbe0f/24082d5 封印 span）。授权链 = Owner 任务书
K.29-B-FIX（Phase 1 预授权,以本审计确认为条件）+ K.29-B 报告 §3
发现。红线（不动 Claim Support/citation gate/Intent/C2/taxonomy/
知识库/prompt 内容/模型参数）全程遵守。

---

## 1. Root Cause（一句话）

**`runtime/grounding/loop.py` 的 `_GatewayProviderAdapter` 在把
`LLMRequest` 翻译成旧协议 provider 调用时,只转发了
`request.messages`,丢弃了 `request.system_prompt`** —— 因此 QA 切片
经 `generate_grounded` 传入的 `qa_system_prompt`（qa-answer-v3）从未
作为 system message 到达 GLM。

同仓库存在正确实现的参照物:`runtime/llm/glm.py::GLMProvider.generate`
（glm.py:39-41）在做同一翻译时**前置了 system message**;适配器的
docstring（loop.py:30-34）自称「Same pattern as
runtime/llm/glm.py::GLMProvider」——但漏抄了 system_prompt 前置这
一步。**这是翻译层的不完整拷贝,不是设计决定。**

## 2. Call Path（逐跳·代码锚点）

```
Intent classify（SEALED·不受影响）
  → Router / server.py:840-875（QA 切片 dispatch·不受影响）
  → run_qa_turn（runtime/qa_agent/agent.py:98·未跟踪 span）
      · agent.py:41-43  system_prompt(r) 读
        config/qa-grounding-rules.yaml generation.qa_system_prompt   ← 定义点
      · agent.py:217    gateway = build_gateway(provider)（生产不传 gateway）
  → generate_grounded（runtime/grounding/loop.py:226·封印）
      · loop.py:305-313 LLMRequest(messages=[user], system_prompt=…,
                                  max_tokens, timeout_s, metadata)   ← 注入点（正常）
  → LLMGateway.generate（runtime/llm/gateway.py:109·封印）
      · policy→PII(343-345 对 system_prompt 做凭据扫描=网关「知道」
        它)→rate→circuit→budget→retry → _do_generate(request)      ← 网关不注入
  → _GatewayProviderAdapter.generate（loop.py:40·封印·**缺陷点**）
      · loop.py:46-49  msgs = [m for m in request.messages]        ← **system_prompt 丢弃**
  → OpenAICompatProvider.generate(messages, tools)（model.py:126）
      · _payload_base(msgs) → HTTP body {"messages":[…]}           ← **无 system role**
  → GLM
```

受影响面（共用同一适配器/同一 generate_grounded）:
- **knowledge-qa 切片**（insurance_qa + 受治理 unknown）
- **product-qa 切片**（product_qa_agent/agent.py:193 同样传
  system_prompt·slice DEFAULT OFF）
- **K.26 流式路径**（adapter.generate_stream 同样只转发 messages——
  运行探针证实,见 §3-2）

不受影响面:
- **Agent 规划环**（runtime/agents/executor.py:113-117 把 system
  prompt 作为 messages 内的 system role 直接构建——一直送达）
- **Intent LLM candidate**（无 LLMRequest.system_prompt 用法·OFF）
- C2 / Citation Gate / Claim Support（消费的是 evidence/answer,与
  prompt 送达无关——它们对「带引用文本」的判定不因本缺陷改变）

**attempt 2 部分恢复的机制**:loop.py:296-302 的 regen 反馈（含引用
格式指令）拼接在 **user message** 内——这是模型在 attempt 2 能部分
遵守引用格式的唯一指令来源;attempt 1 完全无指令。

## 3. 运行取证（进程内探针·2026-10-02 全新鲜执行）

| # | 探针 | 结果 |
|---|---|---|
| 1 | `_GatewayProviderAdapter.generate`（system_prompt="SYS-PROMPT-BODY"） | provider 收到 roles=`['user']`;system 未送达 |
| 2 | `_GatewayProviderAdapter.generate_stream`（同上） | roles=`['user']`;system 未送达;content delta 正常（流式功能本身完好） |
| 3 | `build_gateway(...)` **生产组合**（真网关+适配器+PII/rate/retry）经 `gateway.generate(LLMRequest(system_prompt=qa-answer-v3 文案))` | provider roles=`['user']`;网关正常返回;`"CITATION FORMAT"` 文案零出现 |
| 4 | 参照物 `GLMProvider.generate`（同 request） | roles=`['system','user']`;HTTP payload `[{system},{"user"}]`——证明「正确形态」在本仓库已有实现 |
| 5 | HTTP payload 复现（`_payload_base(adapter 路径 msgs)`） | 无 system role |

历史佐证（K.29-B 既有证据,不重复执行）:
- D-04 capture（10-01·按量端点·真 GLM）:attempt 1 = 0 个 [E#]、
  markdown/emoji 自由形态;attempt 2 = 9 个 [E#]（regen 反馈进入
  user message 后）。
- K.29-B A2 诊断臂（40 例×2 模型·提示词实达）:引用完整度
  0.246-0.273 → 0.372-0.401;no_citation 违规 main 35→1·flash 47→4;
  拒答主因迁移至 claim_support:unsupported（115/110）——**修复有效
  但不单独解锁 grounded**（该迁移=正确安全行为）。

## 4. Before / Expected Payload（探针实录）

**Before（现行生产）**——模型收到的完整 messages:

```json
[{"role": "user", "content": "User question: 重疾险等待期通常是多少天？\n\n
Evidence (governed, ACTIVE only):\n[E1] source: …\n…"}]
```

（qa_system_prompt 的 CITATION FORMAT/VALID/INVALID 示例等内容
**零字节**到达;attempt 2 仅在 user message 尾部附加 regen 反馈。）

**Expected（修复后;= glm.py 参照物形态）**:

```json
[{"role": "system", "content": "You are the Insurance QA Agent. Answer …
CITATION FORMAT (mandatory — output is machine-checked):\n- Cite with
HALF-WIDTH ASCII square brackets …"},
 {"role": "user", "content": "User question: …\n\nEvidence …"}]
```

prompt 内容逐字节 = `config/qa-grounding-rules.yaml`
`generation.qa_system_prompt`（qa-answer-v3·**不修改任何字**）;
user message 逐字节不变;模型参数（max_tokens/timeout/reasoning_
effort）不变。

## 5. 缺陷窗口（受影响历史）

- 缺陷随 `_GatewayProviderAdapter` 引入 = **K.26 真流式提交
  46dbe0f（09-27）**;loop.py 现工作树 == HEAD（24082d5·clean,
  `git diff HEAD` 空）。
- 自该时点起,生产 QA/ProductQA 每一生成轮的 attempt 1 均无系统
  提示词;受影响实证窗口 = 28.K27 观察至今的全部真实用户 QA 轮
  （全部拒答/诚实失败——fail-closed 方向,无不当交付）。
- K.26 之前（28.C-1 QA 切片诞生 09-26~09-27）:qa_agent 包属未跟踪
  span,**git 不可考证**;按 loop.py 封印历史,该早期窗口的交付形态
  UNVERIFIED（如实记录,不影响修复决策）。
- 需重读的历史结论:①28.B5.1 prompt 校准（假设送达而从未送达——
  其「校准有效」的 live 验证全部发生在无指令条件下的拒答一致性）
  ②D-04「prompt v4 无效益」（被测 prompt 未送达→结论无效）。

## 6. Minimal Fix Proposal（待确认后实施）

**改动点**:`runtime/grounding/loop.py` `_GatewayProviderAdapter` 的
`generate()`（~loop.py:46-49）与 `generate_stream()`（~loop.py:107-110）
两处,在构建 `msgs` 后、线程派发前各插入:

```python
if request.system_prompt:
    msgs.insert(0, {"role": "system", "content": request.system_prompt})
```

- 与 glm.py:39-41 参照物逐语义一致;合计 ~4 行。
- **不做**的事:不改 prompt 内容·不改 user message·不改
  max_tokens/timeout/reasoning_effort·不改重试/看门狗/错误规范化·
  不改 ggate/claim_support/gateway·不改 build_gateway 缓存逻辑。
- 流式语义:msgs 在线程派发前构建,insert 不触达看门狗/segmenter;
  K.26 的「段过同一门」契约不变（门在 provider 响应之后）。
- **回滚** = 还原这 4 行（`git checkout runtime/grounding/loop.py`
  或逐行 revert）;无配置开关需求（行为 = 恢复设计意图,非新策略;
  若 Owner 要求灰度旋钮可加 env 门,默认开——**不建议**,理由:这是
  缺陷修复而非行为策略,且 A2 已量化其方向安全）。

**Phase 1 测试计划**（新增,不锁旧错误行为——已核实现有
test_p28b51 watchdog 三测消息内容无关、test_k26 网关级不检查
messages,均不受影响）:
1. system_prompt 存在 → provider 收到 `[{system},{user}]`,system
   内容逐字节等于 request.system_prompt;
2. system_prompt 为空 → provider 收到 `[user]`（旧行为逐字节）;
3. user message 内容/顺序不变（含 regen 反馈拼接轮）;
4. streaming 路径同样送达（generate_stream 探针 + 现有 K.26 套件
   全绿）;watchdog/retry 语义不变（现有 test_p28b51 三测保持）;
5. run_qa_turn 链路级:capture provider 断言 qa-answer-v3 文案的
   CITATION FORMAT 段到达。

**Phase 2 回归面**:QA（test_k22/test_k26/test_p28b51/qa_agent 套件）
· Claim Support（65）· C2（8）· Intent（12+33）· 全电池 865+2
零新增失败。**Phase 3 重跑** = K.29-B A 臂（同语料/同模型/同评估/
同端点与超时偏差设置）对照 A2;B/C 臂不重跑（不受本修复影响——
B/C 本就直连 provider 且 system 在 messages 内）。

## 7. Stop-Condition Check（任务红线自检）

- 只处理 prompt delivery ✓（未动其它任何文件）
- 不开 Hybrid authority ✓ · 不改 Claim Support ✓ · 不改
  Intent/Router/C1/C2 ✓ · 不扩 taxonomy ✓ · 不新增 KB ✓
- 不改 production answer policy ✓（MODE-A 语义不变——修复使
  既有 prompt 按设计生效,策略本身零变化）
- HYBRID_ANSWER_ENABLED 保持 OFF ✓（未触碰）
- 可回滚 ✓（4 行·见 §6）

---

```
PHASE 0: COMPLETE — root cause confirmed at loop.py adapter
(system_prompt dropped in messages-protocol translation).
Minimal fix ready (~4 lines, glm.py-parity). STOP — awaiting
Owner confirmation to proceed to Phase 1 (implementation).
```
