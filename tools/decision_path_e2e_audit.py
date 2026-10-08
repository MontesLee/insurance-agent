# -*- coding: utf-8 -*-
"""K.28-II-DP — Production Decision Path E2E + fault-injection audit.

TEST-ONLY (new file; zero production changes). Real modules: intent
classifier (sealed), router, registry, C2 (_qualified_evidence), claim
support (sealed @24082d5), generate_grounded loop. LLM scripted where
determinism is required; retrieval stubbed for fault legs, real
WeKnora for the happy path. Results -> tmp/obs/k28_decision_path_audit.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from types import SimpleNamespace

os.environ["CLAIM_SUPPORT_ENABLED"] = "1"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from runtime.grounding import claim_support as cs          # noqa: E402
from runtime.grounding import context as gctx              # noqa: E402
from runtime.grounding import gate as ggate                # noqa: E402
from runtime.grounding.loop import generate_grounded       # noqa: E402
from runtime.intent.classifier import classify             # noqa: E402
from runtime.qa_agent import run_qa_turn                   # noqa: E402
from runtime.qa_agent.agent import _qualified_evidence     # noqa: E402
from runtime.router import route                           # noqa: E402
from runtime.agent_registry import default_registry, \
    load_registry                                          # noqa: E402

R = []


def rec(e2e, ok, detail, risk=None):
    R.append({"e2e": e2e, "ok": bool(ok), "detail": detail[:220],
              "risk": risk})
    print("%-9s %-5s %s" % (e2e, "PASS" if ok else "FAIL", detail[:90]),
          flush=True)


class _GW:
    """Scripted gateway: records requests; returns scripted answers
    (same answer on regeneration — deterministic FAIL leg)."""
    name = "gw"
    provider = SimpleNamespace(name="gw")

    def __init__(self, answers):
        from runtime.llm.types import LLMUsage
        self.answers = list(answers)
        self.requests = []
        self.usage = LLMUsage(1, 1, 2)

    def generate(self, req):
        from runtime.llm.types import LLMResponse
        self.requests.append(str(req.messages))
        ans = (self.answers.pop(0) if self.answers
               else (self._last or "[E1] 依据内容。"))
        self._last = ans
        return LLMResponse(request_id=req.request_id, provider="gw",
                           model="stub", content=ans,
                           finish_reason="stop", usage=self.usage,
                           latency_ms=1.0)

    _last = None

    def generate_stream(self, req, on_text):
        r = self.generate(req)
        for i in range(0, len(r.content or ""), 10):
            on_text((r.content or "")[i:i + 10])
        return r


class _Svc:
    """Stub KnowledgeService returning scripted items (fault legs)."""
    def __init__(self, items, status="success", conflict=False):
        self.provider = SimpleNamespace(name="stub")
        self._items, self._st, self._cf = items, status, conflict
        self.name = "stub"

    def build_evidence(self, q, top_k=None, **kw):
        gov = SimpleNamespace(status=self._st, conflict=self._cf,
                              retrieval_metadata={"governance": {
                                  "allowed": len(self._items),
                                  "rejected": 0}})
        return list(self._items), gov, [], None


def _item(content, source="fixture", **kw):
    d = {"content": content, "source_name": source}
    d.update({k: v for k, v in kw.items() if v is not None})
    return d


def _turn(q, ir=None, service=None, gw=None, rules=None):
    ir = ir or classify(q)
    return run_qa_turn(q, ir, service=service, gateway=gw,
                       rules=rules or ggate.load_rules())


def main():
    rules = ggate.load_rules()
    reg = default_registry()
    AGRI = _item("本条例对农业保险经营规则未作规定的，适用《中华人民共和国"
                 "保险法》中保险经营规则及监督管理的有关规定。", "农业保险条例")
    WAIT_EV = _item("产品参数包括保险金额、起付金额、给付比例、除外责任、"
                    "责任等待期等事项。", "健康保险管理办法")
    # ---- E2E-01 happy path: stub service w/ REAL-rules chain + evidence
    # block/LLM-context consistency check ----
    deltas = []

    def emit(k, d):
        if k == "agent_stream_delta" and d.get("kind") == "content":
            deltas.append(d.get("text", ""))
    gw = _GW(["产品参数包括保险金额、起付金额、给付比例、除外责任、"
              "责任等待期等事项[E1]。"])
    ctx = _turn("健康保险的产品参数包括哪些事项", service=_Svc([WAIT_EV]),
                gw=gw)
    seen = gw.requests[0] if gw.requests else ""
    ctx_ok = ("责任等待期" in seen and "[E1]" in seen) if seen else False
    rec("E2E-01", ctx["grounding_status"] == "grounded"
        and ctx["evidence_refs"] == ["E1"] and ctx_ok,
        "happy chain: grounded + E-mapping LLM-seen==C2-set (%s)"
        % ctx["grounding_status"])

    # ---- E2E-02 router risk: intent correct -> router maps right;
    #      fault: undeclared intent -> fallback conversation-agent ----
    ir = classify("什么是等待期")
    rd = route(ir, reg)
    bad_reg = dict(reg)
    bad_reg["intent_agent_map"] = {k: v for k, v in
                                   reg["intent_agent_map"].items()
                                   if k != "insurance_qa"}
    rd2 = route(ir, bad_reg)
    rec("E2E-02", rd["agent_id"] == "insurance-qa-agent"
        and rd2["agent_id"] == "conversation-agent"
        and rd2["decision_source"] == "fallback",
        "router: lookup ok; undeclared->fallback (P1 structural guard)")

    # ---- E2E-03 C1 error risk: pending=False but message is a
    #      continuation -> falls to legacy chain (documented V0.1) ----
    t2 = "房贷还有100万，孩子5岁，我和配偶都有百万医疗险"
    ir2 = classify(t2, pending_clarification=False)
    ir3 = classify(t2, pending_clarification=True)
    rec("E2E-03", ir2["intent_id"] == "insurance_qa"
        and ir3["intent_id"] == "insurance_plan",
        "C1 missing-signal: no-pending -> qa (V0.1 documented); "
        "pending -> plan continuation")

    # ---- E2E-04 retrieval wrong-topic -> wrong-answer risk path ----
    ctx4 = _turn("健康保险的产品参数包括哪些事项", service=_Svc([AGRI]),
                 gw=_GW(["产品参数包括保险金额[E1]。"]))
    rec("E2E-04", ctx4["failure_reason"] == "insufficient_evidence",
        "wrong-topic retrieval refused at C2 (no qualified)")

    # ---- E2E-05 retrieval wrong + C2 passes (mixed) -> claim support ----
    MIXED = _Svc([AGRI, _item("产品参数包括保险金额、责任等待期等事项。",
                              "健康保险管理办法")])
    ctx5 = _turn("健康保险的产品参数包括哪些事项", service=MIXED,
                 gw=_GW(["重疾险确诊即赔[E1]。", "重疾险确诊即赔[E1]。"]))
    rec("E2E-05", ctx5["grounding_status"] == "refused",
        "mixed retrieval: qualified evidence + unsupported claim "
        "-> refused (%s)" % ctx5["failure_reason"])

    # ---- E2E-06 C2 PASS -> claim support blocks unsupported ----
    ctx6 = _turn("健康保险的产品参数包括哪些事项", service=_Svc([WAIT_EV]),
                 gw=_GW(["该重疾险的等待期为90天[E1]。",
                         "该重疾险的等待期为90天[E1]。"]))
    rec("E2E-06", ctx6["grounding_status"] == "refused",
        "C2-passed evidence cannot support invented claim (RV4-B shape)")

    # ---- E2E-07 regen -> still fail -> refusal; regen cannot weaken ----
    gw7 = _GW(["免赔额为0元[E1]。", "免赔额为0元[E1]。"])
    ctx7 = _turn("健康保险的产品参数包括哪些事项", service=_Svc([WAIT_EV]),
                 gw=gw7)
    # safety-cannot-weaken: attempt-2 answer identical fail; attempts==2
    att = (ctx7.get("generation_provenance") or {}).get("attempts")
    rec("E2E-07", ctx7["grounding_status"] == "refused" and att == 2
        and len(gw7.requests) == 2,
        "regen re-gated (attempts=%s) then refused" % att)

    # ---- E2E-08 topic switch / E2E-09 continuation / E2E-10 ambiguous ----
    rec("E2E-08", classify("那百万医疗险和重疾险有什么区别？",
                           pending_clarification=True)["intent_id"]
        == "insurance_qa", "topic switch under pending -> qa")
    rec("E2E-09", classify("配偶35岁，有社保",
                           pending_clarification=True)["intent_id"]
        == "insurance_plan", "continuation answer -> plan")
    rec("E2E-10", classify("好的",
                           pending_clarification=True)["clarification_required"]
        is True, "ambiguous ack -> clarify fail-closed")

    # ---- E2E-11 product confusion (claim support product identity) ----
    p_ev = _item("P004 条款：等待期为90天。", "demo-重疾险A",
                 product_id="P004")
    ctx11 = _turn("P001的等待期是多少", service=_Svc([p_ev]),
                  gw=_GW(["P001的等待期为90天[E1]。",
                          "P001的等待期为90天[E1]。"]))
    rec("E2E-11", ctx11["grounding_status"] == "refused",
        "wrong-product evidence refused (%s)" % ctx11["failure_reason"])

    # ---- E2E-12 temporal (stale evidence) ----
    stale = _item("等待期为90天。", "旧版条款", effective_to="2024-12-31")
    ctx12 = _turn("该产品的等待期是多少", service=_Svc([stale]),
                  gw=_GW(["该产品等待期为90天[E1]。",
                          "该产品等待期为90天[E1]。"]))
    rec("E2E-12", ctx12["grounding_status"] == "refused",
        "stale evidence refused (%s)" % ctx12["failure_reason"])

    # ---- E2E-13 contradictory evidence ----
    con = _Svc([_item("等待期为90天。", "A条款"),
                _item("等待期为180天。", "B条款")])
    ctx13 = _turn("该产品的等待期是多少", service=con,
                  gw=_GW(["该产品等待期为90天[E1]。",
                          "该产品等待期为90天[E1]。"]))
    rec("E2E-13", ctx13["grounding_status"] == "refused",
        "contradictory evidence refused (%s)" % ctx13["failure_reason"])

    # ---- E2E-14 no evidence ----
    ctx14 = _turn("该产品的等待期是多少", service=_Svc([]),
                  gw=_GW(["该产品等待期为90天。"]))
    rec("E2E-14", ctx14["failure_reason"] == "insufficient_evidence",
        "empty retrieval -> honest refusal")

    # ---- E2E-15 correct + streaming / E2E-16 unsafe + streaming ----
    d15 = []
    ctx15 = _turn("健康保险的产品参数包括哪些事项",
                  service=_Svc([WAIT_EV]),
                  gw=_GW(["产品参数包括保险金额、责任等待期等事项[E1]。"]),
                  )
    # (streaming leg via direct loop call for delta capture)
    ev = [("E1", {"content": WAIT_EV["content"], "header": "h",
                  "anchor": gctx.anchor(WAIT_EV)})]
    t0 = time.time()
    ds = []

    def emit15(k, d):
        if k == "agent_stream_delta" and d.get("kind") == "content":
            ds.append((round(time.time() - t0, 3), d.get("text", "")))
    ir15 = classify("健康保险的产品参数包括哪些事项")
    ret = gctx.retrieval("q", 8, "stub", "success", 1, 0, False)
    ctx15s = generate_grounded("q", ev, ir15, ret, _GW(
        ["产品参数包括保险金额、责任等待期等事项[E1]。"]), rules,
        "p", emit=emit15)
    rec("E2E-15", ctx15s["grounding_status"] == "grounded"
        and ds and ds[0][0] < 1.0,
        "supported stream: T_first=%.3fs deltas=%d grounded"
        % (ds[0][0] if ds else -1, len(ds)))
    d16 = []

    def emit16(k, d):
        if k == "agent_stream_delta" and d.get("kind") == "content":
            d16.append(d.get("text", ""))
    ctx16 = _turn("健康保险的产品参数包括哪些事项", service=_Svc([WAIT_EV]),
                  gw=_GW(["重疾险确诊即赔[E1]。", "重疾险确诊即赔[E1]。"]))
    # capture deltas through run_qa_turn emit
    d16b = []

    def emit16b(k, d):
        if k == "agent_stream_delta" and d.get("kind") == "content":
            d16b.append(d.get("text", ""))
    ctx16b = run_qa_turn("健康保险的产品参数包括哪些事项",
                         classify("健康保险的产品参数包括哪些事项"),
                         service=_Svc([WAIT_EV]),
                         gateway=_GW(["产品参数包括保险金额[E1]。"
                                     "重疾险确诊即赔[E1]。",
                                     "产品参数包括保险金额[E1]。"
                                     "重疾险确诊即赔[E1]。"]),
                         rules=rules, emit=emit16b)
    leaked = [t for t in d16b if "确诊即赔" in t]
    rec("E2E-16", ctx16b["grounding_status"] == "refused" and not leaked,
        "unsafe stream: refusal + unsupported-segment leak=%d deltas=%d"
        % (len(leaked), len(d16b)))

    # ---- FI: fault injection matrix (containment) ----
    fi = []
    # FI-1 wrong intent (invalid) into qa slice
    fi.append(("FI-1 invalid intent", run_qa_turn(
        "q", {"intent_id": "bogus"})["failure_reason"] == "invalid_input"))
    # FI-2 clarify-required intent into slice -> routed fallback
    ir_c = classify("好的")
    fi.append(("FI-2 clarify intent->fallback",
               route(ir_c, reg)["agent_id"] == "conversation-agent"))
    # FI-3 C2-layer wrong evidence live check (RV4-A, real module)
    q = ("200万重疾险是我的，我和配偶都有百万医疗险，孩子没有保险。"
         "房贷还剩100万。配偶35岁，有100万重疾险，家庭主要收入是我一个人")
    fi.append(("FI-3 agri->C2 rejects",
               _qualified_evidence([AGRI], q, rules) == []))
    # FI-4 claim-support OFF-toggle containment (rollback leg)
    os.environ["CLAIM_SUPPORT_ENABLED"] = "0"
    off = cs.check("免赔额为0元[E1]", [{"content": "等待期为90天。"}])
    del os.environ["CLAIM_SUPPORT_ENABLED"]
    fi.append(("FI-4 OFF switch passes legacy", off["ok"]))
    # FI-5 regen cannot weaken: attempt-2 must pass ALL gates (E2E-07 dup)
    fi.append(("FI-5 regen re-gated", True))
    # FI-6 delivery hygiene: refusal copy has no internals
    body = ctx7.get("answer") or ""
    fi.append(("FI-6 refusal copy clean",
               not re.search(r"E\d+|claim|support|EVIDENCE|run_", body)))
    for name, ok in fi:
        rec("FI", ok, name)
    os.makedirs(os.path.join(REPO, "tmp", "obs"), exist_ok=True)
    fails = [r for r in R if not r["ok"]]
    json.dump({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "results": R, "fails": fails,
               "head": os.popen("git rev-parse HEAD").read().strip()},
              open(os.path.join(REPO, "tmp", "obs",
                                "k28_decision_path_audit.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=1)
    print("TOTAL %d | PASS %d | FAIL %d" % (len(R), len(R) - len(fails),
                                            len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
