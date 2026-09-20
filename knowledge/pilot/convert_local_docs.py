#!/usr/bin/env python3
"""One-time OFFLINE conversion of verified local-corpus candidates
into pilot fixtures (Phase 14.7 enrichment).

For each candidate: read the ORIGINAL file from the user's local
knowledge base (path from its documents.jsonl metadata), strip page
chrome mechanically, structure chapters/articles as headings, prepend
an honest provenance header (official URL / 文号 / dates / retrieval
date from the KB / copy status), and write the markdown fixture.

NO content is retyped, completed, or merged — only mechanically
filtered. The script verifies each output (article count, closing
施行动态, no residual tags) and refuses on anomaly.
"""
from __future__ import annotations

import json
import os
import re
import sys

KB = r"C:/Users/aubor/WorkBuddy/保险/insurance-knowledge-base"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "documents")

# candidate: KB doc-id → (fixture stem, license basis note)
CANDIDATES = {
    "DOC-000125": "pilot_law_tpll_2006",
    "DOC-000126": "pilot_law_agri_2012",
    "DOC-000303": "pilot_reg_health_ins_2019",
    "DOC-000302": "pilot_reg_internet_ins_2020",
    "DOC-000306": "pilot_reg_consumer_prot_2022",
    "DOC-000309": "pilot_reg_disclosure_2022",
    "DOC-000308": "pilot_reg_antifraud_2024",
}

# governance metadata for the registry table (REAL values from the KB
# documents.jsonl + the instrument numbers inside the documents)
META = {
    "DOC-000125": ("cn-state-council-order-462", "机动车交通事故责任强制保险条例",
                   "law", "S", "2006-07-01", "2006"),
    "DOC-000126": ("cn-state-council-order-629", "农业保险条例",
                   "law", "S", "2013-03-01", "2012"),
    "DOC-000303": ("cn-cbirc-order-2019-3", "健康保险管理办法",
                   "regulation", "A", "2019-12-01", "2019"),
    "DOC-000302": ("cn-cbirc-order-2020-13", "互联网保险业务监管办法",
                   "regulation", "A", "2021-02-01", "2020"),
    "DOC-000306": ("cn-cbirc-order-2022-9", "银行保险机构消费者权益保护管理办法",
                   "regulation", "A", "2023-03-01", "2022"),
    "DOC-000309": ("cn-cbirc-order-2022-8", "人身保险产品信息披露管理办法",
                   "regulation", "A", "2023-06-30", "2022"),
    "DOC-000308": ("cn-nfra-notice-2024-10", "反保险欺诈工作办法",
                   "regulation", "A", "2024-08-01", "2024"),
}

_CHAPTER = re.compile(r"^第[一二三四五六七八九十百]+章")
_ARTICLE = re.compile(r"^第[一二三四五六七八九十百零]+条")
_ARTICLE_ANY = re.compile(r"第[一二三四五六七八九十百零]+条")
# page chrome that never occurs inside a regulation's body
_JUNK_LINE = re.compile(
    r"^(首页|简|繁|EN|English|打印|关闭|分享到[:：]?.*|相关链接|相关文件|"
    r"[|\-—·•\s]+|.*ICP备.*|.*公网安备.*|.*中国政府网.*|.*国务院公报.*|"
    r"【.*】|◆|▪|●|□|×)$")


