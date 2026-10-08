# -*- coding: utf-8 -*-
"""Batch search gov.cn policy library for all 30 KB-V1 whitelist docs."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from search_gov import search_gov_cn  # noqa: E402

QUERIES: dict[str, str] = {
    "L1-01": "中华人民共和国保险法",
    "L1-02": "金融机构产品适当性管理办法",
    "L1-03": "保险销售行为管理办法",
    "L1-04": "健康保险管理办法",
    "L1-05": "人身保险产品信息披露管理办法",
    "L1-06": "互联网保险业务监管办法",
    "L1-07": "保险代理人监管规定",
    "L1-08": "保险经纪人监管规定",
    "L1-09": "保险公司管理规定",
    "L1-10": "保险保障基金管理办法",
    "L1-11": "保险公司偿付能力管理规定",
    "L1-12": "银行业保险业消费投诉处理管理办法",
    "L1-13": "人身保险业务基本服务规定",
    "L1-14": "人身保险公司保险条款和保险费率管理办法",
    "L1-15": "保险销售行为可回溯管理暂行办法",
    "L1-16": "意外伤害保险业务监管办法",
    "L1-17": "保险公司信息披露管理办法",
    "L1-18": "保险公司分支机构市场准入管理办法",
    "L1-19": "保险公司董事监事和高级管理人员任职资格管理规定",
    "L1-20": "保险公司股权管理办法",
    "L1-21": "银行保险机构关联交易管理办法",
    "L1-22": "保险中介行政许可及备案实施办法",
    "L1-23": "关于规范保险公司健康管理服务的通知",
    "L1-24": "关于推动深化人身保险行业个人营销体制改革的通知",
    "L1-25": "国务院关于加强监管防范风险推动保险业高质量发展的若干意见",
    "L2-01": "重大疾病保险的疾病定义使用规范",
    "L2-03": "关于使用重大疾病保险的疾病定义有关事项的通知",
    "L2-05": "中国人身保险业经验生命表",
}


def main() -> None:
    out_path = Path(__file__).resolve().parents[1] / "evidence" / "gov_cn_search_raw.json"
    out: dict[str, list] = {}
    if out_path.exists():
        out = json.loads(out_path.read_text(encoding="utf-8"))
    for doc_id, q in QUERIES.items():
        if doc_id in out:
            continue
        try:
            hits = search_gov_cn(q, "title", n=8)
        except Exception as exc:  # noqa: BLE001
            hits = [{"error": str(exc)}]
        out[doc_id] = hits
        print(f"{doc_id}: {len(hits)} hits")
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(2.0)
    print(f"saved -> {out_path}")


if __name__ == "__main__":
    main()
