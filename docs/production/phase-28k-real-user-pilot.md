# Phase 28.K — REAL_USER Controlled Pilot 报告

Date: 2026-09-26（窗口开启 12:27Z–进行中）· 性质：Owner 已授权
D-03 → **REAL_USER isolated controlled gray pilot**（非正式生产发布）。
本阶段零产品代码改动（禁令清单全遵守：Router/Intent/Grounding/
Ownership/Governance/WeKnora 语义/auth/persistence/债务项均未触碰，
零 commit）。

## Executive Summary

- **Pilot 已部署并通过全量部署验证**：隔离实例 strict
  controlled_pilot · WeKnora 治理知识链（启动预检拒绝式验证）·
  Pilot Full Authority（临时，已记录，D-07 不变）· 11 凭据（8 受邀
  CONSUMER + 1 OPERATOR 值班 + 2 SCRIPTED_PROBE）。
- **真实用户窗口已开启**：访问口 http://localhost:5273（loopback，
  未公网暴露）。**截至本报告 REAL_USER 会话数 = 0**（如实——受邀
  用户由 Owner 分发 key 后进入；探针全部标记 SCRIPTED_PROBE 且数据
  已清零，绝不冒充真实用户样本）。
- **六类旅程机器全部以 SCRIPTED_PROBE 在本实例行为验证**：A/A2 知识
  QA（含 §15 允许状态标准样本：检索成功+引用门拒+安全拒答）·
  B 规划 intent 全脊柱→目录查无→诚实澄清 · C 全 8 阶段脊柱 6
  artifacts→质量门→needs_review 诚实升级（无假报告）· D 澄清文案
  自然零内部泄漏（turn-1）· E 拒答零幻觉零假产物 · F 真实产物+
  不透明 ref+下载+跨主体 404+随父撤销。
- **安全/治理 live 复证全 PASS**：跨用户五路 404 与缺失基线逐字节
  一致（无存在性 oracle）· ref≠授权 · 级联删除×3（含 waiting 态
  mid-lifecycle）· 审计纯元数据 · operator 职责读留痕。
- **P0=0 · P1=0**；**P2 四项**如实登记（最重要：needs_review 终态
  消息向消费者透出内部阶段名 `product_candidate_provider`——文案级
  缺陷，建议 Owner 在真实用户进入前裁决是否先修）。
- **unsafe delivery = 0 · cross-user exposure = 0 · internal leakage
  （P0 级）= 0**。

## Pilot Scope

```text
实例    后端 :8123（python -m runtime.server，strict）· 前端
        http://localhost:5273（vite [::1]，/api 代理 → :8123）
范围    仅受邀真实用户（5-10 目标；8 身份已备）· loopback 部署
        （未公网开放/未匿名/未开放注册）· 隔离于 :8000（保持停止）
        与开发 :5173（未触碰）
禁令    全程遵守（见 Git Scope：零代码改动）
```

## User Count

```text
provisioned  8 受邀 CONSUMER 身份（pilot-user-01..08，独立 key/
             独立 subject/独立 ownership；key 仅存 gitignored
             tmp/pilot-keys/，REGISTRY.md 记 issued_at/status，
             零 raw secret 打印/提交）
REAL_USER    0（截至报告——窗口开启中，待 Owner 分发 key）
SCRIPTED_PROBE 2（probe-alpha/beta；本轮全部验证流量；数据已清零）
SYSTEM_TEST  0（窗口内未跑测试电池）
```

## Traffic Classification

```text
ledger 规则（主体前缀路由，代码零改动）：
  consumer:pilot-user-*  = REAL_USER（唯一计入真实样本）
  consumer:probe-*       = SCRIPTED_PROBE（永不计入）
  电池/CI                = SYSTEM_TEST（本窗口未运行）
本轮全部观测流量=SCRIPTED_PROBE；REAL_USER 样本=0。
```

## Deployment Configuration

