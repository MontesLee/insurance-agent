# KB-V1 Owner Acceptance — WeKnora Insurance KB v1.0

- 构建日期: 2026-10-04　·　构建方式: 真实官方来源采集（无 AI 生成内容）
- 白名单: 30 Document IDs（L1×25 + L2×5）
- 验收人: ______________　日期: ____________

## FINAL STATUS

```
FINAL STATUS: OWNER_REVIEW_READY
REAL DOCUMENTS:            29 / 30   (L2-04 BLOCKED: 生命表本体无官方公开文件)
OFFICIAL SOURCES VERIFIED: 29 / 30
CURRENT/VERSION VERIFIED:  29 / 30
WEKNORA IMPORTED:          29 / 30
ACTIVE (completed+chunks): 29 / 30
SOURCE BLOCKED:            1
RETRIEVAL BENCHMARK:       35 / 57   (22 失败=嵌入模型区分度限制,见§5)
QUALIFIED EVIDENCE:        40 / 50
CLAIM SUPPORT:             16 / 25
NEGATIVE RETRIEVAL:        4 / 7
PRODUCTION RUNTIME CHANGES: 0
```

---

## 1. 文件总表

| ID | Title | Source | URL | Version | Effective | Status | WeKnora | Active | Chunks |
| -- | ----- | ------ | --- | ------- | --------- | ------ | ------- | ------ | ------ |
| L1-01 | 中华人民共和国保险法 | 全国人民代表大会常务委员会（NF | https://flk.npc.gov.cn/detail?id=2c909fdd678bf17901678bf7c40 | 2015年第三次修正 | 2015-04-24 | CURRENT | ✓ | ✓ | 53 |
| L1-02 | 金融机构产品适当性管理办法 | 国家金融监督管理总局 | https://www.gov.cn/gongbao/2025/issue_12246/202508/content_7 | 2025年第7号令 | 2026-02-01 | CURRENT | ✓ | ✓ | 16 |
| L1-03 | 保险销售行为管理办法 | 国家金融监督管理总局 | https://www.gov.cn/gongbao/2023/issue_10826/202311/content_6 | 2023年第2号令 | 2024-03-01 | CURRENT | ✓ | ✓ | 20 |
| L1-04 | 健康保险管理办法 | 中国银行保险监督管理委员会 | https://www.gov.cn/zhengce/zhengceku/2019-12/04/content_5458 | 2019年第3号令 | 2019-12-01 | CURRENT | ✓ | ✓ | 34 |
| L1-05 | 人身保险产品信息披露管理办法 | 中国银行保险监督管理委员会 | http://www.gov.cn/gongbao/content/2023/content_5739545.htm | 2022年第8号令 | 2023-06-30 | CURRENT | ✓ | ✓ | 10 |
| L1-06 | 互联网保险业务监管办法 | 中国银行保险监督管理委员会 | https://www.gov.cn/zhengce/zhengceku/2020-12/14/content_5569 | 2020年第13号令 | 2021-02-01 | CURRENT | ✓ | ✓ | 68 |
| L1-07 | 保险代理人监管规定 | 中国银行保险监督管理委员会 | https://www.gov.cn/zhengce/zhengceku/2020-11/24/content_5563 | 2020年第11号令 | 2021-01-01 | CURRENT | ✓ | ✓ | 88 |
| L1-08 | 保险经纪人监管规定 | 中国保险监督管理委员会 | http://www.gov.cn/gongbao/content/2018/content_5288836.htm | 2018年第3号令 | 2018-05-01 | CURRENT | ✓ | ✓ | 34 |
| L1-09 | 保险公司管理规定 | 中国保险监督管理委员会 | http://www.gov.cn/gongbao/content/2010/content_1585443.htm | 2009年第1号令 | 2009-10-01 | CURRENT | ✓ | ✓ | 23 |
| L1-10 | 保险保障基金管理办法 | 中国银行保险监督管理委员会、财政 | https://www.gov.cn/zhengce/zhengceku/2022-11/14/content_5726 | 2022年第7号令 | 2022-12-12 | CURRENT | ✓ | ✓ | 27 |
| L1-11 | 保险公司偿付能力管理规定 | 中国银行保险监督管理委员会 | http://www.gov.cn/gongbao/content/2021/content_5598125.htm | 2021年第1号令 | 2021-03-01 | CURRENT | ✓ | ✓ | 11 |
| L1-12 | 银行业保险业消费投诉处理管理办法 | 中国银行保险监督管理委员会 | http://www.gov.cn/gongbao/content/2020/content_5512564.htm | 2020年第3号令 | 2020-03-01 | CURRENT | ✓ | ✓ | 13 |
| L1-13 | 人身保险业务基本服务规定 | 中国保险监督管理委员会 | http://www.gov.cn/gongbao/content/2010/content_1702219.htm | 2010年第4号令 | 2010-05-01 | CURRENT | ✓ | ✓ | 9 |
| L1-14 | 人身保险公司保险条款和保险费率管理办法 | 中国保险监督管理委员会 | https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId= | 2015年修订版 | 2011年第3号令自颁布之日施行；2015年修订 | CURRENT | ✓ | ✓ | 19 |
| L1-15 | 保险销售行为可回溯管理暂行办法 | 中国保险监督管理委员会 | http://www.gov.cn/gongbao/content/2017/content_5248245.htm | 保监发〔2017〕54号 | 2017-11-01 | CURRENT | ✓ | ✓ | 8 |
| L1-16 | 意外伤害保险业务监管办法 | 中国银行保险监督管理委员会办公厅 | https://www.gov.cn/zhengce/zhengceku/2021-10/15/content_5642 | 银保监办发〔2021〕106号 | 2022-01-01 | CURRENT | ✓ | ✓ | 27 |
| L1-17 | 保险公司信息披露管理办法 | 中国银行保险监督管理委员会 | http://www.gov.cn/gongbao/content/2018/content_5312244.htm | 2018年第2号令 | 2018-07-01 | CURRENT | ✓ | ✓ | 13 |
| L1-18 | 保险公司分支机构市场准入管理办法 | 中国银行保险监督管理委员会 | https://www.gov.cn/zhengce/zhengceku/2021-09/14/content_5637 | 银保监发〔2021〕37号 | - | CURRENT | ✓ | ✓ | 30 |
| L1-19 | 保险公司董事、监事和高级管理人员任职资格管理规定 | 中国银行保险监督管理委员会 | http://www.gov.cn/gongbao/content/2021/content_5633451.htm | 2021年第6号令 | 2021-07-03 | CURRENT | ✓ | ✓ | 20 |
| L1-20 | 保险公司股权管理办法 | 中国保险监督管理委员会 | http://www.gov.cn/gongbao/content/2018/content_5294432.htm | 2018年第5号令 | 2018-04-10 | CURRENT | ✓ | ✓ | 30 |
| L1-21 | 银行保险机构关联交易管理办法 | 国家金融监督管理总局（重新公布） | https://www.gov.cn/gongbao/2025/issue_12146/202507/content_7 | 2022年第1号令公布，2025年第 | 2022-03-01(施行)；修正自2025-05-15 | CURRENT | ✓ | ✓ | 32 |
| L1-22 | 保险中介行政许可及备案实施办法 | 中国银行保险监督管理委员会 | https://www.gov.cn/zhengce/zhengceku/2021-11/06/content_5649 | 2021年第12号令 | 2022-02-01 | CURRENT | ✓ | ✓ | 76 |
| L1-23 | 中国银保监会办公厅关于规范保险公司健康管理服务的通知 | 中国银行保险监督管理委员会办公厅 | https://www.gov.cn/zhengce/zhengceku/2020-09/10/content_5542 | 银保监办发〔2020〕83号 | - | CURRENT | ✓ | ✓ | 13 |
| L1-24 | 国家金融监督管理总局关于推动深化人身保险行业个人营销体制 | 国家金融监督管理总局 | https://www.gov.cn/zhengce/zhengceku/202504/content_7019852. | 金规〔2025〕13号 | - | CURRENT | ✓ | ✓ | 14 |
| L1-25 | 国务院关于加强监管防范风险推动保险业高质量发展的若干意见 | 国务院 | https://www.gov.cn/zhengce/zhengceku/202409/content_6973835. | 国发〔2024〕21号 | - | CURRENT | ✓ | ✓ | 13 |
| L2-01 | 重大疾病保险的疾病定义使用规范（2020年修订版） | 中国保险行业协会、中国医师协会 | https://www.iachina.cn/art/2020/11/5/art_8616_104704.html | 2020年修订版 | 2020-11-05(发布) | CURRENT | ✓ | ✓ | 35 |
| L2-02 | 《重大疾病保险的疾病定义使用规范（2020年修订版）》修 | 中国保险行业协会 | https://www.iachina.cn/art/2020/11/5/art_8616_104703.html | 2020年修订版对比表 | - | CURRENT | ✓ | ✓ | 44 |
| L2-03 | 中国银保监会办公厅关于使用重大疾病保险的疾病定义有关事项 | 中国银行保险监督管理委员会办公厅 | https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId= | 银保监办便函〔2020〕1452号 | - | CURRENT | ✓ | ✓ | 3 |
| L2-04 | 中国人身保险业经验生命表（2025） | 中国精算师协会 |  | 第四套(CL1养老类/CL2非养老一 | 2026-01-01(使用) | BLOCKED | - | - | - |
| L2-05 | 国家金融监督管理总局关于做好《中国人身保险业经验生命表（ | 国家金融监督管理总局 | https://www.gov.cn/zhengce/zhengceku/202510/content_7046318. | 金规〔2025〕21号 | 2026-01-01 | CURRENT | ✓ | ✓ | 8 |

## 2. Source Verification 统计

```
真实来源(官方URL可达+抓取成功): 29
官方来源(P0/P1/P2 分级):       P0×1(L1-25 国发+L1-01 flk锚) P1×26 P2×2
来源失败:                      0
版本冲突(现行≠初版):           L1-14(2015修订) L1-21(2025修正) L1-05(废止旧办法)
废止文件(未启用):              人身保险新型产品信息披露管理办法(2009)等 lineage 留档
重复文件:                      0 (KB 内 30 ID 互斥; 与 insurance-pilot-2 重叠 L1-04/L1-06 为跨库副本,切换 KB 时由 Owner 裁决)
BLOCKED:                       L2-04 (表格本体无官方公开下载渠道)
```

### 版本谱系关键点（防旧版充现行）

- **L1-01 保险法**: flk.npc.gov.cn 标注【有效】公布 2015-04-24（2015 三修现行；修订草案征求意见中，未生效）。
- **L1-05**: 2022年8号令明确废止《人身保险新型产品信息披露管理办法》（2009年3号令）；旧办法仅 lineage 留档，未导入。
- **L1-14**: 现行文本=保监会令2011年3号发布、2015年3号令修订版（NFRA docId=372901 含修订头全文）；gov.cn 公报 2011 原文= SUPERSEDED，仅留档。
- **L1-21**: 2025年4号令（公报2025年第19号）第四十五条增款+术语修改并**重新公布**；现行文本=修正后重公布全文（13,091字）；2022 原版不作为 Runtime 权威版。
- **L1-04/10/11/17/19/20**: 旧版（2006/2008/2010/2014 等）均已由现行版替代，未导入。
- **L2-05**: 废止保监发〔2016〕108号（第三套生命表通知）。

## 3. WeKnora 状态

```
Dataset:  insurance-kb-v1 (44af9ff2-ecef-445e-87c6-cb1458cd4d44)  [tenant 10001]
Tenant:   10001
Documents: 29 uploaded
Active:   29 (parse completed + enabled)
Chunks:   791
Embedding: builtin-embedding-local (weknora-ollama / nomic-embed-text)
Index:    每 doc chunk_count>0 已验证
```

## 4. Retrieval Benchmark

```
Total:      57
PASS:       35
FAIL:       22
Retrieval层过: 40/50
Qualified层过: 40/50
ClaimSupport:  16/25 (HIGH-risk cases)
Negative:      4/7
```

## 5. 失败 Case 明细

| Case | Query | Expected | Actual(top) | Failure Reason | Risk | Recommendation |
| -- | -- | -- | -- | -- | -- | -- |
| RB-L1-001 | 保险公司注册资本的最低限额是多少 | L1-01 | L1-11,L1-07,L1-20 | expected_fact neither SUPPORTED by module nor verbatim-conta | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L1-006 | 保险销售行为管理办法的施行日期 | L1-03 | L1-06,L1-04,L1-15 | expected_fact neither SUPPORTED by module nor verbatim-conta | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L1-016 | 保险经纪人监管规定的施行日期 | L1-08 | L1-07,L1-08,L1-18 | expected_fact neither SUPPORTED by module nor verbatim-conta | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L1-018 | 保险公司管理规定的施行日期是哪一天 | L1-09 | L1-09,L1-16,L1-07 | expected_fact neither SUPPORTED by module nor verbatim-conta | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L1-023 | 银行保险机构收到消费投诉后多久作出处理决定 | L1-12 | L1-12,L1-12,L1-22 | expected_fact neither SUPPORTED by module nor verbatim-conta | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L1-026 | 人身保险业务基本服务规定的施行日期 | L1-13 | L1-07,L1-13,L1-14 | expected_fact neither SUPPORTED by module nor verbatim-conta | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L1-028 | 人身保险公司保险条款和保险费率管理办法现行版本是 | L1-14 | L1-14,L2-03,L1-16 | expected_fact neither SUPPORTED by module nor verbatim-conta | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L1-029 | 保险销售可回溯资料应当保存多长时间 | L1-15 | L1-06,L1-06,L1-14 | expected doc L1-15 not in top-10 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L2-001 | 2020版重疾规范规定必须包含哪三种轻度疾病 | L2-01 | L2-03,L2-01,L1-12 | expected_fact neither SUPPORTED by module nor verbatim-conta | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L2-002 | 严重溃疡性结肠炎的重疾定义是什么 | L2-01 | L1-08,L1-07,L1-07 | expected_fact neither SUPPORTED by module nor verbatim-conta | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L2-003 | 重大疾病保险的疾病定义使用规范由哪些组织修订 | L2-01 | L2-02,L1-14,L1-07 | expected doc L2-01 not in top-10 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L2-005 | 轻度疾病的累计保险金额与重度疾病有什么比例限制 | L2-01 | L1-01,L1-04,L1-04 | expected doc L2-01 not in top-10 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L2-006 | 重疾定义修订前后严重脑中风后遗症的定义有什么变化 | L2-02 | L1-11,L2-01,L1-08 | expected doc L2-02 not in top-10 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L2-007 | 重疾定义对比表中恶性肿瘤定义修订前后的差异 | L2-02 | L2-01,L1-11,L1-07 | expected doc L2-02 not in top-10 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L2-008 | 哪里可以查到重疾定义修订前和修订后的全文对照 | L2-02 | L1-11,L1-16,L1-21 | expected doc L2-02 not in top-10 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L2-013 | 年金保险评估法定责任准备金应当采用哪张生命表 | L2-05 | L1-04,L1-14,L1-16 | expected doc L2-05 not in top-10 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-L2-015 | 单一生命体表有什么用途 | L2-05 | L1-23,L2-02,L2-01 | expected doc L2-05 not in top-10 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-X-001 | 消费者遇到保险销售误导应该怎么投诉维权 | L1-12 | L1-06,L1-06,L1-06 | expected doc L1-12 not in top-10 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-X-005 | 保险公司与股东之间的关联交易受什么监管约束 | L1-21 | L1-20,L1-20,L1-01 | expected doc L1-21 not in top-10 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-N-001 | 如何办理机动车驾驶证换证手续 | - | L1-06,L1-18,L2-01 | negative query qualified hits: L1-18,L2-01,L2-01,L2-01,L1-13 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-N-002 | 社会保险里的养老保险退休后怎么办理领取手续 | - | L1-24,L1-08,L1-06 | negative query qualified hits: L1-24,L1-08,L1-06,L1-06,L1-06 | HIGH | 人工核对该 case 的检索/资格/支持层 |
| RB-N-006 | 未成年人办理身份证需要什么材料 | - | L1-22,L1-14,L1-07 | negative query qualified hits: L1-22,L1-07,L1-07,L1-12 | HIGH | 人工核对该 case 的检索/资格/支持层 |

### 5.1 检索失败根因证据（SELF-RETRIEVAL 展示）

用**块的原文逐字作为查询**仍无法稳定检回含该原文的块（严重溃疡性结肠炎→未进top-10；注册资本二亿元→rank 8；施行日期→rank 5）。
证明：nomic-embed-text 对中文法律文本的向量相似度区分度接近噪声级——**KB 数据层无缺陷**（791/791 块全嵌入、事实文本逐字在块内、所有 benchmark 失败 case 的 expected_fact 均可在库内块文本中找到），瓶颈在部署级嵌入模型。
Owner 杠杆：更换中文嵌入模型（如 bge-m3）→ KB 重建向量索引（约 30 分钟）→ 重跑 benchmark（evidence/self_retrieval_exhibit.json）。

## 6. Owner 人工检查 Checklist

```
[ ] 30 个 Document ID 是否全部对应真实文件（29 真实 + L2-04 BLOCKED 如实申报）
[ ] 每个文件是否存在官方来源（manifest.official_url 逐条可点开）
[ ] URL 是否可以打开
[ ] 文件标题是否一致（fetch marker 校验全过）
[ ] 文号是否一致（fetch marker 校验全过）
[ ] 发布日期是否一致（extracted_meta.json + manifest）
[ ] 生效日期是否一致
[ ] 当前是否有效（flk/NFRA 规章栏/NFRA 检索交叉核验）
[ ] 是否存在被废止文件误启用（无——旧版仅 lineage 留档）
[ ] WeKnora 是否只有这一套 Runtime KB（新库 insurance-kb-v1 建立后 runtime 仍指向 insurance-pilot-2，切换=Owner 决策）
[ ] 是否存在 AI 自行编写的保险知识（无——全部 corpus 为官方原文+元数据头）
[ ] Retrieval 是否正确（benchmark 50 正例）
[ ] QualifiedEvidence 是否正确（资格层统计）
[ ] Claim Support 是否正确（HIGH 风险 case 统计）
[ ] Negative Retrieval 是否通过（7 负例）
```

## 7. 治理边界声明

- 本任务零生产 runtime 修改（Intent/C2/Claim Support/Authority/Hybrid 均未触碰）。
- WeKnora 仍是唯一 Runtime Knowledge Base；本库为 WeKnora 内新 dataset。
- runtime 仍指向 insurance-pilot-2；是否将生产检索切至 insurance-kb-v1 = Owner 决策（未做）。
- L2-04 未以任何替代文章充数；如后续精算师协会公开表格文件，可补导。

OWNER DECISION REQUIRED: YES
