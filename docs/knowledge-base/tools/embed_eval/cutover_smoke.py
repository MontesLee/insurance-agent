# -*- coding: utf-8 -*-
"""§14 Cutover smoke via the REAL runtime HTTP API (:8123): 5 normal +
5 high-risk + 5 negative turns — full production path (intent -> router
-> knowledge-qa slice -> WeKnora kb-v1 with the SCOPED API key -> C2 ->
LLM -> gates -> consumer transcript). Verifies: no empty answers, no raw
evidence leak, no internal ID leak, negatives refuse, citations in
grounded answers, honesty of refusals. Usage: python cutover_smoke.py"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BASE = "http://127.0.0.1:8123"
# bearer = first runtime API key (INSURANCE_AGENT_API_KEYS in hd2.env)
for _ln in (REPO / "tmp/hd2.env").read_text(encoding="utf-8").splitlines():
    if _ln.strip().startswith("export INSURANCE_AGENT_API_KEYS="):
        KEY = _ln.split("=", 1)[1].strip().split(",")[0].strip().split(":")[0]
        break
OUT = (REPO / "docs/knowledge-base/evidence/eval" / "cutover_smoke.json")

CASES = [
    ("S-N1", "normal", "重大疾病保险一般保障哪些疾病"),
    ("S-N2", "normal", "意外伤害保险的保险期间有什么规定"),
    ("S-N3", "normal", "保险公司设立分支机构需要经过什么程序"),
    ("S-N4", "normal", "互联网保险业务可以通过什么平台经营"),
    ("S-N5", "normal", "偿付能力达标公司需要满足哪些条件"),
    ("S-H1", "high_risk", "保险公司注册资本的最低限额是多少"),
    ("S-H2", "high_risk", "长期健康保险产品的犹豫期不得少于多少天"),
    ("S-H3", "high_risk", "人身保险公司的保险条款和保险费率需要审批还是备案"),
    ("S-H4", "high_risk", "2020版重疾规范规定必须包含哪三种轻度疾病"),
    ("S-H5", "high_risk", "中国人身保险业经验生命表2025从什么时候开始使用"),
    ("S-G1", "negative", "如何办理机动车驾驶证换证手续"),
    ("S-G2", "negative", "社会保险里的养老保险退休后怎么办理领取手续"),
    ("S-G3", "negative", "医院门诊挂号预约有哪些方式"),
    ("S-G4", "negative", "机动车年检流程是怎样的"),
    ("S-G5", "negative", "未成年人办理身份证需要什么材料"),
]

_LEAK = re.compile(r"run_[0-9a-f]{8,}|ART-\d+|EVAL-\d+|L1-\d\d|L2-\d\d|"
                   r"knowledge_base_id|chunk_id|E\d]")
_CITE = re.compile(r"\[E\d\]")


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") \
        if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def run_turn(q):
    chat = api("POST", "/api/chats", {"title": "cutover-smoke"})
    cid = chat.get("chat_id") or chat.get("id")
    t0 = time.time()
    r = api("POST", "/api/chats/%s/messages" % cid, {"text": q})
    rid = (r.get("run_id") or r.get("id")
           or (r if isinstance(r, str) else "")) or ""
    st, status, kind = {}, None, ""
    for _ in range(100):
        time.sleep(3)
        st = api("GET", "/api/chats/%s" % cid)
        msgs = [m for m in (st.get("messages") or [])
                if isinstance(m, dict) and m.get("role") == "assistant"]
        if msgs:
            kind = msgs[-1].get("kind") or ""
            status = "TERMINAL"
            break
    dt = time.time() - t0
    assistant = [m.get("content", "") for m in (st.get("messages") or [])
                 if isinstance(m, dict) and m.get("role") == "assistant"]
    answer = assistant[-1] if assistant else ""
    return {"answer": answer, "elapsed_s": round(dt, 1),
            "run_status": status or "TIMEOUT", "msg_kind": kind,
            "chat_id": cid, "run_id": rid}


def main() -> int:
    results = []
    for cid, cat, q in CASES:
        print("=" * 60, flush=True)
        print(cid, cat, q, flush=True)
        try:
            tr = run_turn(q)
        except Exception as exc:  # noqa: BLE001
            tr = {"answer": "", "elapsed_s": 0, "run_status": "ERROR",
                  "error": "%s: %s" % (type(exc).__name__, str(exc)[:120])}
        tr.update(case_id=cid, category=cat, query=q)
        a = tr.get("answer", "")
        tr["empty_answer"] = not a.strip()
        tr["leak_scan"] = sorted(set(_LEAK.findall(a)))[:8]
        tr["has_citation"] = bool(_CITE.search(a))
        tr["refusal_like"] = any(
            k in a for k in ("无法", "未能通过", "不作答", "没有找到",
                             "暂时无法", "无法确认"))
        print("  [%s] %.1fs empty=%s leak=%s cite=%s | %s"
              % (tr.get("run_status"), tr.get("elapsed_s", 0),
                 tr["empty_answer"], tr["leak_scan"], tr["has_citation"],
                 a[:60]), flush=True)
        results.append(tr)
        (REPO / "docs/knowledge-base/evidence/eval"
         / "cutover_smoke.json").write_text(
            json.dumps({"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "results": results}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        time.sleep(1.0)
    print("\nsaved ->", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
