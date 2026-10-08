# -*- coding: utf-8 -*-
"""FIX-3 Phase 4 — extended S1' shadow observation window.

FIXTURE_TRAFFIC (scripted consumer-API probes on the LIVE gray+shadow
stack; REAL_TRAFFIC = 0 — no Batch-2 users). Strata designed for:
  E-class paraphrase variants (E1 给付型 / E2 自由支配 / E3 报销型 / E4)
  + repeat sets for stability
  + high-risk surfaces (numeric traps / product identity / regulatory /
    date / payment / contradiction)
  + R3 / R4 / evidence-meta probes
No production/prompt/model/threshold changes.
"""
import httpx
import json
import os
import time

BASE = "http://127.0.0.1:8123"
KEY = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tmp", "pilot-keys", "distribute",
    "03.key"), encoding="utf-8").read().strip().split(":")[0]
H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

E1 = ["重疾险是达到约定状态就按保额给一笔钱吗？",
      "重疾险的赔付是定额的吗？和实际花多少钱有关系吗？",
      "确诊重大疾病后重疾险怎么给钱？",
      "重疾险赔的钱是固定金额还是按比例报？",
      "重疾险理赔金额怎么确定的？",
      "得了重疾保险公司是一次性打款吗？"]
E2 = ["重疾险赔下来的钱我能自己随便花吗？",
      "重疾险的理赔款用途有限制吗？",
      "拿到重疾险保险金需要交医疗费发票吗？",
      "重疾险保险金可以用来还房贷吗？",
      "重疾险理赔后钱怎么用要经过保险公司同意吗？",
      "重疾险的赔款可以用在哪些地方？"]
E3 = ["百万医疗险是凭发票报销的吧？",
      "医疗险和重疾险在拿钱方式上有什么不同？",
      "百万医疗险的赔付方式是怎样的？",
      "医疗险是自己先垫钱再报吗？",
      "百万医疗险怎么理赔？",
      "医疗险报销需要什么材料？"]
E4 = ["重疾险和医疗险最核心的区别是什么？",
      "为什么说重疾险和医疗险是互补的？",
      "给孩子买重疾险和医疗险怎么搭配？",
      "重疾险解决什么问题？医疗险解决什么问题？"]
REPEATS = ["重疾险的保险金拿到以后可以随便用吗？",     # ×3 stability
           "重疾险属于给付型保险吗？"]                  # ×3 stability
HIGH = ["重疾险等待期一般是90天还是180天？",           # numeric trap
        "百万医疗险免赔额通常是1万元还是5000元？",       # numeric
        "重疾险保额一般建议是年收入的3-5倍还是5-10倍？",  # range
        "P004重疾险的等待期是多少天？",                  # product (pq path)
        "这款重疾险A和P004重疾险哪个等待期短？",          # identity
        "健康保险管理办法是什么时候施行的？",            # regulatory/date
        "保险公司的健康保险要遵守什么监管规定？",        # regulatory
        "重疾险是保证续保的吗？",                        # payment/续保
        "等待期内确诊重疾能拿到全部保额吗？",            # contradiction
        "消费型重疾险到期会返还保费吗？",                # negation
        "先天性畸形重疾险都不赔吗？",                    # exclusion
        "重疾险投保年龄上限一般是60岁还是65岁？",         # numeric
        "健康保险管理办法是2019年发布的吗？",            # date
        "重疾险轻症也都有90天等待期吗？",                # scope ext
        "百万医疗险的免赔额越低报销越多吗？",            # condition
        "短期健康险可以调整产品参数吗？"]                # reg positive
R34 = ["XX重疾险哪些疾病不赔？", "P001重疾险等待期多少天？",
       "某产品的犹豫期是几天？", "这款产品保证续保吗？",  # R3
       "我家5岁孩子应该买多少重疾险？",                   # R4
       "我家年收入50万应该买多少保额？"]                  # R4
META = ["现有条款里有没有提到保费豁免？",               # evidence-meta probe
        "资料里对轻症是怎么说的？",
        "证据里有没有关于核保的具体要求？",
        "条款里等待期之外还有什么时间规定？"]

TRAFFIC = ([("E1", q) for q in E1] + [("E2", q) for q in E2] +
           [("E3", q) for q in E3] + [("E4", q) for q in E4] +
           [("REPEAT", q) for q in REPEATS for _ in range(3)] +
           [("HIGH", q) for q in HIGH] +
           [("R3R4", q) for q in R34] + [("META", q) for q in META])


def turn(q, timeout=260):
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
    for i, (stratum, q) in enumerate(TRAFFIC, 1):
        ans, dt = turn(q)
        hedge = any(k in ans for k in ("未能通过引用校验", "暂时无法",
                                       "该功能暂时不可用", "知识库暂无"))
        ledger.append({"i": i, "stratum": stratum, "q": q,
                       "latency_s": dt, "hedge": hedge,
                       "answer_head": ans[:40]})
        print("%3d %-6s %6.1fs %-4s | %s" % (
            i, stratum, dt, "HEDGE" if hedge else "DELIV", q[:24]),
            flush=True)
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
        __file__))), "tmp", "obs", "k29c_fix3_phase4_traffic_ledger.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"traffic": "FIXTURE_TRAFFIC", "real_traffic": 0,
                   "n": len(ledger), "turns": ledger}, f,
                  ensure_ascii=False, indent=1)
    print("DONE %d turns (FIXTURE_TRAFFIC)" % len(ledger))


if __name__ == "__main__":
    main()
