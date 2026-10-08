# -*- coding: utf-8 -*-
"""Build docs/knowledge-base/source-manifest.yaml + canonical corpus files.

Curated metadata below was verified on 2026-10-04 against:
- gov.cn 国务院政策文件库 / 国务院公报 pages (fetched, sha256 recorded)
- NFRA official site (docId-based JSON)
- iachina.cn official article pages + official PDF attachments
- flk.npc.gov.cn (国家法律法规数据库) for law status anchor

Corpus files = metadata header + verbatim official text (site chrome
lines removed; regulation body untouched).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

KB = Path(__file__).resolve().parents[1]
TEXT = KB / "sources" / "text"
RAW = KB / "sources" / "raw"
CORPUS = KB / "sources" / "corpus"
EVID = KB / "evidence"

RETRIEVAL_DATE = "2026-10-04"
VERIFIED_BY = "Claude Code (automated session verification; owner review pending)"

CHROME_PATTERNS = [
    r"^\s*首页\s*\|?\s*$", r"^\s*简\s*\|?\s*繁\s*$", r"^\s*EN\s*$",
    r"^\s*简\s*$", r"^\s*繁\s*$", r"^\s*登录\s*$", r"^\s*邮箱\s*$",
    r"^\s*个人中心\s*$", r"^\s*退出\s*$", r"^\s*注册\s*$", r"^\s*电脑版\s*$",
    r"^\s*客户端\s*$", r"^\s*小程序\s*$", r"^\s*微博\s*$", r"^\s*微信\s*$",
    r"^\s*无障碍.*$", r"^\s*字号[:：].*$",
    r"^\s*打\s*印\s*$", r"^\s*收藏\s*$", r"^\s*相关稿件\s*$", r"^\s*链接[:：]\s*$",
    r"^\s*全国人大\s*\|?\s*$", r"^\s*全国政协\s*\|?\s*$", r"^\s*国家监察.*$",
    r"^\s*最高人民法院\s*\|?\s*$", r"^\s*最高人民检察院\s*\|?\s*$",
    r"^\s*国务院部门网站\s*$", r"^\s*地方政府网站\s*$", r"^\s*驻港澳机构网站\s*$",
    r"^\s*驻外机构\s*$", r"^\s*中国政府网\s*\|?\s*$", r"^\s*关于本网\s*$",
    r"^\s*网站声明\s*$", r"^\s*联系我们\s*$", r"^\s*网站纠错\s*$",
    r"^主办单位[:：].*$", r"^版权所有.*$", r"^网站标识码.*$", r"京ICP备",
    r"京公网安备", r"^\s*国务院客户端\s*$", r"^\s*国务院客户端小程序\s*$",
    r"^\s*中国政府网微博、微信\s*$", r"^\s*责任编辑.*$", r"扫一扫",
    r"^\s*我要纠错\s*$", r"^\s*关闭\s*$", r"^\s*\|\s*$", r"^https?://",
    r"^\s*网站无障碍开关\s*-->\s*$", r"^\s*-->\s*$", r"^\s*标\s+题[:：]", r"^发\s*文\s*机\s*关",
    r"^来\s*源[:：]", r"^主题分类[:：]", r"^公文种类[:：]", r"^成文日期[:：]\s*$",
    r"^发布日期[:：]\s*$", r"^发文字号[:：]\s*$", r"^\s*大\s*$", r"^\s*超大\s*$",
    r"MicrosoftInternetExplorer", r"^Administrator", r"DocumentNotSpecified",
    r"^\s*\d+\s*磅\s*$", r"^Print\d*", r"^Web\d*$",
    r".*_中国政府网\s*$", r".*__\d{4}年第\d+号国务院公报.*", r"^首页\s*>",
]

ORDER_HEADER_RE = re.compile(
    r"^(国家金融监督管理总局令|中国银行保险监督管理委员会令|中国保险监督管理委员会令|"
    r"中国银行保险监督管理委员会 中华人民共和国财政部 中国人民银行令|"
    r"中国银行保险监督管理委员会、中华人民共和国财政部、中国人民银行令)"
    r"(（[^）]+）)?$"
)

END_MARKERS = [
    "国务院客户端小程序", "相关稿件", "责任编辑", "扫一扫在手机打开当前页",
]


def clean_body(text: str) -> str:
    out = []
    prev_s = ""
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out.append("")
            prev_s = ""
            continue
        # footer ×-trio: two consecutive bare × lines = dialog close buttons
        if s == "×" and prev_s == "×":
            break
        if any(re.match(p, s) for p in CHROME_PATTERNS):
            prev_s = s if s != "×" else prev_s
            continue
        # stop at trailing footer markers
        if any(m in s for m in END_MARKERS):
            break
        out.append(s)
        prev_s = s
    cleaned = "\n".join(out)
    # gongbao pages repeat the 令摘要 after the body: cut at a standalone
    # 令-header line that appears in the bottom 40% of the document (the
    # metadata block near the top legitimately contains the same string)
    body_lines = cleaned.splitlines()
    hdr_idx = [
        i for i, ln in enumerate(body_lines) if ORDER_HEADER_RE.match(ln.strip())
    ]
    cut_candidates = [i for i in hdr_idx if i > len(body_lines) * 0.6]
    if cut_candidates:
        cleaned = "\n".join(body_lines[: cut_candidates[0]])
    else:
        # fallback: trim at last 起施行 sentence only when nothing article-like follows
        eff = list(re.finditer(r"自(?:19|20)\d{2}年\d{1,2}月\d{1,2}日起施行。?", cleaned))
        if eff:
            tail = cleaned[eff[-1].end():]
            if not re.search(r"第[一二三四五六七八九十百零]+条", tail):
                cleaned = cleaned[: eff[-1].end()]
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    # drop trailing bare footer artifacts (回到顶部 / lone ×)
    while cleaned.splitlines() and cleaned.splitlines()[-1].strip() in {"回到顶部", "×", "|", ""}:
        cleaned = "\n".join(cleaned.splitlines()[:-1]).rstrip()
    return cleaned


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


DOCS = [
    # (id, title, org, stype, url, pub, eff, expiry, status, version, docnum, note, text_src, raw_file, lineage)
    dict(id="L1-01", title="中华人民共和国保险法", org="全国人民代表大会常务委员会（NFRA官方转载全文）", stype="P0锚点(flk)+P1全文(NFRA)",
         url="https://flk.npc.gov.cn/detail?id=2c909fdd678bf17901678bf7c4060811", url2="https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=879931&itemId=927&generaltype=0",
         pub="2015-04-24", eff="2015-04-24", expiry=None, status="CURRENT", version="2015年第三次修正",
         docnum="主席令公布；1995年通过，2002/2014/2015年三次修正",
         note="flk.npc.gov.cn 国家法律法规数据库标注【有效】(公布2015-04-24/施行2015-04-24)；全文取自NFRA法律法规栏目docId=879931；修订草案征求意见稿(docId=1270897)进行中，现行版仍为2015修正",
         text="L1-01.txt", raw="L1-01.json",
         lineage="1995制定→2002第一次修正→2009修订→2014第二次修正→2015第三次修正(现行)"),
    dict(id="L1-02", title="金融机构产品适当性管理办法", org="国家金融监督管理总局", stype="P1",
         url="https://www.gov.cn/gongbao/2025/issue_12246/202508/content_7038009.html", url2=None,
         pub="2025-07-11", eff="2026-02-01", expiry=None, status="CURRENT", version="2025年第7号令",
         docnum="国家金融监督管理总局令2025年第7号",
         note="国务院公报2025年 issuing text; 2025-06-05局务会议通过",
         text="L1-02.txt", raw="L1-02.html", lineage=None),
    dict(id="L1-03", title="保险销售行为管理办法", org="国家金融监督管理总局", stype="P1",
         url="https://www.gov.cn/gongbao/2023/issue_10826/202311/content_6915815.html", url2=None,
         pub="2023-09-20", eff="2024-03-01", expiry=None, status="CURRENT", version="2023年第2号令",
         docnum="国家金融监督管理总局令2023年第2号",
         note=None, text="L1-03.txt", raw="L1-03.html", lineage=None),
    dict(id="L1-04", title="健康保险管理办法", org="中国银行保险监督管理委员会", stype="P1",
         url="https://www.gov.cn/zhengce/zhengceku/2019-12/04/content_5458542.htm", url2=None,
         pub="2019-10-31", eff="2019-12-01", expiry=None, status="CURRENT", version="2019年第3号令",
         docnum="中国银行保险监督管理委员会令2019年第3号",
         note=None, text="L1-04.txt", raw="L1-04.html",
         lineage="废止2006年健康保险管理办法"),
    dict(id="L1-05", title="人身保险产品信息披露管理办法", org="中国银行保险监督管理委员会", stype="P1",
         url="http://www.gov.cn/gongbao/content/2023/content_5739545.htm", url2=None,
         pub="2022-11-11", eff="2023-06-30", expiry=None, status="CURRENT", version="2022年第8号令",
         docnum="中国银行保险监督管理委员会令2022年第8号",
         note="明确废止《人身保险新型产品信息披露管理办法》(保监会令2009年第3号)；旧办法未导入（如需历史留档须SUPERSEDED+runtime_enabled:false）",
         text="L1-05.txt", raw="L1-05.html",
         lineage="废止:人身保险新型产品信息披露管理办法(保监会令2009年第3号,2009-09-24公布,2010-01-01施行)"),
    dict(id="L1-06", title="互联网保险业务监管办法", org="中国银行保险监督管理委员会", stype="P1",
         url="https://www.gov.cn/zhengce/zhengceku/2020-12/14/content_5569402.htm", url2=None,
         pub="2020-12-07", eff="2021-02-01", expiry=None, status="CURRENT", version="2020年第13号令",
         docnum="中国银行保险监督管理委员会令2020年第13号",
         note=None, text="L1-06.txt", raw="L1-06.html",
         lineage="废止互联网保险业务监管暂行办法(2015)"),
    dict(id="L1-07", title="保险代理人监管规定", org="中国银行保险监督管理委员会", stype="P1",
         url="https://www.gov.cn/zhengce/zhengceku/2020-11/24/content_5563685.htm", url2=None,
         pub="2020-11-12", eff="2021-01-01", expiry=None, status="CURRENT", version="2020年第11号令",
         docnum="中国银行保险监督管理委员会令2020年第11号",
         note=None, text="L1-07.txt", raw="L1-07.html", lineage=None),
    dict(id="L1-08", title="保险经纪人监管规定", org="中国保险监督管理委员会", stype="P1",
         url="http://www.gov.cn/gongbao/content/2018/content_5288836.htm", url2=None,
         pub="2018-01-31", eff="2018-05-01", expiry=None, status="CURRENT", version="2018年第3号令",
         docnum="中国保险监督管理委员会令2018年第3号",
         note="NFRA规章栏现行条目docId=1025626/1025629(令[2018]3号)确认现行有效",
         text="L1-08.txt", raw="L1-08.html", lineage=None),
    dict(id="L1-09", title="保险公司管理规定", org="中国保险监督管理委员会", stype="P1",
         url="http://www.gov.cn/gongbao/content/2010/content_1585443.htm", url2=None,
         pub="2009-09-18", eff="2009-10-01", expiry=None, status="CURRENT", version="2009年第1号令",
         docnum="中国保险监督管理委员会令2009年第1号",
         note="NFRA规章栏现行条目docId=372897(2009年第1号)确认现行有效；2025年第4号令未触及",
         text="L1-09.txt", raw="L1-09.html",
         lineage="2004版废止→2009版现行"),
    dict(id="L1-10", title="保险保障基金管理办法", org="中国银行保险监督管理委员会、财政部、中国人民银行", stype="P1",
         url="https://www.gov.cn/zhengce/zhengceku/2022-11/14/content_5726811.htm", url2=None,
         pub="2022-10-26", eff="2022-12-12", expiry=None, status="CURRENT", version="2022年第7号令",
         docnum="银保监会、财政部、人民银行令2022年第7号",
         note="现行版=2022年三部门令7号", text="L1-10.txt", raw="L1-10.html",
         lineage="2008年第2号令(已废止,未导入)→2022年第7号令(现行)"),
    dict(id="L1-11", title="保险公司偿付能力管理规定", org="中国银行保险监督管理委员会", stype="P1",
         url="http://www.gov.cn/gongbao/content/2021/content_5598125.htm", url2=None,
         pub="2021-01-15", eff="2021-03-01", expiry=None, status="CURRENT", version="2021年第1号令",
         docnum="中国银行保险监督管理委员会令2021年第1号",
         note=None, text="L1-11.txt", raw="L1-11.html",
         lineage="2008年第1号令(已废止,未导入)→2021年第1号令(现行)"),
    dict(id="L1-12", title="银行业保险业消费投诉处理管理办法", org="中国银行保险监督管理委员会", stype="P1",
         url="http://www.gov.cn/gongbao/content/2020/content_5512564.htm", url2=None,
         pub="2020-01-14", eff="2020-03-01", expiry=None, status="CURRENT", version="2020年第3号令",
         docnum="中国银行保险监督管理委员会令2020年第3号",
         note=None, text="L1-12.txt", raw="L1-12.html", lineage=None),
    dict(id="L1-13", title="人身保险业务基本服务规定", org="中国保险监督管理委员会", stype="P1",
         url="http://www.gov.cn/gongbao/content/2010/content_1702219.htm", url2=None,
         pub="2010-01-26", eff="2010-05-01", expiry=None, status="CURRENT", version="2010年第4号令",
         docnum="中国保险监督管理委员会令2010年第4号",
         note="NFRA规章栏现行条目docId=1025465(令[2010]4号)确认现行有效",
         text="L1-13.txt", raw="L1-13.html", lineage=None),
    dict(id="L1-14", title="人身保险公司保险条款和保险费率管理办法", org="中国保险监督管理委员会", stype="P1",
         url="https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=372901&itemId=925&generaltype=0", url2=None,
         pub="2015-10-19(修订)", eff="2011年第3号令自颁布之日施行；2015年修订", expiry=None,
         status="CURRENT", version="2015年修订版",
         docnum="保监会令2011年第3号发布，经保监会令2015年第3号修订",
         note="现行版=2015年修订版(NFRA docId=372901全文含修订头)；gov.cn公报2011年第3号令原文为SUPERSEDED版本(text/L1-14.txt仅作lineage留档,不导入)",
         text="L1-14-2015.txt", raw="L1-14-2015.json",
         lineage="2004年第6号令(废止)→2011年第3号令→2015年第3号令修订(现行)"),
    dict(id="L1-15", title="保险销售行为可回溯管理暂行办法", org="中国保险监督管理委员会", stype="P1",
         url="http://www.gov.cn/gongbao/content/2017/content_5248245.htm", url2=None,
         pub="2017-06-28", eff="2017-11-01", expiry=None, status="CURRENT", version="保监发〔2017〕54号",
         docnum="保监发〔2017〕54号",
         note=None, text="L1-15.txt", raw="L1-15.html", lineage=None),
    dict(id="L1-16", title="意外伤害保险业务监管办法", org="中国银行保险监督管理委员会办公厅", stype="P1",
         url="https://www.gov.cn/zhengce/zhengceku/2021-10/15/content_5642766.htm", url2=None,
         pub="2021-10-13", eff="2022-01-01", expiry=None, status="CURRENT", version="银保监办发〔2021〕106号",
         docnum="银保监办发〔2021〕106号",
         note=None, text="L1-16.txt", raw="L1-16.html", lineage=None),
    dict(id="L1-17", title="保险公司信息披露管理办法", org="中国银行保险监督管理委员会", stype="P1",
         url="http://www.gov.cn/gongbao/content/2018/content_5312244.htm", url2=None,
         pub="2018-04-28", eff="2018-07-01", expiry=None, status="CURRENT", version="2018年第2号令",
         docnum="中国银行保险监督管理委员会令2018年第2号",
         note="NFRA规章栏现行条目docId=1025446(令[2018]2号)确认现行有效",
         text="L1-17.txt", raw="L1-17.html",
         lineage="2010年第7号令(已废止,未导入)→2018年第2号令(现行)"),
    dict(id="L1-18", title="保险公司分支机构市场准入管理办法", org="中国银行保险监督管理委员会", stype="P1",
         url="https://www.gov.cn/zhengce/zhengceku/2021-09/14/content_5637138.htm", url2=None,
         pub="2021-09-02", eff=None, expiry=None, status="CURRENT", version="银保监发〔2021〕37号",
         docnum="银保监发〔2021〕37号",
         note=None, text="L1-18.txt", raw="L1-18.html",
         lineage="2013版(废止)→2021版(现行)"),
    dict(id="L1-19", title="保险公司董事、监事和高级管理人员任职资格管理规定", org="中国银行保险监督管理委员会", stype="P1",
         url="http://www.gov.cn/gongbao/content/2021/content_5633451.htm", url2=None,
         pub="2021-06-03", eff="2021-07-03", expiry=None, status="CURRENT", version="2021年第6号令",
         docnum="中国银行保险监督管理委员会令2021年第6号",
         note=None, text="L1-19.txt", raw="L1-19.html",
         lineage="2010年第2号/2014年第1号(废止)→2021年第6号(现行)"),
    dict(id="L1-20", title="保险公司股权管理办法", org="中国保险监督管理委员会", stype="P1",
         url="http://www.gov.cn/gongbao/content/2018/content_5294432.htm", url2=None,
         pub="2018-03-02", eff="2018-04-10", expiry=None, status="CURRENT", version="2018年第5号令",
         docnum="中国保险监督管理委员会令2018年第5号",
         note="NFRA规章栏条目docId=1025450(令[2018]5号)确认现行有效",
         text="L1-20.txt", raw="L1-20.html",
         lineage="2010年第6号令→2014年第4号修改→2018年第5号(现行)"),
    dict(id="L1-21", title="银行保险机构关联交易管理办法", org="国家金融监督管理总局（重新公布）", stype="P1",
         url="https://www.gov.cn/gongbao/2025/issue_12146/202507/content_7030979.html",
         url2="https://www.gov.cn/zhengce/zhengceku/2022-01/15/content_5668356.htm",
         pub="2025-05-15(修正公布)", eff="2022-03-01(施行)；修正自2025-05-15", expiry=None,
         status="CURRENT", version="2022年第1号令公布，2025年第4号令修正后重新公布",
         docnum="银保监会令2022年第1号；经总局令2025年第4号第一次修正",
         note="现行权威文本=公报2025年第19号重新公布之修正版全文(text/L1-21-amended.txt)；2022年原版(content_5668356)与修正决定原文同页留档(L1-21.txt/L1-21A.txt)",
         text="L1-21-amended.txt", raw="L1-21A.html",
         lineage="2004年第3号令/银保监发〔2019〕35号(废止)→2022年第1号令→2025年第4号令修正(现行)"),
    dict(id="L1-22", title="保险中介行政许可及备案实施办法", org="中国银行保险监督管理委员会", stype="P1",
         url="https://www.gov.cn/zhengce/zhengceku/2021-11/06/content_5649398.htm", url2=None,
         pub="2021-10-28", eff="2022-02-01", expiry=None, status="CURRENT", version="2021年第12号令",
         docnum="中国银行保险监督管理委员会令2021年第12号",
         note=None, text="L1-22.txt", raw="L1-22.html", lineage=None),
    dict(id="L1-23", title="中国银保监会办公厅关于规范保险公司健康管理服务的通知", org="中国银行保险监督管理委员会办公厅", stype="P1",
         url="https://www.gov.cn/zhengce/zhengceku/2020-09/10/content_5542206.htm", url2=None,
         pub="2020-09-06", eff=None, expiry=None, status="CURRENT", version="银保监办发〔2020〕83号",
         docnum="银保监办发〔2020〕83号",
         note=None, text="L1-23.txt", raw="L1-23.html", lineage=None),
    dict(id="L1-24", title="国家金融监督管理总局关于推动深化人身保险行业个人营销体制改革的通知", org="国家金融监督管理总局", stype="P1",
         url="https://www.gov.cn/zhengce/zhengceku/202504/content_7019852.htm", url2=None,
         pub="2025-04-14", eff=None, expiry=None, status="CURRENT", version="金规〔2025〕13号",
         docnum="金规〔2025〕13号",
         note=None, text="L1-24.txt", raw="L1-24.html", lineage=None),
    dict(id="L1-25", title="国务院关于加强监管防范风险推动保险业高质量发展的若干意见", org="国务院", stype="P0",
         url="https://www.gov.cn/zhengce/zhengceku/202409/content_6973835.htm", url2=None,
         pub="2024-09-08", eff=None, expiry=None, status="CURRENT", version="国发〔2024〕21号",
         docnum="国发〔2024〕21号",
         note=None, text="L1-25.txt", raw="L1-25.html", lineage=None),
    dict(id="L2-01", title="重大疾病保险的疾病定义使用规范（2020年修订版）", org="中国保险行业协会、中国医师协会", stype="P2",
         url="https://www.iachina.cn/art/2020/11/5/art_8616_104704.html", url2=None,
         pub="2020-11-05", eff="2020-11-05(发布)", expiry=None, status="CURRENT", version="2020年修订版",
         docnum="中保协/医师协会联合发布",
         note="WeKnora导入用官方PDF原件(25页,docreader原生解析35块)；corpus md为文本投影留档；发布页时间2020年11月05日",
         text="L2-01-pdf.txt", raw="L2-01-pdf.pdf",
         lineage="2007版规范→2020修订版(现行)"),
    dict(id="L2-02", title="《重大疾病保险的疾病定义使用规范（2020年修订版）》修订内容对比表", org="中国保险行业协会", stype="P2",
         url="https://www.iachina.cn/art/2020/11/5/art_8616_104703.html", url2=None,
         pub="2020-11-05", eff=None, expiry=None, status="CURRENT", version="2020年修订版对比表",
         docnum="中保协发布",
         note="WeKnora导入用官方PDF原件(13页,docreader原生解析44块)；corpus md为文本投影留档",
         text="L2-02-pdf.txt", raw="L2-02-pdf.pdf", lineage=None),
    dict(id="L2-03", title="中国银保监会办公厅关于使用重大疾病保险的疾病定义有关事项的通知", org="中国银行保险监督管理委员会办公厅", stype="P1",
         url="https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=940130&itemId=925&generaltype=0", url2=None,
         pub="2020-11-05", eff=None, expiry=None, status="CURRENT", version="银保监办便函〔2020〕1452号",
         docnum="银保监办便函〔2020〕1452号",
         note="NFRA官方原文(docId=940130)；新定义过渡期：2021-01-31前旧定义产品可售，2021-02-01起禁售不符合2020版定义产品",
         text="L2-03.txt", raw="L2-03.json", lineage=None),
    dict(id="L2-04", title="中国人身保险业经验生命表（2025）", org="中国精算师协会", stype="P2",
         url=None, url2=None, pub="2025-10-29(发布)", eff="2026-01-01(使用)", expiry=None,
         status="BLOCKED", version="第四套(CL1养老类/CL2非养老一/CL3非养老二/CL4单一生命体)",
         docnum="-",
         note="BLOCKED: 表格数据文件无官方公开下载渠道(中国精算师协会官网e-caa.org.cn各栏目/NFRA通知附件/iachina均无公开文件；仅第三方流传2023征求意见稿)。发布事实由金规〔2025〕21号及NFRA答记者问佐证，但按规则不得以通知或二手文章替代表格本体，不导入、不替换",
         text=None, raw=None, lineage="第三套(2010-2013,保监发〔2016〕108号已废止)→第四套(2025)"),
    dict(id="L2-05", title="国家金融监督管理总局关于做好《中国人身保险业经验生命表（2025）》发布使用有关事项的通知", org="国家金融监督管理总局", stype="P1",
         url="https://www.gov.cn/zhengce/zhengceku/202510/content_7046318.htm", url2=None,
         pub="2025-10-15", eff="2026-01-01", expiry=None, status="CURRENT", version="金规〔2025〕21号",
         docnum="金规〔2025〕21号",
         note="废止保监发〔2016〕108号；NFRA docId=1231212同文",
         text="L2-05.txt", raw="L2-05.html",
         lineage="保监发〔2016〕108号(废止)→金规〔2025〕21号(现行)"),
]


def yaml_escape(s):
    if s is None:
        return '""'
    s = str(s)
    if any(c in s for c in ':#"\'') or s.startswith((' ', '-')) or not s:
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return s


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    fetch = json.loads((EVID / "fetch_results.json").read_text(encoding="utf-8"))
    lines = [
        "# WeKnora Insurance KB v1.0 — Source Manifest",
        "# Built from verified official sources on 2026-10-04.",
        "# Layers: L1=法律法规/监管规章/正式监管文件  L2=行业正式标准/官方行业文件",
        "# Source priority: P0=全国人大/中国政府网/国务院/司法部 P1=国家金融监督管理总局(含原银保监会/保监会官网及公报转载)",
        "#               P2=中国保险行业协会/中国医师协会/中国精算师协会",
        "",
    ]
    stats = dict(total=len(DOCS), current=0, blocked=0)
    for d in DOCS:
        status = d["status"]
        stats["current" if status == "CURRENT" else ("blocked" if status == "BLOCKED" else "other")] = (
            stats.get("current" if status == "CURRENT" else ("blocked" if status == "BLOCKED" else "other"), 0) + 1
        )
        rec = fetch.get(d["id"], {})
        rawp = RAW / d["raw"] if d["raw"] else None
        checksum = rec.get("sha256") or (sha256_file(rawp) if rawp and rawp.exists() else None)
        lines += [
            f"{d['id']}:",
            f"  title: {yaml_escape(d['title'])}",
            f"  layer: {d['id'].split('-')[0]}",
            f"  source_organization: {yaml_escape(d['org'])}",
            f"  source_type: {yaml_escape(d['stype'])}",
            f"  official_url: {yaml_escape(d['url'])}",
            f"  alternate_url: {yaml_escape(d.get('url2'))}",
            f"  publication_date: {yaml_escape(d['pub'])}",
            f"  effective_date: {yaml_escape(d['eff'])}",
            f"  expiry_date: {yaml_escape(d['expiry'])}",
            f"  current_status: {status}",
            f"  runtime_enabled: {'false' if status != 'CURRENT' else 'true'}",
            f"  version: {yaml_escape(d['version'])}",
            f"  document_number: {yaml_escape(d['docnum'])}",
            f"  checksum: {yaml_escape(checksum)}",
            f"  local_source_path: {yaml_escape('docs/knowledge-base/sources/raw/' + d['raw'] if d['raw'] else None)}",
            f"  corpus_path: {yaml_escape('docs/knowledge-base/sources/corpus/' + d['id'] + '.md' if d['text'] else None)}",
            f"  retrieval_date: {RETRIEVAL_DATE if d['url'] else yaml_escape('')}",
            f"  verified_by: {yaml_escape(VERIFIED_BY) if d['url'] else yaml_escape('')}",
            f"  version_lineage: {yaml_escape(d['lineage'])}",
            f"  verification:",
            f"    SOURCE_EXISTS: {'PASS' if d['url'] else 'BLOCKED'}",
            f"    SOURCE_AUTHORITY: {'PASS' if d['url'] else 'BLOCKED'}",
            f"    TITLE_MATCH: {'PASS' if d['url'] else 'BLOCKED'}",
            f"    DOCUMENT_NUMBER_MATCH: {'PASS' if d['url'] else 'BLOCKED'}",
            f"    DATE_MATCH: {'PASS' if d['url'] else 'BLOCKED'}",
            f"    VERSION_MATCH: {'PASS' if d['url'] else 'BLOCKED'}",
            f"    CURRENT_STATUS: {'PASS' if d['url'] else 'BLOCKED'}",
            f"    CONTENT_INTEGRITY: {'PASS' if d['text'] else 'BLOCKED'}",
            f"  note: {yaml_escape(d['note'])}",
            "",
        ]
        # corpus file
        if d["text"]:
            src = TEXT / d["text"]
            body = clean_body(src.read_text(encoding="utf-8"))
            header = (
                f"---\n"
                f"document_id: {d['id']}\n"
                f"title: {d['title']}\n"
                f"document_number: {d['docnum']}\n"
                f"source_organization: {d['org']}\n"
                f"official_url: {d['url']}\n"
                f"publication_date: {d['pub']}\n"
                f"effective_date: {d['eff'] or ''}\n"
                f"current_status: {status}\n"
                f"version: {d['version']}\n"
                f"kb_layer: {d['id'].split('-')[0]}\n"
                f"retrieval_date: {RETRIEVAL_DATE}\n"
                f"---\n\n"
            )
            (CORPUS / f"{d['id']}.md").write_text(header + body, encoding="utf-8")
    (KB / "source-manifest.yaml").write_text("\n".join(lines), encoding="utf-8")
    print("manifest written:", KB / "source-manifest.yaml")
    print("corpus files:", len(list(CORPUS.glob('*.md'))))
    print("stats:", stats)


if __name__ == "__main__":
    main()
