# K.29-C FIX-3 Phase 1.5 · Phase 0 Baseline Audit

Date: 2026-10-02 · READ-ONLY（零生产改动）· 详细 JSON: tmp/obs/k29c_fix3_phase1_5_baseline_audit.json

## 九问九答(摘要)

**Q1.** Claim Support authority = claim_support.py check() 聚合 + loop.py _full_gate 挂接(引用门+支持层合并·K.26 句段门共用);D-08 @24082d5+FIX2 层

**Q2.** 硬安全门 = _full_gate 复合;规则=C-FACT 全 SUPPORTED-only(PARTIAL/UNSUPPORTED/CONTRADICTED 皆拒→重生成→拒答)

**Q3.** 三态处理 = 全部 FAIL;CONTRADICTED 仅数字锚冲突检测(否定语义盲区=K.29-C F2 发现)

**Q4.** 建议句 = classify 类型序 REC 先于 FACT → 整句 NOT_APPLICABLE 豁免(含数字前提)= F-1(v2 实测 7/11 逃逸)

**Q5.** 数字前提 = numeric_anchors 仅对 C-FACT 运行;REC 句不达;_BARE_NUM_RE 无 倍/% → 区间逃逸(F4-08);D 插入位=类型豁免早退处

**Q6.** 产品身份 = _product_ok 双通道(P0xx 正则+catalog 名解析→evidence_refs);PARTIAL(catalog 覆盖缺口=F5-08/N4-3 同族)

**Q7.** 日期时窗 = _in_window(effective_from/to vs 冻结 as-of);缺口=时点限定 claim(F6-08)+锚元数据不入搜索域(F5-05)

**Q8.** 回滚开关 = 已有双旋钮(env CLAIM_SUPPORT_ENABLED>rules·生产 S1=env 1);B/D 沿同惯例

**Q9.** S1/S2/S3 = OD-12 框架(当前 CURRENT_GRAY S1·S2 staged 未启动·S3=连续窗口+零硬失败+Owner);OD12_BASELINE 冻结

## 核对结论
治理工件(ADR-019/022/024/025·OD-12·D-08·冻结金标×2)全在位;Phase 0/Phase 1 结论一致;基线自 Phase 1 后零变更(核 mtime)。
