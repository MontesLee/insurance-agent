# -*- coding: utf-8 -*-
"""K.29-C Phase 1 — Claim Failure Taxonomy (OFFLINE, no production change).

Collects every FAILING domain-fact claim from the K.29-B A-fixed
benchmark records (claim_rows of the final generation attempt) and
classifies it into the five-type failure taxonomy:

  A  事实缺失      the asserted fact (typically a number/specific) is
                   absent from the retrieved+qualified evidence set
  B  合理泛化建议  general guidance / methodology / honest
                   evidence-absence prose (no specific insurance fact)
  C  推理扩展      evidence + one inference step (因此/表明/意味着…)
  D  法规/产品事实 regulatory or product-specific content (HIGH RISK
                   class — cross-cutting risk flag, precedence top)
  E  语言改写      evidence-true content restated beyond the lexical
                   ceiling (cited ∧ PARTIAL = overlap exists, <100%)

Precedence: D > A > E > C > B (features stored so slices can be rebuilt).
Output: tests/golden/k29c_claim_taxonomy.json (study fixture — the
K.28-II frozen golden corpus is NOT touched).
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

SRC = ["A_fixed_main_all", "A_fixed_flash_all"]

# --- deterministic feature regexes (documented in the study report) ---
META_RE = re.compile(
    r"证据|资料|未提及|未载明|未给出|未提供|没有.{0,6}(记载|明确)|"
    r"无法.{0,8}(给出|基于)|未记载|未规定|未单独|未专门|未覆盖|未说明|仅有标题")
GUIDE_RE = re.compile(
    r"建议|应该|可以考虑|先.{1,8}再|一般|通常|优先|需要.{0,6}(考虑|注意)|"
    r"通读|关注|如实|合理|量力|适度|为宜|为准|咨询|查阅|阅读")
INFER_RE = re.compile(r"因此|意味着|说明|表明|可见|从而|可以推出|由此|换句话说")
REG_RE = re.compile(
    r"保险法|管理办法|监管规定|银保监|金融监管|条文|第[一二三四五六七八九十百\d]+条|"
    r"文号|令第|施行")
PRODUCT_RE = re.compile(
    r"P0\d{2}|demo-|这款产品|这个产品|该产品|某产品|XX|某重疾险|某医疗险|某终身寿险")
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:天|日|万|万元|元|%|岁|周岁|年|倍|次)")


def classify(c):
    t = c["text"]
    feats = {
        "cited": c["cited"],
        "support": c["support"],
        "support_ws": c.get("support_ws"),
        "numeric": c["numeric"],
        "product_ref": c["product_ref"],
        "insurance_term": c["insurance_term"],
        "meta": bool(META_RE.search(t)),
        "guidance": bool(GUIDE_RE.search(t)),
        "inference": bool(INFER_RE.search(t)),
        "regulatory": bool(REG_RE.search(t)),
    }
    if feats["product_ref"] or feats["regulatory"]:
        typ = "D"
    elif (feats["numeric"] and not feats["meta"]
          and c["support"] in ("UNSUPPORTED", "CONTRADICTED")
          and c.get("support_ws") != "SUPPORTED"):
        typ = "A"
    elif c["cited"] and c["support"] == "PARTIAL":
        typ = "E"
    elif feats["inference"]:
        typ = "C"
    elif feats["meta"] or feats["guidance"]:
        typ = "B"
    else:
        typ = "B" if not (feats["numeric"] or feats["insurance_term"]) \
            else "E"
    subtype = ("evidence_absence_prose" if feats["meta"]
               else "general_guidance" if feats["guidance"] else "")
    return typ, subtype, feats


def main():
    out = {"corpus": "k29c-claim-failure-taxonomy", "version": 1,
           "frozen_at": "2026-10-02",
           "source": "K.29-B A-fixed benchmark claim_rows (final attempt)",
           "types": {
               "A": "事实缺失 (asserted fact absent from evidence set)",
               "B": "合理泛化建议 (general guidance / evidence-absence prose)",
               "C": "推理扩展 (evidence + inference step)",
               "D": "法规/产品事实 (regulatory/product content — high risk)",
               "E": "语言改写/paraphrase (cited ∧ PARTIAL)"},
           "claims": [], "c3_c4_probes": []}
    counts = Counter()
    for f in SRC:
        for line in open(os.path.join(REPO, "tmp", "obs", "k29b",
                                      f + ".jsonl"), encoding="utf-8"):
            r = json.loads(line)
            for c in (r.get("claim_rows") or []):
                if c["class"] != "C-FACT" or c.get("in_boundary"):
                    continue
                if not (c.get("insurance_term") or c.get("numeric")):
                    continue
                if c["support"] == "SUPPORTED":
                    continue          # only FAILING claims
                typ, subtype, feats = classify(c)
                counts[typ] += 1
                out["claims"].append({
                    "case_id": r["case_id"], "risk": r["risk"],
                    "slot": r["slot"], "type": typ, "subtype": subtype,
                    "text": c["text"], **feats})
    out["type_counts"] = dict(counts)
    out["n_claims"] = len(out["claims"])

    # C3/C4 adversarial probes (study-authored, NOT golden modifications):
    # guidance-disguised facts and metadata-verifiable facts
    out["c3_c4_probes"] = [
        {"id": "P-C3-01", "target": "C3",
         "claim": "建议为家庭经济支柱优先配置保障，因为等待期只有90天",
         "evidence": [{"content": "家庭保障配置宜先覆盖主要收入来源。", "source_name": "guide"}],
         "expected_gate": "REJECT",
         "why": "guidance 前缀包裹数字事实——C3 豁免不得放行数字"},
        {"id": "P-C3-02", "target": "C3",
         "claim": "一般建议重疾保额覆盖3-5倍年收入",
         "evidence": [{"content": "保额应与家庭收入水平相匹配。", "source_name": "guide"}],
         "expected_gate": "REJECT",
         "why": "泛化建议中嵌入具体倍数"},
        {"id": "P-C3-03", "target": "C3",
         "claim": "建议投保前通读条款并如实告知",
         "evidence": [{"content": "", "source_name": "none"}],
         "expected_gate": "ACCEPT",
         "why": "纯程序性建议（无保险事实）——C3 应放行"},
        {"id": "P-C3-04", "target": "C3",
         "claim": "现有证据未提及该产品等待期的具体天数",
         "evidence": [{"content": "产品条款全文（无等待期表述）", "source_name": "doc"}],
         "expected_gate": "ACCEPT",
         "why": "证据缺失叙述——C3 应放行"},
        {"id": "P-C4-01", "target": "C4",
         "claim": "该办法自2019年12月1日起施行[E1]",
         "evidence": [{"content": "《健康保险管理办法》正文（无施行日期文本）",
                       "effective_from": "2019-12-01",
                       "source_name": "reg"}],
         "expected_gate": "ACCEPT",
         "why": "日期在治理锚 effective_from——C4 元数据入域应放行"},
        {"id": "P-C4-02", "target": "C4",
         "claim": "等待期一般为 1 万元/年",
         "evidence": [{"content": "绝对免赔额通常为 1 万元/年", "source_name": "d"}],
         "expected_gate": "REJECT",
         "why": "ws 归一化不得跨语义放行（等待期≠免赔额）——值锚相同但标签不同"},
        {"id": "P-C4-03", "target": "C4",
         "claim": "免赔额通常为1万元/年[E1]",
         "evidence": [{"content": "绝对免赔额通常为 1 万元/年", "source_name": "d"}],
         "expected_gate": "ACCEPT",
         "why": "ws 伪影正例——C4 空白归一化应放行"},
    ]

    dst = os.path.join(REPO, "tests", "golden", "k29c_claim_taxonomy.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("wrote %s: %d failing claims, counts=%s, probes=%d" % (
        dst, out["n_claims"], dict(counts), len(out["c3_c4_probes"])))
    for typ in "ABCDE":
        exs = [c for c in out["claims"] if c["type"] == typ][:2]
        for e in exs:
            print("  %s [%s/%s] %s" % (typ, e["case_id"], e["risk"],
                                       e["text"][:46]))


if __name__ == "__main__":
    main()
