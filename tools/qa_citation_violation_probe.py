#!/usr/bin/env python3
"""28.C-4 citation-violation distribution probe (OBSERVATION ONLY).

Runs the REAL QA generation path (KnowledgeService evidence -> gateway
-> generate_grounded with the production QA model) on a handful of
questions, wrapping runtime.grounding.gate.check with a recorder so
every gate call's FULL answer text + per-sentence marker/citation
analysis is captured. The wrapper delegates to the original check —
results are byte-identical; only observation is added. No production
file is modified (wrapper lives in THIS script).

Per violating sentence it records:
  text, markers_hit (explicit/generic split), citation_present,
  heuristic V-class (V1 specific-fact-uncited / V2 generic-transition
  / V3 extraction-miss) — final classes are human-reviewed in the report.
Run-level: evidence_count (V5), retries, final result.
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
    "帮我解释一下百万医疗险的免赔额和续保条件是怎么规定的。",   # B-type reject
    "百万医疗险和重疾险有什么区别？",                             # A-type (V5 probe)
    "意外险和医疗险有什么不同？",                                 # weak-evidence probe
    "保险的等待期是什么意思？",                                   # historically HIT
    "什么是保险的现金价值？",                                     # historically HIT
]

GENERIC = {"保险", "条款", "投保", "保障", "医疗", "疾病"}
TRANSITION = ("总结", "以下", "建议", "参考", "如下", "希望", "可以",
              "情况", "以上", "总之", "综合", "了解", "考虑", "结合")


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
            detail = []
            for v in verdict.get("violations", []):
                m = re.match(r"fact_sentence:no_citation:(\d+)", v)
                if not m:
                    continue
                i = int(m.group(1))
                seg = sents[i] if i < len(sents) else "?"
                hit = [w for w in markers if w in seg]
                gen = [w for w in hit if w in GENERIC]
                has_cite = bool(re.findall(_r["citation"]["pattern"], seg))
                looks_transition = (all(w in GENERIC or w in TRANSITION
                                        for w in hit) and gen
                                    and not re.search(r"\d", seg))
                vcls = "V2?" if looks_transition else "V1?"
                if "[" in seg and not has_cite:
                    vcls = "V3?"
                detail.append({"idx": i, "text": seg[:80],
                               "markers": hit, "generic_markers": gen,
                               "citation": has_cite, "class": vcls})
            GATE_LOG.append({"violations": verdict["violations"],
                             "sentences": detail})
        return verdict          # delegated — result unchanged

    ggate.check = recording_check


def main() -> int:
    _setup_env()
    _install_gate_recorder()
    from runtime.agent.config import load_llm_config
    from runtime.grounding import gate as ggate
    from runtime.grounding.loop import (build_gateway, evidence_block,
                                        generate_grounded)
    from runtime.qa_agent import system_prompt
    from knowledge.service import default_service

    cfg = load_llm_config()
    provider = cfg.to_provider(qa=True)          # production QA tier
    rules = ggate.load_rules()
    svc = default_service()
    gateway = build_gateway(provider, rules)

    intent = {"intent_id": "insurance_qa", "confidence": 0.9,
              "confidence_source": "rules", "reason_codes": [],
              "clarification_required": False}
    from runtime.grounding import context as gctx

    out_rows = []
    for q in QUESTIONS:
        GATE_LOG.clear()
        streamed = []
        try:
            items, governed, _d, _c = svc.build_evidence(q, top_k=8)
        except Exception as e:  # noqa: BLE001
            out_rows.append({"question": q, "error": repr(e)[:120]})
            continue
        evidence = [("E%d" % (i + 1),
                     {"content": it.get("content", ""),
                      "header": "hdr",
                      "anchor": gctx.anchor(it)})
                    for i, it in enumerate(items[:8])]
        retrieval = gctx.retrieval(q, 8, "weknora",
                                   getattr(governed, "status", ""), 0, 0,
                                   False)
        emit = lambda t, d: streamed.append(d)  # noqa: E731
        ctx_out = generate_grounded(q, evidence, intent, retrieval,
                                    gateway, rules, system_prompt(rules),
                                    emit=emit)
        out_rows.append({
            "question": q,
            "model": provider.model,
            "evidence_count": len(items),
            "grounding_status": ctx_out["grounding_status"],
            "failure_reason": ctx_out["failure_reason"],
            "gate_violations": (ctx_out.get("violations")
                                or (ctx_out.get("generation") or {}).get(
                                    "gate_violations")),
            "attempts": (ctx_out.get("generation") or {}).get("attempts"),
            "per_attempt_violating_sentences": [dict(g) for g in GATE_LOG],
            "streamed_passing_sentences": len(
                [d for d in streamed
                 if (d or {}).get("kind") == "content"]),
        })
        print("[probe] %-24s ev=%d %s/%s attempts=%s viol-sents=%d" % (
            q[:12], len(items), ctx_out["grounding_status"],
            ctx_out["failure_reason"],
            (ctx_out.get("generation") or {}).get("attempts"),
            sum(len(g["sentences"]) for g in GATE_LOG)), flush=True)

    path = os.path.join(REPO, "tmp", "obs", "c4_violations.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out_rows, fh, ensure_ascii=False, indent=1)
    print("written: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
