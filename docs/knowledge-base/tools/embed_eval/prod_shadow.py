# -*- coding: utf-8 -*-
"""§12 Production Shadow: >=30 queries through the REAL production
retrieval path (governed KnowledgeService + PG registry + live WeKnora
provider + agent scoring policy + C2 + LLM gates), in-process, zero
user-visible production change.

Transport note: production authenticates with the scoped retrieve-only
API key (hd2-production-retrieval); its scope extension to kb-v1 is an
Owner-gated cutover step, so this shadow uses the SAME endpoint/payload
with admin Bearer auth (harness-local transport variant). The X-API-Key
path is validated at cutover smoke.

Usage: python prod_shadow.py [start_index]
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

KB = HERE.parents[1]
EVID = KB / "evidence" / "eval"
BASE = "http://127.0.0.1:8080"
KB1 = "44af9ff2-ecef-445e-87c6-cb1458cd4d44"
os.environ["CLAIM_SUPPORT_ENABLED"] = "1"
os.environ["INSURANCE_AGENT_WEKNORA_SEARCH_METHOD"] = "vector_search"

QUERIES = [
    # 10 normal insurance questions
    ("N01", "保险公司倒闭了，我的人寿保险单还有效吗", "normal"),
    ("N02", "什么是保险销售行为可回溯", "normal"),
    ("N03", "重大疾病保险一般保障哪些疾病", "normal"),
    ("N04", "通过互联网买保险需要注意什么", "normal"),
    ("N05", "意外伤害保险的保险期间有什么规定", "normal"),
    ("N06", "银行保险机构收到消费投诉后多久作出处理决定", "normal"),
    ("N07", "保险公司设立分支机构需要经过什么程序", "normal"),
    ("N08", "互联网保险业务可以通过什么平台经营", "normal"),
    ("N09", "偿付能力达标公司需要满足哪些条件", "normal"),
    ("N10", "保险公司销售人身保险产品时应当向消费者披露哪些产品材料",
     "normal"),
    # 5 high-risk fact questions
    ("H01", "保险公司注册资本的最低限额是多少", "high_risk"),
    ("H02", "长期健康保险产品的犹豫期不得少于多少天", "high_risk"),
    ("H03", "人身保险公司的保险条款和保险费率需要审批还是备案",
     "high_risk"),
    ("H04", "2020版重疾规范规定必须包含哪三种轻度疾病", "high_risk"),
    ("H05", "中国人身保险业经验生命表2025从什么时候开始使用", "high_risk"),
    # 5 negative
    ("G01", "如何办理机动车驾驶证换证手续", "negative"),
    ("G02", "社会保险里的养老保险退休后怎么办理领取手续", "negative"),
    ("G03", "医院门诊挂号预约有哪些方式", "negative"),
    ("G04", "机动车年检流程是怎样的", "negative"),
    ("G05", "未成年人办理身份证需要什么材料", "negative"),
    # 5 product / numeric
    ("P01", "保险保障基金由谁缴纳、按什么缴纳", "product_numeric"),
    ("P02", "保险销售可回溯资料应当保存多长时间", "product_numeric"),
    ("P03", "银行保险机构董事近亲属与机构发生的关联交易要经过什么程序",
     "product_numeric"),
    ("P04", "重疾新规下恶性肿瘤轻度疾病有哪些", "product_numeric"),
    ("P05", "不符合2020版定义的重疾产品最迟可以销售到什么时候",
     "product_numeric"),
    # 5 R4 personalization
    ("R01", "我30岁月收入8000元，应该重点买什么保险", "r4_personal"),
    ("R02", "孩子刚出生，预算每年3000元，怎么配置重疾险", "r4_personal"),
    ("R03", "我有100万房贷，需要多少定期寿险保额", "r4_personal"),
    ("R04", "父母50岁了买重疾险要注意什么", "r4_personal"),
    ("R05", "网上买的保险和线下买的保险理赔一样吗", "r4_personal"),
]


class JWTTransport:
    """Harness-local variant of WeKnoraLiveTransport: identical payload
    (query/kb_id/search_method) with admin Bearer auth."""

    def __init__(self, base_url, jwt, timeout=15.0):
        self.base_url = base_url.rstrip("/")
        self.jwt = jwt
        self.timeout = timeout
        self.search_method = os.environ.get(
            "INSURANCE_AGENT_WEKNORA_SEARCH_METHOD", "").strip()

    def __call__(self, payload: dict) -> dict:
        req_body = {"query": payload.get("query", ""),
                    "knowledge_base_id": payload.get("kb_id", "")}
        if self.search_method:
            req_body["search_method"] = self.search_method
        body = json.dumps(req_body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/api/v1/knowledge-search", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self.jwt,
                     "X-Tenant-ID": "10001"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout + 45) as r:
            doc = json.loads(r.read().decode("utf-8"))
        if not isinstance(doc, dict) or doc.get("success") is not True:
            raise RuntimeError("weknora search failed")
        return doc


def main() -> int:
    from knowledge.service import KnowledgeService, pg_registry
    from knowledge.provider.weknora import WeKnoraLiveProvider
    from runtime.grounding import context as gctx
    from runtime.grounding import gate as ggate
    from runtime.grounding import loop as gloop
    from runtime.intent.classifier import classify
    from runtime.qa_agent.agent import _qualified_evidence, system_prompt
    from runtime.agent.config import load_llm_config

    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    jwt = (REPO / "tmp" / "weknora-admin.jwt").read_text(
        encoding="utf-8").strip()
    rules = ggate.load_rules()
    top_k = int((rules.get("retrieval") or {}).get("top_k", 8))

    registry, krs = pg_registry()
    content_map = krs.content_map(only_active=True)
    provider = WeKnoraLiveProvider(
        transport=JWTTransport(BASE, jwt), kb_id=KB1,
        stamps=registry.provider_stamps(), content_map=content_map)
    svc = KnowledgeService(provider=provider, registry=registry)
    llm = load_llm_config().to_provider(qa=True)
    print("registry entries:", len(registry.entries),
          "| content_map docs:", len(content_map), "| llm:", llm.model,
          flush=True)

    shadow_log = []

    def observer(event, data):
        try:
            shadow_log.append((data.get("ok"),
                               (data.get("violations") or [])[:6]))
        except Exception:  # noqa: BLE001
            pass
    gloop.shadow_observer = observer

    out_path = EVID / "prod_shadow_kb1.json"
    record = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "kb": "insurance-kb-v1", "kb_id": KB1,
              "retrieval": "governed KnowledgeService + PG registry + "
                           "live WeKnora provider (JWT transport variant)",
              "model": llm.model, "cases": []}
    if start:
        record["cases"] = json.loads(
            out_path.read_text(encoding="utf-8"))["cases"]

    for cid, q, cat in QUERIES[start:]:
        print("=" * 60, flush=True)
        print(cid, cat, q, flush=True)
        tr = {"case_id": cid, "category": cat, "query": q}
        t_all = time.time()
        try:
            ir = classify(q)
            tr["intent"] = ir["intent_id"]
            t0 = time.time()
            items, governed, decisions, qr = svc.build_evidence(
                q, top_k=top_k)
            t_ret = time.time() - t0
            gm = (getattr(governed, "retrieval_metadata", None) or {}).get(
                "governance", {})
            tr["retrieval"] = {
                "status": getattr(governed, "status", ""),
                "allowed": len(items),
                "denied": gm.get("rejected", 0) or 0,
                "docs": sorted({(it.get("document_name")
                                 or it.get("source_name") or "?")
                                for it in items})[:8],
                "latency_ms": int(t_ret * 1000)}
            qualified = _qualified_evidence(items, q, rules)
            tr["qualified_n"] = len(qualified)
            if not qualified:
                tr["final"] = "REFUSAL"
                tr["reason"] = "insufficient_evidence"
                tr["answer"] = ""
            else:
                evidence = [("E%d" % (i + 1),
                             {"content": it.get("content", ""),
                              "header": gloop.kb_header(it),
                              "anchor": gctx.anchor(it)})
                            for i, it in enumerate(qualified[:top_k])]
                retrieval_rec = gctx.retrieval(
                    q, top_k, "weknora", getattr(governed, "status",
                                                 "success"),
                    len(items), gm.get("rejected", 0) or 0,
                    bool(getattr(governed, "conflict", False)))
                shadow_log.clear()
                gateway = gloop.build_gateway(llm, rules)
                t0 = time.time()
                res = gloop.generate_grounded(
                    q, evidence, ir if ir["intent_id"] in
                    ("insurance_qa", "unknown_insurance_intent") else
                    {"intent_id": "insurance_qa", "confidence": 1.0,
                     "confidence_source": "probe", "context_refs": {},
                     "clarification_required": False,
                     "reason_codes": ["probe"], "created_at": "now"},
                    retrieval_rec, gateway, rules, system_prompt(rules))
                tr["generation_s"] = round(time.time() - t0, 1)
                status = res.get("grounding_status", "")
                tr["final"] = ("ANSWER" if status == "grounded"
                               else "PARTIAL"
                               if status == "partial_grounding" else
                               "REFUSAL")
                tr["reason"] = res.get("failure_reason", "")
                tr["answer"] = (res.get("answer", ""))[:600]
                tr["raw_gate_ok"] = shadow_log[-1][0] if shadow_log \
                    else None
                tr["viol_kinds"] = sorted(set(
                    str(v).split(":")[0] for v in
                    (shadow_log[-1][1] if shadow_log else [])))
        except Exception as exc:  # noqa: BLE001 — record and continue
            tr["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
            tr["final"] = "ERROR"
        tr["total_s"] = round(time.time() - t_all, 1)
        print("  ->", tr.get("final"), tr.get("reason", ""),
              "| ret %dms qual=%s | %.1fs"
              % (tr.get("retrieval", {}).get("latency_ms", -1),
                 tr.get("qualified_n", "-"), tr["total_s"]), flush=True)
        record["cases"].append(tr)
        out_path.write_text(json.dumps(record, ensure_ascii=False,
                                       indent=1), encoding="utf-8")
        time.sleep(1.0)

    gloop.shadow_observer = None
    ok = sum(1 for c in record["cases"] if c.get("final") != "ERROR")
    print("done: %d cases (%d errors) -> %s"
          % (len(record["cases"]),
             len(record["cases"]) - ok, out_path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
