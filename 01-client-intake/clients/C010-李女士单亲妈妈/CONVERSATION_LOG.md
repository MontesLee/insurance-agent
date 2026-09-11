# Conversation Log

> 角色：保存历史问答、QID 注册表、逐轮原文
> 不作为长期事实源

---

## 使用规则

1. 不把本文件当作最终客户事实
2. 所有历史轮次都保留，不覆盖
3. 新问题必须先在 Asked Questions Registry 注册，再出现在输出里
4. 客户修改旧信息时，先记录在 Round History，再由 `CLIENT_PROFILE.md` 更新最新值
5. 对于每个新问题，除了问题原文，还应记录标准化的 `Question Intent`

---

## 1. Asked Questions Registry

| QID | Priority | Question Intent | 问题原文 | 首次出现 Round | 当前状态 | 客户回答原文 | Related Pending ID | 最后操作 Round |
|-----|----------|-----------------|----------|----------------|----------|--------------|--------------------|---------------|
| | | | | | | | | |

### 状态说明

- `unanswered`：问题刚提出，尚未进入下一轮客户输入
- `answered`：客户已明确回答，不得重复问
- `declined`：客户明确拒绝，不得重复问
- `pending`：客户承诺后补，按 `PENDING.md` 节奏提醒
- `ignored`：已进入下一轮但客户跳答，后续可再问但不得机械重复

---

## 2. Round History

### Round 0

- 时间：[YYYY-MM-DD HH:MM]
- 事件：初始化对话日志（Regression Script R0 Reset）
- 客户原文：N/A
- 本轮新增 confirmed：无
- 本轮新增 inferred：无
- 本轮新增 pending：无
- Completion Check：未开始
- 备注：等待 Round 1

---

## 3. Conflict Notes

> 客户前后说法出现冲突时，写在这里，方便后续核对。

- [空]