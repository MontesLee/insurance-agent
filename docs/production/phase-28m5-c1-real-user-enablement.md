# Phase 28.M5-C.1 — Real User Traffic Enablement & First-Party Observation 报告

Date: 2026-09-25 · 窗口 15:44–16:05Z · 零代码改动（仅 docs/tmp 证据）。
授权：Owner M5-C.1 Prompt（真实用户流量开放 + 第一方观察）。

## 1. Executive Summary

- **Web UI 接入：PASS** — Owner 既有的 vite dev server（PID 39456，
  2026-09-24 21:08 启动，`web/node_modules/vite --port 5173`）经
  `/api` 代理连通 :8000；`UI→vite proxy→:8000→Intent→Router(full)→
  Agent→既有脊柱→交付` 全链经两轮真实浏览器操作验证贯通。
- **Runtime：PASS** — :8000 = 当前代码 + Owner 授权 full 灰度
  （15:35:22Z 重启实例，health LIVE，无竞争实例）。
- **Full Authority 生效：PASS** — 两探针 shadow 记录
  `fired=true reason=authority`（product-qa / plan）。
- **WeKnora production-ready：NO** — 实例自报 `knowledge_provider=mock`、
  `weknora_url_configured=False`、`weknora_kb_configured=False`
  → **§5 STOP-1 触发：不开放真实用户、不以 mock 知识冒充生产验证，
  HD-2 BLOCKED**。
- **REAL_USER：0**（实例 bus 计数=2=全部为本阶段脚本探针）。
- **真实用户证据：无**（观察窗口未开放——前置缺失）。
- **Incident：NONE**（零不安全交付；零跨案；gate 全程 fail-closed）。
- **回归：backend 728/729**——唯一失败=planning 基线 tripwire 的
  **日历滚动敏感**（`governance.as_of` 当日字段跨本地午夜变化；
  根因完整取证见 §12.1，非行为回归，守卫未动）；B4/M4/M3/web/tsc
  全绿。
- **最终状态：`BLOCKED — PREREQUISITE MISSING`**（WeKnora/HD-2 为主；
  另记录 User-Space 面缺口——当前 UI 为内部观测台，见 §4/§8）。

**对 M5-C 的一处如实更正**：M5-C 曾以"web UI 5173 未运行"作为
REAL_USER=0 的辅助论据；本阶段发现 vite 监听 `[::1]:5173`（IPv6-only，
2026-09-24 21:08 起）——M5-C 的 127.0.0.1 探测方式漏检。M5-C 的
REAL_USER=0 结论**不受影响**（由实例 bus runs=6=探针独立证明），但
"UI 未运行"表述不准确，以本报告为准。

## 2. Environment

| 项 | 值 |
|---|---|
| Runtime | 127.0.0.1:8000，PID 38120，`python -m runtime.server --port 8000`（标准命令），创建 2026-09-25T15:35:22Z（=M5-C 恢复的灰度实例） |
| Authority | 运行级 `INSURANCE_AGENT_ROUTER_AUTHORITY=full`（进程 env 注入；**代码默认 slices 未变**——`runtime/router_authority.py` 空/缺省→slices） |
| Slice flags | 未设置（.env 无任何 SLICE 变量；QA=D4 默认 ON，PRODUCT/PLAN=默认 OFF，均被 authority 覆盖） |
| Web UI | `[::1]:5173`，PID 39456 node vite（Owner 昨日启动的进程，本阶段未触碰），`/api`→`http://127.0.0.1:8000` 代理 |
| 知识 | **mock 治理组合**（weknora 三变量全缺：URL/KB/API_KEY） |
| LLM | live glm-5.3（.env；窗口内 2 次调用 3997 tokens 全成功） |
| Runtime mode | demo（非 strict、json 后端）——如实记录的环境限制 |
| 代码 | HEAD 9407a84 + 未提交跨度 27.7.6-D..F..28.M5-C（与 M5-C 相同；本阶段零改动） |
| 竞争实例 | 无（8100-8199 无监听；仅一个 :8000） |

## 3. User Traffic Classification（15:44–16:05Z 窗口）

| Traffic Type | Count | Included |
|---|---:|---|
| REAL_USER | 0 | YES（无可计入者） |
| DEVELOPER | 0 | NO |
| SCRIPTED_PROBE | 2 | NO |
| SYSTEM_TEST | 后台回归进程内流量（不触 :8000，只写共享 shadow.jsonl） | NO |
| OPERATOR | 0 | NO |

判定依据：实例 `/api/health` bus 计数自 15:35Z 重启后 **runs=2 ==
恰好 U1/U2 两探针**（chat_7054c08f / chat_e039d892，bridgic-browser
驱动=脚本验证请求）。**INSUFFICIENT LIVE SAMPLE = YES。**

## 4. Routing Observation（探针口径，经真实 UI 路径）

| 探针 | 消息 | Intent（rule） | slice_decision | 结果 |
|---|---|---|---|---|
| U1 | P001 的等待期是多少？ | product_qa conf=1.00 | product-qa · fired · **authority** | refused(citation)→QA_REFUSED 诚实拒答 |
| U2 | 我想给孩子做一份保险规划。 | insurance_plan conf=1.00 | plan · fired · **authority** | 规划首轮信息采集（澄清问题） |

