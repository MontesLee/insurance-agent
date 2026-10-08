# K.29-C FIX-3 Phase 3 — Controlled Gray + S1' Shadow · Checkpoint

## Phase 0 (2026-10-02) — 授权边界冻结

### AUTHORIZED
1. B/D controlled gray(env EXEMPTION_V2_ENABLED / PREMISE_SCAN_ENABLED·
   默认必须 OFF·沿 CLAIM_SUPPORT_ENABLED S1 惯例)
2. Semantic Judge S1' Shadow(SHADOW ONLY·六不改变·零 authority)
3. :8123 restart/runtime refresh(受 Phase 1A 端点门约束)
4. Shadow 观测指标采集(OD-FIX3-5 预算门内·超配置即 STOP)

### NOT_AUTHORIZED
Semantic Judge 生产 authority/改答案/改判定/改拒答/改 artifact/改路由/
改用户可见输出·Hybrid·OD-12 S2·Batch-2·任何 rollout promotion·任何
authority threshold 变更·为灰度放宽 deterministic gate·修改 Golden

### HARD_STOP(任一>0 → 停灰度扩展·留证·不 promote·不放宽·不改 Golden)
HIGH_RISK_FALSE_UPGRADE / R3 escape / R4 escape / numeric escape /
contradiction escape / product identity escape / date-time escape /
recommendation-number escape

### 关键执行序
P1 :8123 预检 → P1A 端点决策门 → P2 灰度启动(记录 commit/config/
pid/endpoint/flags) → P3 14 类 smoke → P4 S1' 影子(旁路离线重放式)
→ P5-9 安全契约/指标/监控/质量/运营 → P10 观察窗 → P11 回滚验证 →
P12 不升级 → P13 终报

- blockers: 端点裁决(Phase 1A)

## Phase 1-13 (2026-10-02) — GRAY_SHADOW_PASS
- 端点:Owner 批准切 .env→api.z.ai coding plan(回滚行留 .env 注释)。
- :8123 三次重启:①hd2-key 401(教训)→pilot key 集②无影子灰度栈
  (smoke 14/14·修异步轮询后真数据)③灰度+影子栈(终态·LIVE)。
- 影子:ops 启动器(launch_8123_gray_shadow.py)经生产缝挂载·异步
  旁路·证据元组 bug 一次(31 错误记录全 KEEP_BASELINE·修复后 0)。
- 观察窗(受控 25 轮·7 达终门):38 claim 记录·21 判定·ALLOW 8(全
  真 paraphrase)·**HARD STOP 七项全零**·p50 10.7s·malformed/timeout
  /error 0·成本 COST_NOT_OBSERVABLE。
- 回滚 A/B live PASS(旗关=逐字一致)·C/D/E/F 单测+实证。
- 终报 k29c-fix3-phase3-controlled-gray-shadow.md;证据
  tmp/obs/k29c_fix3_phase3_*.json(6 件)。
- **STOP——authority 未授予·promotion 未发生·等 Owner 四项决策
  (窗口扩大/E 类 authority 议程/span 续封/灰度保持)。**

## FIX-3 Phase 4 (2026-10-02 晚·IN PROGRESS·READ/OBSERVE ONLY)
- 授权:扩窗+evidence-meta 专项观察;未授权清单同决策书。
- Phase0 预检 PASS::8123 灰度+影子栈 LIVE(14:30Z)·authority 路径
  grep=空·loop 不 import judge·commit e1aba0e+span。
- Phase1 扩展窗口运行中:FIXTURE_TRAFFIC(~70 轮·分层 E1/E2/E3/E4×
  6-4 变体+REPEAT×3 稳定性+HIGH×16 高危+R3R4×6+META×4)·REAL=0 如实。
- 待做:Phase2-7 分析(ALLOW_CASE_REVIEW/E 类/时点专项/稳定性/假升
  二审/充分性[重点:高危 0-ALLOW=结构保证 vs 样本不足的区分])→
  Phase8-9 就绪判定→Phase10-11 回滚+零改动审计→Phase12-13 报告+
  OD v5(OD-FIX3-7..12)。

## Phase 4 完成 (2026-10-02 深夜·EXTENDED_SHADOW_PASS·零硬停)
- 扩窗:FIXTURE 54 轮分层(累计 79)→影子累计 337 记录/170 判定/
  9 硬类前置/0 错;ALLOW 74·KEEP 262·UNCERTAIN 1。
- 二审:SAFE 73/FALSE 0/REVIEW 1=ACR-023(否定方向与证据一致的真
  paraphrase·人工裁 SAFE·二层正则不能判方向=确定性层限制→OD-11 素材)。
- E 类稳定复现(E1 29%/E3 46%);meta 12/36 ALLOW 全 NON_BUSINESS_META
  →WATCH_ONLY;稳定性 95.3%(43 簇);p50 12.5s;高危管线零=结构
  (前置)非抽样·判定单独面 INSUFFICIENT(S0 仅)——区分如实。
- 判定:BATCH2_READY_FOR_OWNER_REVIEW·Authority=
  EVIDENCE_SUFFICIENT_FOR_OWNER_REVIEW(≠GRANTED)。
- 本阶段生产改动=0(mtime 证:三文件=Phase-2 窗口 20:52-21:05)。
- 报告 k29c-fix3-phase4-extended-shadow.md + OD v5
  (OD-FIX3-7..12)。
- **STOP——状态保持:gray LIVE·shadow LIVE·authority 未授予。**
