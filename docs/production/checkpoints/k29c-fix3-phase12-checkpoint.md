# K.29-C FIX-3 Phase 12 — Controlled Authority Rollout · Checkpoint

## COMPLETE (2026-10-03 18:14-18:55Z·ROLLED_BACK_TO_BASELINE)
- Owner 本会话批准:SCRIPTED_PROBE cohort + Phase-11 提案值 + 进程内
  ops 接线(launch_8123_authority.py·零 git 生产变更·重启即移除)。
- 接线:AuthorityClaimSupportProxy 以包属性+sys.modules 双替换挂接
  (首验 gloop.csupp 无效——loop 局部 import 锚点·教训入档·修复后
  单探针实证拦截)。
- 运行:34 探针(E20/H10/B4)→113 claim ledger→**12 bounded 升级
  (全部真 factual-paraphrase·scope audit 逐条复验)**·硬类拦截 3·
  阻断探针 4/4 baseline·**九类逃逸+八类硬门全零**·post-gate 12/12·
  judge 12/8/0·配额 12/20 与 20/200 未触顶·版本钉扎零 mismatch。
- **18:55:45Z 自动 KILL:延迟 p95 40.98s>30s(Owner 阈值正确
  fail-closed·运营级非安全)**;回滚 live 演练:kill 后探针=baseline
  拒答·65s 零自动恢复·状态冻结零残留。
- 用户可见变化=0(交付路径缺口=发现:升级翻转门裁决但 regen 循环
  未交付——「升级→交付」路径需设计·OD-63 附加发现)。
- 伪警报澄清(留痕):内联分析正则过宽曾误标 12 升级为 HARD——
  runtime 门逐条复验全部 SOFT·为分析侧假阳性非运行时逃逸。
- 10 件证据+2 报告+OD v13(OD-FIX3-57..68)。
- **终态:ROLLED_BACK_TO_BASELINE(authority=KILLED 保持 OFF)。
  STOP——等 Owner(67:CONTINUE/ROLLBACK/TERMINATE)。**
