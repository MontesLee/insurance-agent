# 04 — 问题优先级与 QID 状态机

不使用权重计算，不写 50/30/20。

只用离散规则：

| 优先级 | 规则 |
|--------|------|
| `P0` | 如果缺失会导致无法进入下一阶段，必须优先问 |
| `P1` | 对家庭责任或风险判断影响大，且回答成本低 |
| `P2` | 重要，但可以下一轮再问 |
| `P3` | 需要找资料、高成本获取、适合后补 |

每轮问题选择顺序：

1. 先看 `P0`
2. `P0` 没有时再看 `P1`
3. 然后 `P2`
4. `P3` 默认延后，不主动占据本轮名额

单轮提问规则：

- 最多 3 个
- 一问一个点
- 口语化，不像表单
- 优先回答成本最低的问题
- 已在 `Asked Questions Registry` 中标记 `answered / declined / pending` 的，禁止重复问

## 5.1 Asked Questions 状态定义

- `unanswered`
  已提出，客户尚未回应

- `answered`
  客户已明确回答，不得重复问

- `declined`
  客户明确拒绝回答，不得重复问

- `pending`
  客户明确承诺后续补充，不得重复直接追问，按 Pending 节奏提醒

- `ignored`
  客户未回答且转向其他话题，可在后续轮次重新提问，但不得连续两轮重复同一问题

## 5.2 Ignored 处理规则

同一 QID：

1. 第一次被忽略后，可在后续轮次重新提问
2. 不得连续两轮重复同一问题
3. 连续被 ignored 2 次后，自动降级优先级
4. 若该问题属于 P0 Hard Required，则不降级，但提问方式必须调整得更自然、更短

## 5.3 Pending 与 QID 关联规则

当一个已有 QID 的问题被客户明确承诺后补时：

1. 原 QID 状态更新为 `pending`
2. 在 `PENDING.md` 创建对应 Pending Item
3. Pending Item 必须记录 `related_qid`
4. 后续提醒不得创建新的 QID
5. 提醒行为仍视为对原 QID 的跟进
6. 客户提供资料后：
   - Pending Item 更新为 `received`
   - `related_qid` 更新为 `answered`
7. 客户明确拒绝提供：
   - Pending Item 更新为 `declined`
   - `related_qid` 更新为 `declined`
8. Pending 超过最大提醒次数后：
   - Pending Item 更新为 `expired`
   - `related_qid` 更新为 `ignored`
   - 不再主动提醒

补充规则：

若客户在**未被当前轮次显式追问**的情况下，主动承诺后续补某项资料，例如：

- “保单我晚点发你”
- “我回头把体检报告找给你”

也允许直接创建 `Pending Item`。

此时：

1. 可以直接在 `PENDING.md` 新增条目
2. 若需要统一追踪，可同步新增一个对应的 `Question Intent`
3. 该记录用于状态跟踪，不视为“重复追问”
4. 后续提醒仍不得创建新的重复 QID

## 5.4 Unanswered 与 Ignored 判定规则

- `unanswered`
  当前 QID 已提出，但尚未进入下一轮客户输入。

- `ignored`
  已进入下一轮客户输入，客户没有回答该问题，且输入内容明显转向其他信息或其他话题。

规则：

1. QID 在提出后的下一轮之前保持 `unanswered`
2. 一旦客户进入下一轮且未回答该问题：
   - 明确转向其他信息 -> `ignored`
   - 表示稍后提供 -> `pending`
   - 明确拒绝 -> `declined`
   - 已回答 -> `answered`
3. 不允许一个问题跨轮次长期保持 `unanswered`

### 5.4.1 每轮进入时的旧 QID 状态处理

处理新一轮客户输入前，必须先检查上一轮所有状态为 `unanswered` 的 QID。

逐个判断：

1. 客户明确回答 -> `answered`
2. 客户明确拒绝 -> `declined`
3. 客户承诺后补 -> `pending`
4. 客户未回答且明显转向其他信息 -> `ignored`

处理完成后，才开始本轮 Extract。

禁止存在跨越一个完整客户 Round 后仍保持 `unanswered` 的 QID。
