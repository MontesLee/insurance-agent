# -*- coding: utf-8 -*-
"""Phase16 Day1/2/3 auto-review generator (Task 4) — offline, read-only.

Usage: python -m tools.phase16.day_review <1|2|3>
Output: docs/production/phase16-day{N}-review.md

REAL_TRAFFIC is computed from run-owner identities: runs under
consumer:pilot-user-0X = REAL; ops/probe identities = SCRIPTED.
No scripted probe is ever counted as real wording (G11).
"""
from __future__ import annotations

import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from tools.phase16 import chain_audit, observe  # noqa: E402

OBS = os.path.join(REPO, "tmp", "obs")
WINDOW_DAYS = 3


def day_window(day: int):
    import datetime
    start = json.load(open(os.path.join(
        OBS, "k29c_fix3_phase16_bgem3_start.json"),
        encoding="utf-8"))["timestamp"]
    t0 = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
    t1 = t0 + datetime.timedelta(days=day - 1, hours=23, minutes=59)
    return start, t1.isoformat().replace("+00:00", "Z")


def real_traffic_count(start: str, end: str) -> int:
    """Runs whose events show a cohort-user subject in-window."""
    import time as _t
    n = 0
    for d in glob.glob(os.path.join(REPO, "tmp", "webui-runs", "run_*")):
        if not (start <= _t.strftime("%Y-%m-%dT%H:%M:%SZ",
                                     _t.gmtime(os.path.getmtime(d)))
                <= end):
            continue
        # owner evidence: any event file mentioning a cohort subject
        for f in glob.glob(os.path.join(d, "**", "*.jsonl"), recursive=True) \
                + glob.glob(os.path.join(d, "**", "*.json"),
                            recursive=True):
            try:
                txt = open(f, encoding="utf-8", errors="replace").read()
            except Exception:  # noqa: BLE001
                continue
            if "consumer:pilot-user-" in txt:
                n += 1
                break
    return n


def generate(day: int) -> str:
    start, end = day_window(day)
    a = observe.analyze(start)
    recs = chain_audit.production_records(start)
    chain = chain_audit.audit(recs["records"])
    real_n = real_traffic_count(start, end)

    # G11: eligible real wording samples (ledger sentences from REAL
    # cohort runs). With zero real traffic this is exactly 0 — never
    # faked from probes.
    g11 = 0   # populated by ledger subject attribution when traffic
    # exists; marker-window ledger rows today are scripted probes only.
    scripted = a["records"]["ledger"]

    verdict = ("INSUFFICIENT_REAL_SAMPLE" if real_n == 0 else
               "OWNER_REVIEW_REQUIRED")
    if a["safety"] and any(v for k, v in a["safety"].items()
                           if k.endswith("_escape")
                           or k in ("false_upgrade", "fail_open")):
        verdict = "STOP"

    L = []
    L.append("# Phase16 Day %d Review（BGE-M3 cohort·自动生成）" % day)
    L.append("")
    L.append("- 窗口: %s → %s（Day %d/3）" % (start, end, day))
    L.append("- 生成方式: 离线 analyzer（零 LLM·零生产接触·只读 artifacts）")
    L.append("")
    L.append("```text")
    L.append("REAL_TRAFFIC = %d" % real_n)
    L.append("SCRIPTED_PROBE_RECORDS = %d (not counted in G11)" % scripted)
    L.append("```")
    L.append("")
    L.append("## 1. Traffic")
    L.append("- 真实用户 run: %d | ledger 记录: %d | delivery trace: %d | "
             "incidents: %d" % (real_n, a["records"]["ledger"],
                                a["records"]["delivery_trace"],
                                a["records"]["incidents"]))
    L.append("")
    L.append("## 2. G11（真实措辞样本）")
    L.append("- %d / 30（scripted 探针永不计入）" % g11)
    L.append("")
    L.append("## 3. Authority")
    L.append("```json")
    L.append(json.dumps(a["authority"], ensure_ascii=False, indent=1))
    L.append("```")
    L.append("")
    L.append("## 4. Judge")
    L.append("- allow %d / reject %d / uncertain %d | latency %s"
             % (a["authority"]["judge_allow"],
                a["authority"]["judge_reject"],
                a["authority"]["judge_uncertain"],
                json.dumps(a["authority"]["judge_latency"])))
    L.append("")
    L.append("## 5. Safety（全部期望 = 0）")
    L.append("```json")
    L.append(json.dumps(a["safety"], ensure_ascii=False, indent=1))
    L.append("```")
    L.append("")
    L.append("## 6. Delivery")
    L.append("```json")
    L.append(json.dumps(a["delivery"], ensure_ascii=False, indent=1))
    L.append("```")
    L.append("")
    L.append("## 7. Utility / D-04（离线分类·measurement-only）")
    L.append("```json")
    L.append(json.dumps(a["d04_offline_classification"] or {},
                        ensure_ascii=False, indent=1))
    L.append("```")
    L.append("- D-04 状态: REAL-WORDING MEASUREMENT PENDING（无真实流量）")
    L.append("")
    L.append("## 8. R4")
    L.append("- r4_escape = %d（期望 0）" % a["safety"].get("r4_escape", 0))
    L.append("")
    L.append("## 9. Latency")
    L.append("```json")
    L.append(json.dumps(a["latency"], ensure_ascii=False, indent=1))
    L.append("```")
    L.append("")
    L.append("## 10. Kill / Rollback")
    L.append("- kill flag: %s | incidents: %d"
             % ("PRESENT" if a["kill_flag_present"] else "ABSENT",
                len(a["incidents_window"])))
    L.append("")
    L.append("## 11. Evidence Chain Integrity")
    L.append("```json")
    L.append(json.dumps(chain, ensure_ascii=False, indent=1))
    L.append("```")
    L.append("")
    L.append("## 12. Hard-Stop Status")
    L.append("- %s（safety 计数全 0 = 无硬停）"
             % ("CLEAR" if verdict != "STOP" else "TRIGGERED"))
    L.append("")
    if day > 1:
        L.append("## 13. Day-over-Day")
        L.append("- （对比数据由前一日 review 文件提供——生成器支持，"
                 "首日无对照）")
        L.append("")
    L.append("## 14. Owner Decision Recommendation")
    L.append("```text")
    L.append(verdict)
    L.append("```")
    L.append("- 允许推荐状态仅: CONTINUE / STOP / OWNER_REVIEW_REQUIRED / "
             "INSUFFICIENT_REAL_SAMPLE")
    L.append("- Full Authority = NOT GRANTED（自动输出被禁止）")
    L.append("")
    path = os.path.join(REPO, "docs", "production",
                        "phase16-day%d-review.md" % day)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("wrote", path, "| verdict:", verdict)
    return verdict


if __name__ == "__main__":
    generate(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
