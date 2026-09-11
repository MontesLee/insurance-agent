# Client Intake Skill — 测试案例索引

> 版本：v1.1
> 规则来源：以 [SOP.md](file:///D:/Workspace/insurance-agent/01-client-intake/SOP.md) 为唯一真值。
> 评估方式：以 [EVAL.md](file:///D:/Workspace/insurance-agent/01-client-intake/EVAL.md) 的 Hard Fail + Assertions + 六维评分为准。

---

## 执行说明

每个 Case 的标准流程：

1. 读取 `SOP.md`
2. 初始化或清空：
   - `CLIENT_PROFILE.md`
   - `CONVERSATION_LOG.md`
   - `PENDING.md`
3. 粘贴当轮客户原文
4. 让 Skill 执行
5. 核对：
   - JSON 输出
   - `CLIENT_PROFILE.md`
   - `CONVERSATION_LOG.md`
   - `PENDING.md`
6. 按 `EVAL.md` 执行评估
7. 未达标则改规则并重跑同一轮

补充原则：

- Case 优先验证行为结果、状态转换和契约是否满足
- 不应把 QID、问题原文、唯一问题主题等实现细节过度写死
- 若存在多个同等合法实现，优先写成主题级断言或 `question_intent_one_of`

---

## Case 列表

- [CASE_001.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_001.md)
  标准三口之家，测试基础提取、Completion Check 与最小追问。
- [CASE_002.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_002.md)
  客户先问产品，测试边界与引导。
- [CASE_003.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_003.md)
  创业者与多轮对抗，测试状态继承与反问处理。
- [CASE_004.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_004.md)
  Dirty Input，测试模糊输入与 inferred 白名单。
- [CASE_005.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_005.md)
  客户跳着回答，测试 ignored 状态、优先级重算与非机械追问。
- [CASE_006.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_006.md)
  客户修正旧信息，测试 Profile 只保留最新值、Log 保留历史、Conflict Notes 记录修正。
- [CASE_007.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_007.md)
  Pending 完整生命周期，测试 `pending -> received / declined / expired` 与 `related_qid` 同步。
- [CASE_008.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_008.md)
  P0 Hard Required 被连续忽略，测试“不降级但不机械重复”的追问策略。

---

## 当前建议执行顺序

1. 先跑 `CASE_001 / Round 1`
2. 分数达到 A 或至少 B 后，再推进 `Round 2`
3. 跑通 `CASE_001` 后，优先进入 `CASE_002`
4. 再跑 `CASE_005`
5. 然后补 `CASE_006 / CASE_007 / CASE_008`