wrong-agent 0 · unexpected route 0 · flag 触发 0 · LLM/前端选 Agent 0。
**UI 用户可见契约审计（Step 4，核心发现）**：当前「对话」面是
Phase-1 时代 observability 控制台，默认暴露——

1. `⚙ Developer Mode` 开关（`ChatLayout.tsx:244` 恒渲染）；
2. 顶部 `Dashboard` / `Developer` / `审核队列` 入口（Operator/Developer 面）；
3. 默认 Run inspector 裸露 `run_id` / `case_id`（run_03771136 /
   agentcase-03771136 实测可见）+ 原始事件名（run_started/qa_answered…）；
4. 演示 case 下拉（bm-* 内部 id）+ Agent 模式下仍显示误导标签
   「Portfolio Demo Mode · bm-complete-001」（实际走 live glm Agent 链）；
5. **QA 轮渲染缺陷**：QA_REFUSED 轮被套上规划时代模板——「分析完成」
   标题 + 8 阶段全空清单 + 侧栏「📄 客户保险需求分析报告」卡片
   （**服务端零 artifact，纯模板虚构**；根因 `chatState.ts:210` 对
   completed 一律返回报告话术 + `ChatLayout.tsx:93/113` 硬编码标题；
   28.B 仅同步了事件可接收性，UI 状态机未改——当时设计决定）。

正面确认：拒答文案与规划澄清问题均**真实、完整、自然语言**呈现；
会话 reload 恢复 PASS；SSE/轮询正常；console 仅 2 条无害 404
（被放弃空会话槽 chat_3be945ab 恢复请求）。

## 5. QA Observation（本窗口）

未开放真实用户观察（STOP-1）。探针覆盖：product 路径 1 轮（U1，
refused/citation，74.6s）；knowledge-QA 路径本窗口未探（M5-C C1 基线：
refused/citation）。grounded 0 · unsafe delivery **0**（拒答=安全拒答）。

## 6. Product QA Observation（U1）

目录锚点 P001 解析正确（intent rule:product_qa_catalog_name）→
Product QA agent → 证据检索 → 生成两轮均未过 citation gate →
**fail-closed 拒答**（"本次生成的回答未能通过引用校验……为避免误导，
本次不作答。"）· 目录缺失事实 0 · 推荐泄漏 0 · 无支撑产品事实交付 0。

## 7. Planning Observation（U2）

identity=insurance-planning-agent（经 Router authority）· 首轮信息
采集（CLIENT_ADVISORY）：5 个自然语言澄清问题（年龄/健康/已有保障/
预算/父母保障）· **零产物、零编造方案**（信息不足不生成=安全正确）·
零跨案（单 case_id）· run 19.0s completed(waiting)。

## 8. Safety

```text
hallucination delivery   = 0（gate 拒）
unsupported product fact = 0
recommendation leakage   = 0
cross-case leakage       = 0
internal ID leakage      = UI 面存在（run_id/case_id/原始事件名默认可见
                            ——Phase-1 观测台设计，见 §4；非事件/数据层泄漏）
evidence bypass          = 0
```

## 9. Performance

| 指标 | 值 |
|---|---|
| Intent/Router 开销 | 15ms / 0ms（rule_fast_path；p50≈0，可忽略） |
| U1 total（refused+regen） | 74.6s（llm 单调用 p95 50.0s；≤240s 预算，零超时） |
| U2 total | 19.0s |
| 检索（mock） | 12.2ms |

延迟全部 live 模型主导；router/代理开销可忽略（vite 代理链路无感）。

## 10. Citation Model-fit Observation（只观察，未修）

U1 再添一例同型：长答案漏引 → 两轮再生成仍不合规 → gate 拒答。
与 M5-A/B/C 完全同模式（模型适配/UX 问题，**非 Router 缺陷；gate
零触碰**）。窗口内 grounded/合规交付 0/1 产品轮（小样本无统计意义）。
拒答文案用户可见且诚实——"未交付"≠"错误交付"。

## 11. Rollback

触发：无（零 incident、真实用户窗口未开放）。就绪：既有程序
（unset `INSURANCE_AGENT_ROUTER_AUTHORITY` + 重启；M5-C 于 15:35Z 在
**本端口**刚演练过，QA→D4 flag / product+plan→legacy / unknown 不变）。
**实例保持 Owner 授权 full 灰度继续暴露**；Web UI（Owner 进程）保持
运行；两者均未被本阶段触碰。

## 12. Regression

```text
backend：FAIL（1/729）—— 728 passed + 1 failed
  失败：test_p28b6_preflight.py::test_planning_baseline_matches_committed
  （GC-PL-G01 artifact_hashes[3]=knowledge-evidence）
B4：PASS（套件 7/7；17 golden cases 全含） · M4：PASS 9/9 · M3：PASS 7/7
  （三套件 battery 内绿 + 定向复跑 23/23 绿）
web：PASS — 148 passed + 2 skipped（18 文件）
tsc：PASS — tsc --noEmit clean
```

