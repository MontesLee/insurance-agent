# K.29-C FIX-3 Phase 3 · Controlled Gray + S1' Shadow — 终报

Date: 2026-10-02 · Status: **GRAY_SHADOW_PASS**
（授权:OD-FIX3 Phase3 决策书·端点切换 Owner 批准 2026-10-02）

---

## 1. Owner Authorization（执行核对）

执行:B/D 灰度(env ON·默认仍 OFF)·S1' 影子(SHADOW ONLY·六不改变)·
:8123 重启·影子指标采集。未执行:judge authority/改答案/Hybrid/S2/
Batch-2/任何 promotion(全零触碰)。

## 2. Actual Config / 3. Runtime Commit / 4. Endpoint

- **端点(Owner 批准切换)**:`.env LLM_BASE_URL → https://api.z.ai/
  api/coding/paas/v4`(+coding token 入 gitignored .env;回滚行保留
  于 .env 注释;按量端点 429/1113 余额 0 实证)。
- commit e1aba0e + FIX-3 未提交 span(claim_support/rules/loop 缝/
  shadow_judge);rules 默认 B/D=OFF(env 启动覆盖)。
- 模型:main glm-5.3/fast flashx/**qa flash**;`/api/agent/config`
  实测 base_url=api.z.ai ✓。

## 5. B/D Gray Status

**LIVE**(:8123 env EXEMPTION_V2_ENABLED=1·PREMISE_SCAN_ENABLED=1·
CLAIM_SUPPORT_ENABLED=1 沿生产 S1;HYBRID/judge authority 无路径)。
启动快照:tmp/obs/k29c_fix3_phase3_config_snapshot.json。

## 6. Smoke Results(14 类·live HTTP·异步轮询)

**14/14 PASS**(首轮两次空跑教训:①hd2 时代 API key 401→改 pilot key 集
②消息异步 queued→轮询修正;两次教训均已如实入档)。行为:知识题=引用门
诚实拒(20-94s 真生成);证据不足=3-4s 快拒;产品题=slice-OFF fail-closed;
R4=无金额结论。**零不安全交付**。

## 7. Shadow Invocation Count

观察窗=本会话受控流量(14 smoke+6 窗口+5 短窗=25 轮·其中 7 轮达终门)
→ 门事件 3+·**claim 记录 38·judge 调用 21**(预算内:qa 槽·≤20/轮·
τ=0.7·S0 同配)。影子为**异步旁路**(队列入队≈0 开销·独立线程判定)。

## 8. Safety Metrics(OD-FIX3-6 硬停监控)

| 指标 | 值 |
|---|---|
| HIGH_RISK_FALSE_UPGRADE | **0** |
| R3/R4 escape | 0(全部诚实拒) |
| numeric / contradiction / product / date-time / rec-number escape | **0** |
| FALSE_UPGRADE(非高危面) | 8(全部为真 paraphrase 的 would-flip:给付型/自由支配/报销型——判定=ENTAILED·高危扫描 0) |

**HARD STOP:未触发。** 影子含 2 例 evidence-meta prose 被判 ENTAILED
(「证据仅覆盖…」)——非高危·列入 watch(元叙述判定语义留 S1' 观察)。

## 9. Quality Metrics

- SAFE_RECOVERY(门拒+判 ALLOW+非高危):8 claim / 21 判定 ≈ 38%
  would-flip 率——与 S0 的 E 类恢复预期一致;
- UNSAFE_RECOVERY:0;
- 拒绝类(泛化/半真/否定/矛盾/建议数字):生产全拒(正确)·影子 0 ALLOW
  于高危面;
- 注意(如任务书):不把「更多 ALLOW」当质量——上表按 SAFE/UNSAFE 分列。

## 10-12. Ops / Window / Rollback

- 判定延迟 p50 **10.7s**/p95 35.8s(旁路·门路径零增:灰度与无影子两
  次同题运行答案逐字一致);malformed/timeout **0**;model error 0;
  稳定性窗内 0 漂移;**成本:COST_NOT_OBSERVABLE**(coding plan 无按
  调用计费遥测·调用数 21 实测·不估算)。
- 观察窗=Owner 已批配置内的本会话受控窗口;**未扩大**。
- 回滚验证(自动化+live):
  A/B 旗关=**C1 逐字一致**(live A/B 两题 PASS·tmp/obs/k29c_fix3_
  phase3_rb_*.json)·C 影子关=答案不变(live 前后栈对照)·D/E 判定
  超时/不可用=KEEP_BASELINE(单测)且生产无路径·F 影子日志失败=吞噬
  (单测+31 条前版错误记录实证生产答案未受影响)。

## 13. Failures(全记录)

①首启 hd2-key 401(改 pilot key 集)②消息异步未轮询(空答案)③影子
证据元组形状(31 条 KEEP_BASELINE 错误记录→修复后 0 error)。全部
运维层·零生产代码变更·零安全影响。

## 14. Hard-Stop Status / 15. Remaining Risks / 16. Next

- **HARD STOP:无**(七项全零)。
- 风险:shadow 样本量小(38 claim);evidence-meta ALLOW 语义待观察;
  灰度收益边际(交付仍全拒——B/D 定位=底座+纵深·E 类解锁待 S1' 后
  续裁决);coding plan 端点用于生产的配额/条款面=Owner 持续关注。
- **Next Owner Decision**:①S1' 真实窗口时长/流量来源(本窗=受控
  25 轮)与 batch-2 前是否扩大 ②E 类解锁(判定 authority)是否进入
  议程(需 S1' 更多数据+OD-12 式门槛)③FIX-3 span(Phase1+2+3 三
  文件+shadow_judge)D-08 续封 ④灰度保持/回退决策。

---

```
FINAL STATUS: GRAY_SHADOW_PASS
B/D gray = LIVE(默认 OFF·env 灰度)·Smoke 14/14·Shadow 38 records/
21 judgments·HARD STOP 全零·Rollback A/B PASS·Authority NOT GRANTED
·Hybrid OFF·S2 unchanged·Batch-2 not distributed
```
