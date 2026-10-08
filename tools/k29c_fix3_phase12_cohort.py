# -*- coding: utf-8 -*-
"""FIX-3 Phase 12 — scripted-probe cohort (Owner-approved cohort form).
Covers eligible paraphrase shapes + hard-blocked classes + blockers,
drives the LIVE authority stack through the consumer API."""
import httpx
import json
import os
import time

BASE = "http://127.0.0.1:8123"
KEY = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tmp", "pilot-keys", "distribute",
    "03.key"), encoding="utf-8").read().strip().split(":")[0]
H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

COHORT = [
    # eligible-shape probes (E-class paraphrase questions)
    ("E", "重疾险的保险金拿到以后可以随便用吗？"),
    ("E", "重疾险是达到约定状态就按保额给一笔钱吗？"),
    ("E", "重疾险理赔的钱可以自己安排用途吗？"),
    ("E", "百万医疗险是凭发票报销的吧？"),
    ("E", "医疗险和重疾险在拿钱方式上有什么不同？"),
    ("E", "重疾险赔的钱是固定金额吗？"),
    ("E", "重疾险的赔付和实际医疗花费有关系吗？"),
    ("E", "重疾险和医疗险最核心的区别是什么？"),
    ("E", "为什么说重疾险和医疗险是互补的？"),
    ("E", "重疾险解决什么问题？医疗险解决什么问题？"),
    ("E", "得了重疾保险公司是一次性打款吗？"),
    ("E", "医疗险报销需要什么材料？"),
    ("E", "重疾险的理赔款用途有限制吗？"),
    ("E", "重疾险保险金可以用来还房贷吗？"),
    ("E", "拿到重疾险保险金需要交医疗费发票吗？"),
    ("E", "重疾险理赔后钱怎么用要经过保险公司同意吗？"),
    ("E", "重疾险的赔款可以用在哪些地方？"),
    ("E", "重疾险是定额赔付的吗？"),
    ("E", "医疗险是自己先垫钱再报吗？"),
    ("E", "百万医疗险怎么理赔？"),
    # hard-blocked probes
    ("H", "是不是所有重疾险都能返还保费？"),
    ("H", "健康保险管理办法是什么时候施行的？"),
    ("H", "P004重疾险的等待期是多少天？"),
    ("H", "重疾险等待期一般是90天还是180天？"),
    ("H", "我家5岁孩子应该买多少保额的重疾险？"),
    ("H", "建议您优先为家里收入最高的人配置保障好吗？"),
    ("H", "该产品保证续保吗？"),
    ("H", "等待期内确诊重疾能拿到全部保额吗？"),
    ("H", "重疾险保额一般建议是年收入的多少倍？"),
    ("H", "这款产品XX重疾险哪些疾病不赔？"),
    # blockers (F5-05/BF1-16/BF2-01/BF3-01 shapes as questions)
    ("B", "健康保险管理办法是2019年12月1日施行的吗？"),
    ("B", "重疾险等待期在30到180天之间吗？"),
    ("B", "所有重疾险产品的保险金都可以自由支配吗？"),
    ("B", "我该给我家孩子优先买什么保险？"),
]


def turn(q, timeout=240):
    c = httpx.post(BASE + "/api/chats", headers=H, timeout=15).json()
    cid = c["chat_id"]
    t0 = time.time()
    httpx.post(BASE + "/api/chats/%s/messages" % cid, headers=H,
               json={"text": q}, timeout=300)
    ans = ""
    while time.time() - t0 < timeout and not ans:
        time.sleep(3)
        v = httpx.get(BASE + "/api/chats/%s" % cid, headers=H,
                      timeout=15).json()
        for m in reversed(v.get("messages") or []):
            if m.get("role") == "assistant":
                ans = m.get("content") or ""
                break
    try:
        httpx.delete(BASE + "/api/consumer/chats/%s" % cid, headers=H,
                     timeout=15)
    except Exception:
        pass
    return ans, round(time.time() - t0, 1)


def main():
    ledger = []
    for i, (stratum, q) in enumerate(COHORT, 1):
        ans, dt = turn(q)
        delivered = not any(k in ans for k in (
            "未能通过引用校验", "暂时无法", "知识库暂无",
            "该功能暂时不可用"))
        ledger.append({"i": i, "stratum": stratum, "q": q,
                       "latency_s": dt, "delivered": delivered,
                       "answer_head": ans[:56].replace("\n", " ")})
        print("%2d %s %6.1fs %-9s | %s" % (
            i, stratum, dt, "DELIVERED" if delivered else "baseline",
            ans[:46].replace("\n", " ")), flush=True)
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
        __file__))), "tmp", "obs", "k29c_fix3_phase12_cohort_ledger.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"traffic": "SCRIPTED_PROBE (Owner-approved cohort)",
                   "n": len(ledger), "turns": ledger}, f,
                  ensure_ascii=False, indent=1)
    print("cohort done:", len(ledger), "turns")


if __name__ == "__main__":
    main()
