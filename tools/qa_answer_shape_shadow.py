#!/usr/bin/env python3
"""28.C-4A answer-shape prompt SHADOW experiment (experiment only).

Same 5 questions as 28.C-4; evidence is retrieved ONCE per question and
reused for BOTH arms (exact same evidence → no retrieval variance).
Same model (glm-5.3-flash, production QA tier), same gateway, same gate
(the C-4 in-process recorder delegates byte-identically), same retry.
The ONLY variable: Arm B appends a minimal answer-shape constraint to
the system prompt AT THE REQUEST LAYER (production prompt file untouched).

Writes tmp/obs/c4a_shadow.json.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

QUESTIONS = [
    "帮我解释一下百万医疗险的免赔额和续保条件是怎么规定的。",
    "百万医疗险和重疾险有什么区别？",
    "意外险和医疗险有什么不同？",
    "保险的等待期是什么意思？",
    "什么是保险的现金价值？",
]

SHAPE_CONSTRAINT = (
    "\n\n回答形态要求（不改变引用规则）：\n"
    "- 不要使用 Markdown 标题（# / ## / ###）。\n"
    "- 不要输出“第 X 部分 / 一、二、三”等结构化标题。\n"
    "- 不要输出关于引用过程、证据不足、系统限制、[E#] 标记本身的"
    "元叙述。\n"
    "- 直接回答用户问题，使用连贯的段落文字。\n"
    "- 事实性陈述仍必须按照现有引用规则引用 evidence。"
)

GENERIC = {"保险", "条款", "投保", "保障", "医疗", "疾病"}
STRUCT = re.compile(r"^(#|\*\*|[0-9]+[\.\、]|[-\*] |\*|《)|(:|：)$|"
                    r"(说明|建议|以下|提供|无法|解读|参考|总结|如下|情况|进一步)")


def _setup_env() -> None:
    def priv(name):
        try:
            with open(os.path.join(REPO, "tmp", name), encoding="utf-8",
                      errors="replace") as fh:
                for line in fh:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        return s
        except OSError:
            return ""
        return ""
    os.environ["INSURANCE_AGENT_MODE"] = "controlled_pilot"
    os.environ.setdefault("INSURANCE_AGENT_KNOWLEDGE_PROVIDER", "weknora")
    os.environ.setdefault("INSURANCE_AGENT_WEKNORA_URL", "http://127.0.0.1:8080")
    os.environ.setdefault("INSURANCE_AGENT_WEKNORA_API_KEY", priv("hd2.key"))
    os.environ.setdefault("AGENT_PG_PASSWORD", priv("hd2.pgpass"))
    os.environ.setdefault("INSURANCE_AGENT_DATA_KEY", priv("hd2-data.key"))
    os.environ.setdefault(
        "INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID",
        "54d7b757-f6e0-4c29-8de0-e40e92d8464a")
    os.environ.setdefault("INSURANCE_AGENT_WEKNORA_SEARCH_METHOD",
                          "vector_search")


GATE_LOG: list = []


def _install_gate_recorder() -> None:
    from runtime.grounding import gate as ggate
    _orig = ggate.check
    _rules = ggate.load_rules()

    def recording_check(answer, evidence_map, rules=None, _o=_orig,
                        _r=_rules):
        verdict = _o(answer, evidence_map, rules)
        if not verdict["ok"]:
            sents = ggate.split_sentences(answer or "", _r)
            markers = _r["gate"]["fact_markers"]
            det = []
            for v in verdict.get("violations", []):
                m = re.match(r"fact_sentence:no_citation:(\d+)", v)
                if not m:
                    continue
                i = int(m.group(1))
                seg = sents[i] if i < len(sents) else "?"
                hit = [w for w in markers if w in seg]
                det.append({"idx": i, "text": seg[:80], "markers": hit,
                            "structural": bool(STRUCT.search(seg))})
            GATE_LOG.append({"violations": verdict["violations"],
                             "sentences": det})
        return verdict                      # delegate — unchanged result

    ggate.check = recording_check


def main() -> int:
    _setup_env()
    _install_gate_recorder()
    from runtime.agent.config import load_llm_config
    from runtime.grounding import gate as ggate
    from runtime.grounding.loop import build_gateway, generate_grounded
    from runtime.qa_agent import system_prompt
    from knowledge.service import default_service
    from runtime.grounding import context as gctx

    cfg = load_llm_config()
    provider = cfg.to_provider(qa=True)          # glm-5.3-flash (fixed)
    rules = ggate.load_rules()
    svc = default_service()
    gateway = build_gateway(provider, rules)
    base_prompt = system_prompt(rules)
    intent = {"intent_id": "insurance_qa", "confidence": 0.9,
              "confidence_source": "rules", "reason_codes": [],
              "clarification_required": False}

    results = []
    for q in QUESTIONS:
        items, governed, _d, _c = svc.build_evidence(q, top_k=8)
        evidence = [("E%d" % (i + 1),
                     {"content": it.get("content", ""),
                      "header": "hdr", "anchor": gctx.anchor(it)})
                    for i, it in enumerate(items[:8])]
        retrieval = gctx.retrieval(q, 8, "weknora",
                                   getattr(governed, "status", ""), 0, 0,
                                   False)
        for arm, prompt in (("A", base_prompt),
                            ("B", base_prompt + SHAPE_CONSTRAINT)):
            GATE_LOG.clear()
            streamed = []
            ctx_out = generate_grounded(
                q, evidence, intent, retrieval, gateway, rules, prompt,
                emit=lambda t, d: streamed.append(d))
            viol = [dict(g) for g in GATE_LOG]
            sents_all = viol[0]["sentences"] if viol else []
            # answer shape metrics from the streamed+held corpus: use the
            # union of violating sentences + streamed pass sentences
            answer_text = "".join(
                str((d or {}).get("text") or "") for d in streamed)
            structural_v = sum(1 for a in viol for s in a["sentences"]
                               if s["structural"])
            results.append({
                "question": q, "arm": arm, "model": provider.model,
                "evidence_count": len(items),
                "streamed_chars": len(answer_text),
                "streamed_sentences": len(
                    [d for d in streamed
                     if (d or {}).get("kind") == "content"]),
                "markdown_headings_streamed":
                    len(re.findall(r"(?m)^#", answer_text)),
                "total_violations": sum(
                    len(a["sentences"]) for a in viol),
                "structural_violations": structural_v,
                "prose_violations": sum(len(a["sentences"])
                                        for a in viol) - structural_v,
                "gate_attempts_logged": len(viol),
                "grounding_status": ctx_out["grounding_status"],
                "failure_reason": ctx_out["failure_reason"],
                "attempts": (ctx_out.get("generation") or {}).get(
                    "attempts"),
            })
            print("[shadow] %-14s arm%s ev=%d viol=%d struct=%d -> %s" % (
                q[:12], arm, len(items), results[-1]["total_violations"],
                structural_v, ctx_out["grounding_status"]), flush=True)

    path = os.path.join(REPO, "tmp", "obs", "c4a_shadow.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
    a = [r for r in results if r["arm"] == "A"]
    b = [r for r in results if r["arm"] == "B"]
    print("\nArm A: viol=%d struct=%d rejected=%d" % (
        sum(r["total_violations"] for r in a),
        sum(r["structural_violations"] for r in a),
        sum(1 for r in a if r["grounding_status"] == "refused")))
    print("Arm B: viol=%d struct=%d rejected=%d" % (
        sum(r["total_violations"] for r in b),
        sum(r["structural_violations"] for r in b),
        sum(1 for r in b if r["grounding_status"] == "refused")))
    print("written: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