```text
INSURANCE_AGENT_MODE=controlled_pilot（strict：无 keys/无数据密钥/
  WeKnora 不可达均拒启动——启动即验证）
knowledge_provider=weknora · mock fallback=forbidden（strict 构造拒绝）
strict preflight=enabled 且通过（实例存活即证明；12:27Z 启动）
diagnostics 实证：runtime_mode=controlled_pilot · knowledge_provider=
  weknora · weknora_url/kb configured=true · state_backend=postgres ·
  registry=postgres · dependency_status=READY（PG/knowledge/mode 全 OK）
配置快照（非秘密）tmp/pilot.env.snapshot.txt；秘密注入仅经
  gitignored tmp/（hd2.key/pgpass/data-key；运行时零打印）
已知观测项：diagnostics llm_provider=null（读取时序 LOW 债——实际
  生成 glm attempts=2 实跑在案，见 Citation）
```

## Router Authority

```text
pilot_authority     = full（仅本实例 env；临时）
permanent_authority = deferred（D-07 不变；代码默认 slices 未动）
行为证据            Journey B intent=insurance_plan(conf1.0,rule,
                    route_decision=registry_lookup)→完整规划脊柱执行
                    （默认 slices 下 PLAN=OFF 不会执行规划脊柱）
回滚                unset env+重启（armed，见 Rollback）
```

## Authentication

```text
whoami 实证：consumer:pilot-user-01/CONSUMER · consumer:probe-alpha/
  CONSUMER · rbac:pilot-ops/OPERATOR（mode=authenticated）
匿名=401 · 篡改 token=401 · Bearer 仅认 token 段（role/user 不在
头部）；前端 IdentityGate+按主体分域存储（G 套件锁定，本实例同码）
```

## Consumer Ownership

服务端创建时绑定 owner（whoami 主体；客户端声明全忽略——G 套件
锁定）。chat→run→artifact 父链继承；重启后无主对象 fail-closed。

## Journey Results（SCRIPTED_PROBE 行为验证；真实用户旅程待样本）

| 旅程 | 结果 | 观察要点 |
|---|---|---|
| A 知识 QA「百万医疗险续保需要注意什么？」 | **QA_REFUSED（insufficient_evidence）** | intent=insurance_qa(rule conf1.0)→WeKnora 活链检索 allowed=0/denied=0→生成未尝试（attempts=0）→诚实拒答文案；**证据层拒答非引用门**；零幻觉 |
| A2 知识 QA「健康保险的等待期一般有多久？」 | **QA_REFUSED（citation_gate_rejected）** | 检索 allowed=1（WeKnora 真证据）→glm attempts=2（初生+再生成）→引用闭包门拒→安全拒答。**§15 允许状态标准样本：retrieval_success ∧ citation_failure ∧ safe_refusal**；不计 unsafe |
| B「健康满分主要保障什么？」 | **COMPLETED（诚实澄清）** | intent=insurance_plan(rule"保障")→完整脊柱→product-candidate 阶段：目录查无此产品+知识无可核实资料→不描述+请求准确名称/编号（P001 式）——零编造；产出真实 knowledge-evidence artifact（5.7KB lineage 全） |
| C 规划「给孩子重新规划保险」两轮 | **needs_review（诚实升级）** | turn-1 自然信息收集（5 问，零内部状态暴露）→turn-2 全脊柱 81 事件·6 VALID artifacts（client-profile→requirement→risk→coverage-gap→solution→knowledge-evidence）→product_candidate 质量门修复后仍未过→停止+人工复核标记；**无假报告** |
| D 澄清 | 机器验证 | C turn-1/B 均自然追问缺失信息；无 reason code/schema/router/agent id 泄漏（B/C turn-1 文案在案） |
| E 拒答 | 机器验证 | A/A2/B 三型拒答/澄清全部 fail-closed；零幻觉、零假产物 |
| F 产物交付 | 机器验证 | 真实 artifact→不透明 ref（ar_+hex24）→按 ref 下载 5709B→跨主体 ref=404→**父删时 ref 撤销=1 实证**（B chat 删除） |
| 真实用户 A–F | **待样本** | 窗口开启；0 会话（如实） |

