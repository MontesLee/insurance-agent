# -*- coding: utf-8 -*-
"""FIX-3 Phase 3 — observation-window extra turns (evidence-rich QA)
to exercise the final gate + shadow on real generations."""
import httpx, json, time, os, sys

BASE = "http://127.0.0.1:8123"
KEY = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tmp", "pilot-keys", "distribute",
    "03.key"), encoding="utf-8").read().strip().split(":")[0]
H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

EXTRA = [
    "W1 什么是重大疾病保险？它和医疗险有什么区别？",
    "W2 重疾险的保险金拿到以后可以随便用吗？",
    "W3 等待期是什么意思？为什么重疾险要设等待期？",
    "W4 给孩子配置重疾险前一般应该先考虑哪些方面？",
    "W5 健康保险管理办法对保险公司销售有什么要求？",
    "W6 买保险前需要注意什么？有哪些一般原则？",
]

for q in EXTRA:
    c = httpx.post(BASE + "/api/chats", headers=H, timeout=15).json()
    cid = c["chat_id"]
    t0 = time.time()
    r = httpx.post(BASE + "/api/chats/%s/messages" % cid, headers=H,
                   json={"text": q}, timeout=300)
    run_id = (r.json() or {}).get("run_id")
    ans = ""
    while time.time() - t0 < 240:
        time.sleep(3)
        v = httpx.get(BASE + "/api/chats/%s" % cid, headers=H,
                      timeout=15).json()
        for m in reversed(v.get("messages") or []):
            if m.get("role") == "assistant":
                ans = m.get("content") or ""
                break
        if ans:
            break
    try:
        httpx.delete(BASE + "/api/consumer/chats/%s" % cid, headers=H,
                     timeout=15)
    except Exception:
        pass
    print("%-3s %5.1fs | %s" % (q[:2], time.time() - t0,
                                ans[:60].replace("\n", " ")), flush=True)
print("window turns done")
