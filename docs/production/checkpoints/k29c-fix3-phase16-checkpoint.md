# K.29-C FIX-3 Phase 16 — Real-User Controlled Cohort · Checkpoint

## ACTIVE (2026-10-03 14:46Z armed·REAL_USER_CONTROLLED_COHORT_ACTIVE)
- Owner 本会话批准 OD-FIX3-85..95(cohort/20/200/调用数代理 G9/
  30 条 G11/3 天/p95≤30/硬停 kill/单逃逸 rollback)。
- Preflight PASS(九项+已知限制:日配额进程内存计数·真实流量依赖
  key 物理分发);靶向回归 44/44。
- Cohort 启动:kill 移除→:8123 重启(v2+子集钩子+kill-watcher)
  →AUTHORITY ARMED→武装探针(SCRIPTED_PROBE·1/20):60.6s 交付
  首条真实 authority 答案(12 eligible/12 升级/6 judge/0 硬拦/
  0 错误)。
- 窗口 OPEN(3 天·G11 0/30);REAL_USER=0 如实;四维指标+硬停+
  kill/rollback 程序装载;NO AUTO-RECOVERY/EXPANSION。
- 9 件工件+2 报告+OD v17(OD-FIX3-98..100=key 分发/窗口节奏/
  G11 处置)。**STOP——等 Owner(key 分发/窗口复核)。**