## Knowledge / WeKnora

治理链活体：provider=weknora（diagnostics+A/A2/B/C 的 retrieval/
artifact 实证）；A2 allowed=1（真实证据可得）；B/C knowledge-evidence
artifact 为真实 WeKnora 产物。**新观测（如实）**：A 主流问法 allowed=0
（同 KB 在 28.H H-R1"续保"短句 allowed=2）——长具体问法下打分/覆盖
敏感（110/304 无嵌入+稀疏打分阈值属已知债范畴）；n=2 知识 QA 探针
拒答率 2/2（1 检索缺口+1 引用门）→ **P1 WATCH：若真实用户系统性
再现则逼近"核心流程不可用"阈值**（当前未触发——非系统性证据）。

## Grounding

全部窗口 **unsafe delivery=0**；三型拒答均为 fail-closed 诚实文案；
grounding_status=refused 正确传播；无绕过（闭包门 B5.1 套件+本轮
行为一致）。

## Citation

§15 规则执行：A2=retrieval_success AND citation_failure AND
safe_refusal（允许状态，如实分层记录）；A=证据层（生成未尝试，
citation N/A）；B/C=脊柱内证据锚定。citation_failure≠unsafe_delivery
全程遵守。

## Artifact Delivery

仅真实事件门控产物（本轮 7 个：B 1 + C 6，全 VALID+lineage）；
不透明 ref 发行/解析/所有权复检/下载/随父撤销全实证；无伪造卡片
（B-03/E-2 锁定同码）。

## Data Governance（§11 live 观察）

```text
Consumer  仅自己（越权五路全 404）
Operator  职责读留痕：consumer_data_read 审计实证（actor/purpose
          元数据；200 正常执行 O-7 不变）
Developer 同内部通道（rbac 值班键）；已删对象 fail-closed（operator
          resurrect=404 实证）
Delete    级联×3 实证（终态×2 + waiting 态×1 mid-lifecycle；目录
          rmtree+bus purge+refs 撤销+messages 全删）
审计      deletion_request/deletion_executed/consumer_data_read 全
          在案；内容泄漏检查=阴性（问题/答案文本零出现）
删后      chat/run/events/stream/artifacts/ref 全 404
```

## Security

跨用户 A→B（chat/run/events/stream/artifacts）=404 且与缺失基线
**同状态同 detail**（`{"detail":"not found"}` 逐字节一致——无存在性
oracle）· ref≠授权（跨主体 404）· 匿名/篡改=401 · 枚举限流 keys 模式
在位（240/60s）· secrets 零打印零提交（本轮全程）· P0 级 internal
leakage（run_id/case_id/agent_id/provider/model/raw event）=0。

## Reliability

uptime 711s+ 无崩溃；探针期 5xx=0（失败计数 27=预期 401/404 探针）；
WeKnora 全程可用（依赖检查 OK）；SSE stream 正常（waiting/completed/
needs_review 状态轮询+事件读取全通）；无 provider crash。

## Incidents

```text
P0  无
P1  无（WATCH：知识 QA 拒答率——见 Knowledge 节，n=2 未成系统性）
P2  ①needs_review 终态消息附带内部阶段名「product_candidate_provider
    did not pass evaluation after repair — needs human review」面向
    消费者（文案级内部术语透出；无 id/凭据/数据暴露；影响所有
    needs_review 结局；**建议 Owner 在真实用户进入前裁决**：一行
    模板级修复需改码授权，或接受为 R1 已知项）
    ②B 答案措辞「当前演示产品目录」（目录范围诚实但"演示"字样
    面向消费者——D-04 措辞轨道）
    ③diagnostics llm_provider=null 读取时序（已知 LOW 债，本轮
    再次实证）
    ④A 长问法检索 allowed=0（覆盖/打分敏感——已知嵌入/CJK 债范本）
```