def html_text(path: str) -> str:
    raw = open(path, encoding="utf-8", errors="replace").read()
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw,
                 flags=re.S | re.I)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    txt = re.sub(r"<[^>]+>", "\n", raw)
    txt = (txt.replace("&nbsp;", " ").replace("&#160;", " ")
              .replace("&amp;", "&").replace("&lt;", "<")
              .replace("&gt;", ">").replace("&quot;", '"'))
    txt = re.sub(r"[ \t\u3000]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    return txt.strip()


def clean_noise(txt: str, title: str) -> str:
    """Mechanically drop page chrome: junk nav lines anywhere; body
    starts at the first ARTICLE line (backed up to include its
    preceding 公布令 block) and ends at the last 施行/公布 sentence."""
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    lines = [l for l in lines if not _JUNK_LINE.match(l)]
    first_art = next((i for i, l in enumerate(lines)
                      if _ARTICLE.match(l)), None)
    if first_art is None:
        # no line-start article; fall back to first line containing an
        # article number at all, else the title hit
        first_art = next((i for i, l in enumerate(lines)
                          if _ARTICLE_ANY.search(l)
                          and len(l) > 12), 0)
    start = first_art
    # back up over the 公布令/《title》/通过 preamble (≤8 short lines)
    j = first_art - 1
    while j >= 0 and first_art - j <= 8:
        l = lines[j]
        if (re.search(r"(令|第[一二三四五六七八九十百零]+号|《|公布|通过|"
                      r"^\s*$)", l) or l == title) and len(l) < 60:
            start = j
            j -= 1
        else:
            break
    end = len(lines)
    for i in range(len(lines) - 1, start, -1):
        if re.search(r"(施行|印发给|现予公布)", lines[i]):
            end = i + 1
            break
    return "\n".join(lines[start:end])


def to_markdown(txt: str, title: str) -> str:
    # government texts often pack several 条 on one physical line:
    # split BEFORE an article/chapter number that follows end-of-
    #sentence punctuation (a mid-sentence citation never follows 。；
    # so this cannot split a quotation inside an article).
    txt = re.sub(r"(?<=[。;；])\s*(第[一二三四五六七八九十百]+章)",
                 r"\n\1", txt)
    txt = re.sub(r"(?<=[。;；])\s*(第[一二三四五六七八九十百零]+条)",
                 r"\n\1", txt)
    out = []
    for line in txt.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _CHAPTER.match(line):
            out.append("\n## " + line)
        elif _ARTICLE.match(line):
            out.append("\n### " + line)
        else:
            out.append(line)
    return "\n".join(out)


def main() -> int:
    rows = {r["document_id"]: r for r in (
        json.loads(l) for l in open(
            os.path.join(KB, "10_METADATA", "documents.jsonl"),
            encoding="utf-8"))}
    report = []
    for cid, stem in CANDIDATES.items():
        r = rows[cid]
        sid, title, stype, auth, eff, ver = META[cid]
        src = os.path.join(KB, r["file_path"])
        txt = html_text(src)
        body = clean_noise(txt, title)
        arts = len(_ARTICLE_ANY.findall(body))
        ok_close = bool(re.search(r"(施行|现予公布|印发给)", body))
        ok_tags = "<" not in body.replace(" <", "").replace("< ", "")
        header = (
            "# %s(REAL PILOT SOURCE — FULL COPY)\n\n"
            "> REAL PILOT DOCUMENT, converted mechanically (HTML →\n"
            "> markdown; chapter/article headings added; wording\n"
            "> unmodified) from the local knowledge base copy of the\n"
            "> official page %s (retrieved %s by the KB pipeline).\n"
            "> 文号: %s · effective_from: %s · authority: %s ·\n"
            "> jurisdiction: CN · license: ALLOWED per《著作权法》第五条.\n"
            "> copy_status: FULL.\n"
            % (title, r.get("source_url"), r.get("retrieval_date"),
               r.get("doc_no") or "(见正文公布令)", eff, auth))
        with open(os.path.join(OUT, stem + ".md"), "w",
                  encoding="utf-8") as f:
            f.write(header + "\n" + to_markdown(body, title) + "\n")
        report.append({"kb_id": cid, "stem": stem, "title": title,
                       "cn_chars": len(re.findall(r"[\u4e00-\u9fff]",
                                                  body)),
                       "articles": arts, "closes": ok_close,
                       "residual_tags": not ok_tags})
    for x in report:
        print("%(kb_id)s -> %(stem)s | %(cn_chars)6d chars | "
              "%(articles)3d articles | closes=%(closes)s "
              "tags_residual=%(residual_tags)s" % x)
    bad = [x for x in report if not x["closes"] or x["residual_tags"]
           or x["articles"] < 20]
    if bad:
        print("ANOMALY:", bad)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
