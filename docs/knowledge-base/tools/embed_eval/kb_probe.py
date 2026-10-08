# -*- coding: utf-8 -*-
"""Single-turn live probe for rollback rehearsal: sends one QA query to
:8123 and classifies the refusal template (which discriminates KBs:
L1-08 保险经纪人 lives only in kb-v1). Usage: python kb_probe.py <q>"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8123"
REPO = "D:\\Workspace\\insurance-agent"
key = None
for ln in open(REPO + "\\tmp\\hd2.env", encoding="utf-8"):
    if ln.strip().startswith("export INSURANCE_AGENT_API_KEYS="):
        key = ln.split("=", 1)[1].strip().split(",")[0].strip().split(":")[0]
        break


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") \
        if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


q = sys.argv[1]
cid = api("POST", "/api/chats", {"title": "rehearsal"})["chat_id"]
t0 = time.time()
api("POST", "/api/chats/%s/messages" % cid, {"text": q})
answer, kind = "", ""
for _ in range(100):
    time.sleep(3)
    st = api("GET", "/api/chats/%s" % cid)
    asst = [m for m in (st.get("messages") or [])
            if isinstance(m, dict) and m.get("role") == "assistant"]
    if asst:
        answer = asst[-1].get("content", "")
        kind = asst[-1].get("kind") or ""
        break
dt = time.time() - t0
if "引用校验" in answer:
    verdict = "citation_gate_rejected (evidence found -> gated)"
elif "暂无可靠依据" in answer:
    verdict = "insufficient_evidence (no relevant evidence)"
elif "知识服务当前不可用" in answer:
    verdict = "kb_unavailable"
else:
    verdict = "OTHER/answered"
print(json.dumps({"query": q[:24], "elapsed_s": round(dt, 1),
                  "kind": kind, "verdict": verdict,
                  "answer_head": answer[:50]}, ensure_ascii=False))