## Stop Conditions

未触发（P0=0；P1=0；P2 仅登记）。

## Rollback

```text
状态    ARMED·未执行（窗口开启中——真实用户待进入）
程序    ①停 :8123/:5273 任务 ②unset ROUTER_AUTHORITY（代码默认
        slices 即恢复）③验证 :5173/:8000 未受影响、无残留 env
        （全部注入仅在进程内/tmp/）
触发    窗口结束 / Owner 指令 / P0-P1 STOP 条件
验证点  default state restored = git 代码默认 slices + 无 REAL_USER
        进程存活（重启后对象无主 fail-closed 亦为安全默认）
```

## User Feedback

无（REAL_USER=0——如实；反馈通道=对话内反馈面板+Owner 收集）。

## Metrics（基线；真实用户指标待窗口样本）

```text
Product   active=0 · conversations=0（真实）· refusal_rate：探针
          知识 QA 2/2（1 检索+1 引用）· artifact_rate：探针 3 run
          中 2 run 产真实 artifact · download：ref 下载实证 1
Quality   grounding 拒绝传播正确 · citation 合规（生成层）0/1 过门
          · unsafe=0 · wrong-agent=0（intent/route_decision 全对）
          · fake artifact/completion=0
Reliability requests 94/66 成功/27 预期失败（全探针）· WeKnora
          failure=0 · timeout=0 · 5xx=0 · stream failure=0 ·
          rollback events=0
Security  unauthorized=预期 401 · cross-user=0 · oracle=0 ·
          P0 级 leakage=0（P2 文案项另计）
```

## Technical Debt Observed（本轮新增/再现，未修）

P2①终态文案内部阶段名 · P2②"演示产品目录"措辞 · P2③diagnostics
读取时序 · P2④长问法检索敏感（110/304 嵌入+CJK+稀疏打分已知债的
行为表现）· MEMORY V0.1（已按 §12 作为试点披露项写入用户须知建议）。

## Permanent Full Authority Recommendation

```text
PERMANENT_FULL_AUTHORITY:
RECOMMEND: DEFER
EVIDENCE: 代码支持✓（非法值 fail-closed）· 灰度矩阵/等价门历史
  PASS（28.J 复证 B4 7/7+B6 10/10+M4 9/9）· 本轮 pilot full
  authority 行为正常（insurance_plan 正确路由+脊柱执行+澄清/升级
  语义正确）· **真实用户样本=0**（D-07 的关键缺失证据）· 试点期
  未出现路由类 P1/P0
```

## Pilot Conclusion

**DEPLOYED & VERIFIED — WINDOW OPEN, AWAITING INVITED USERS。**
技术就绪以行为级证据闭合（六旅程机器+安全+治理全 live 验证）；试点
本体（真实用户样本）尚未发生——窗口开启、凭据就绪、观察台账在位。
成功判据（安全零事件+至少一条真实用户完整业务链+无 P0/P1）当前
状态：安全零事件✓（探针域）；真实用户链路=待样本；P0/P1=0。试点
未结束，判定 DEFERRED 至窗口关闭复评。**给 Owner 的两项进入前
建议**：①裁决 P2①文案缺陷（修或接受）；②按 §12 向用户告知内存
试点限制。下一步：Owner 分发 8 把 key → 真实用户进入 → 观察窗口
（拒答率/泄漏/安全零事件）→ 窗口关闭执行 Rollback → 复评报告。

---

```text
Phase 28.K Status: PILOT DEPLOYED & VERIFIED · WINDOW OPEN
（REAL_USER=0 如实；探针验证全 PASS；P0/P1=0；P2×4 登记）
```
