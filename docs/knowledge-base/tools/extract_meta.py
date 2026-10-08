# -*- coding: utf-8 -*-
"""Extract metadata (发文字号/成文日期/发布日期/施行日期) from fetched texts."""
from __future__ import annotations

import json
import re
from pathlib import Path

KB = Path(__file__).resolve().parents[1]
TEXT = KB / "sources" / "text"

DATE_RE = r"(19|20)\d{2}年\d{1,2}月\d{1,2}日"


def main() -> None:
    out: dict[str, dict] = {}
    for p in sorted(TEXT.glob("*.txt")):
        doc_id = p.stem
        t = p.read_text(encoding="utf-8")
        rec: dict = {"chars": len(t)}

        # zhengceku metadata block
        for field, key in [
            (r"发文字号[：:]\s*(\S+)", "doc_number"),
            (r"成文日期[：:]\s*(" + DATE_RE + ")", "chengwen_date"),
            (r"发布日期[：:]\s*(" + DATE_RE + ")", "fabu_date"),
        ]:
            m = re.search(field, t)
            if m:
                rec[key] = m.group(1).strip()

        # 施行日期 (usually '自X年X月X日起施行')
        m = re.search(r"自((" + DATE_RE + r"))起施行", t)
        if m:
            rec["effective_date"] = m.group(1)

        # 公报/令公布日期: 'X年X月X日' near 令 header — take first date in body after 标题
        dates = re.findall(DATE_RE, t)
        # findall with group returns tuples; redo:
        dates = re.findall(r"(?:(19|20)\d{2})年\d{1,2}月\d{1,2}日", t)
        flat = re.findall(r"(?:19|20)\d{2}年\d{1,2}月\d{1,2}日", t)
        rec["dates_found"] = flat[:6]

        # 令号 patterns
        for pat, key in [
            (r"国家金融监督管理总局令[（(]?(\d{4})年第(\d+)号[）)]?", "nfra_order"),
            (r"中国银行保险监督管理委员会令[（(]?(\d{4})年第(\d+)号[）)]?", "cbirc_order"),
            (r"中国保险监督管理委员会令[（(]?(\d{4})年第(\d+)号[）)]?", "circ_order"),
            (r"[银保监发|保监发|银保监办发|金规|国发][〔\[](\d{4})(\d+)[〕\]]", "doc_num"),
        ]:
            m = re.search(pat, t)
            if m:
                rec[key] = m.group(0)
                break
        out[doc_id] = rec
    dest = KB / "evidence" / "extracted_meta.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for k in sorted(out):
        v = out[k]
        print(
            k,
            "| num:", v.get("doc_number") or v.get("nfra_order") or v.get("cbirc_order") or v.get("circ_order"),
            "| 成文:", v.get("chengwen_date"),
            "| 施行:", v.get("effective_date"),
            "| dates:", ",".join(v.get("dates_found", [])[:3]),
        )


if __name__ == "__main__":
    main()