### 12.1 唯一失败的根因（完整取证，非忽略）

- **现象**：仅 knowledge-evidence artifact 的 stable-hash 不等；其余
  全等（run_status / event_chain / eval_verdicts / risk_signals /
  artifact_count / 另外 8 个 artifact 哈希）。
- **字段定位**：evidence 条目 `governance.as_of` = **当日日期
  （date-only）**。基线采集于本地 2026-09-25（B6）；本阶段 battery
  23:58:19（本地）启动、跨本地午夜进入 09-26 → as_of 由 09-25 滚动为
  09-26 → 哈希变化。复跑（本地 09-26 00:07）稳定复现 ✓。
- **为何历史全绿**：B6→M5-C 的全部 battery 均在本地 09-25 内执行；
  这是第一个跨本地午夜跑 tripwire 的 battery。
- **为何归一化救不了**：B4 归一化明确**不洗裸日期**（"bare dates
  untouched——effective windows 是语义"，B5 时代设计决定）；
  `runner.py:121` 对 artifacts 只过 `nm.normalize`（ISO 时间→TS，
  如 retrieved_at 稳定），date-only 的 as_of 按设计保留。
- **与本阶段行为无关**：零代码改动（diff 审计 ✓）· 测试 hermetic
  （in-process + NO_DOTENV）· 字段来自系统时钟 · 生产探针在独立
  进程/run 目录。**非行为回归——tripwire 日历敏感设计的首次暴露。**
- **处置**：守卫未动（改 tripwire 归一化或重采基线均超出本阶段
  wiring 范围，且重采只会把失败推迟到下一个午夜）→ 记录为 Owner
  决策项（tripwire 日期归一化 / 冻结时钟注入 / 重采纪律）。取证
  工件：tmp/b6-tripwire-probe/（ignored）。

## 13. Diff Scope

```text
code changes:              NO（git tracked 集与 M5-C 完全一致）
allowed integration/config only: N/A（无需任何修复——wiring 本就正确）
architecture changed:      NO
frozen contract changed:   NO
```

本阶段仅新增 docs/报告 + tmp/ 证据（ignored）+ .agent/memory 簿记。

## 14. Live Sample Sufficiency

```text
REAL_USER = 0
INSUFFICIENT LIVE SAMPLE = YES
```

真实用户观察**未开放**（前置缺失，非样本不足问题）；探针 2 轮仅证
链路，不替代真实用户证据。

## 15. Final State

### `BLOCKED — PREREQUISITE MISSING`

主前置：**WeKnora 生产能力缺失（§5 STOP-1，HD-2 BLOCKED）**——
真实用户路径将使用 mock 知识，按阶段纪律不得作为生产验证开放。
次前置（记录）：**User-Space 面缺失**——当前 UI 为内部观测台
（Developer Mode/Dashboard/内部 id/原始事件默认可见），直接对
外部消费者开放违反 PRODUCT_VISION User/Developer 边界（CLAUDE.md
禁令 6）；需产品级 UI 决策（非本阶段可修的 wiring 范畴）。

## 16. Handoff

**已完成**：只读 preflight（含 M5-C「UI 未运行」误判更正）· :8000
实例验证（当前代码/full 灰度/无竞争）· Web UI 接入验证（Owner vite
进程 + 代理链路）· 真实 UI 两轮契约审计（全链贯通 + 用户面缺陷清单
+ 根因定位）· WeKnora 判定（STOP-1/HD-2）· 全量回归 · 报告。

**未完成**：真实用户开放与第一方观察（被 STOP-1 阻断）· 三业务路径
真实用户口径观察 · 真实用户 citation/延迟分布。

**已知风险**：① mock 知识上的一切"生产"结论无效（HD-2）；② UI
内部面直接暴露给外部用户=产品边界违规；③ QA 轮误导性模板（虚构
报告卡片）可能让用户误以为生成了报告；④ runtime_mode=demo（非
strict/json 后端）——生产化配置差距。

**未解决的 Model-fit 问题**：citation compliance 低（U1 再证；模型
档位实验 / 免责句豁免=gate 语义变更——均待 Owner 决策，gate 未动）。

**Owner 决策项**：

1. **HD-2**：配置 weknora env（URL/API_KEY/KB_ID）+ 治理语料——重开
   本阶段的第一前置；
2. **User-Space 面**：是否建设消费者专用 chat 面（或对现 UI 做空间
   隔离）——外部用户开放前的产品决策；
3. **真实用户范围**：若 HD-2 就绪，明确第一批真实用户是谁/范围
   （第一方 dogfood 或外部）与授权；
4. citation 缓解决策（同 M5-C 遗留）；
5. M5 Cleanup / Permanent Full Authority（同 M5-C 遗留，均未动）；
6. **planning 基线 tripwire 日历敏感**（§12.1）：日期归一化 / 冻结
   时钟注入 / 重采纪律——三选一决策（守卫语义变更需按三段式纪律
   处理）。
