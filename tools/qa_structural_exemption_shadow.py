#!/usr/bin/env python3
"""28.C-5A deterministic structural-exemption SHADOW classifier.

Read-only experiment: NEVER changes the production gate. Replays a
40-case corpus and (if present) the C-4 violation corpus through a
deterministic classifier that answers ONE question per gate sentence:

    after stripping structural shells (heading/bullet/number/bold/
    label-colon per LINE — newline pre-split solves the gate's \\n
    glue), does ANY line still carry an independent factual
    proposition?

STRUCTURAL_ONLY (shadow-exempt)  <=>  every line, after stripping, is
    empty / a pure noun-phrase label / a whitelisted transition or
    meta template — i.e. NO predicate signal.
MUST_CITE otherwise. Deterministic, local, reproducible; no LLM.

Predicate signal (conservative — biased to MUST_CITE): digits, or any
predicate/modal marker (是/有/存在/没有/通常/一般/可以/保证/覆盖/
需要/属于/包括/分为/适用/为/取决于/一定/必须/应当/不得/禁止/支持/
赔付/报销/约定/指/称/意味着/不构成投资建议例外…). Any hit on any
line => factual.
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

# ---- deterministic structural shell grammar ------------------------ #
LINE_SHELL = re.compile(
    r"^\s*(?:#{1,6}\s*|[-*+]\s+|\d+[\.、)]\s*|>\s*)")
BOLD = re.compile(r"^\*\*(.+?)\*\*[:：]?\s*")
LABEL = re.compile(r"^(?:关于)?[^：:]{1,14}[：:]\s*")

TRANSITION = re.compile(
    r"^(下面|接下来|首先|然后|其次|最后|现在|以上|总之|综上|总的来说)"
    r"[^。]{0,18}。?$")
META = re.compile(
    r"(按照|根据).{0,8}(要求|提示|问题|说明)|本次.{0,12}(证据|参考|整理)"
    r"|以下内容.{0,12}(证据|参考|常识|整理)|无法.{0,8}(引用|提供)"
    r"|仅供参考|不构成.{0,6}(建议|要约)|我会|我将")

PREDICATE = re.compile(
    r"\d|是|有|存在|没有|无免|通常|一般|往往|常见的|常为|可以|可|能|保证|"
    r"覆盖|需要|需|属于|包括|分为|适用|为期|取决于|一定|必须|应当|"
    r"不得|禁止|支持|赔付|报销|约定|指的?是|意味着|起到|用作|针对|"
    r"适合|不赔付|上限|达到|超过|低于|高于|等于|区别在于|影响|要注意|"
    r"需要注意|存在与否")


def strip_line(line: str) -> str:
    """Remove ONE structural shell layer (repeatedly while it changes)."""
    s = line.strip()
    prev = None
    while prev != s:
        prev = s
        s = LINE_SHELL.sub("", s)
        m = BOLD.match(s)
        if m:
            # keep whatever FOLLOWS the bold label — the label is only
            # the shell, the rest of the line may carry the claim
            s = m.group(1) + s[m.end():]
        if LABEL.match(s) and not PREDICATE.search(LABEL.match(s).group(0)[:-1]):
            # a short non-predicating label prefix "免赔额：" — drop it
            s = LABEL.sub("", s, count=1)
        s = s.strip().strip("*").strip()
    return s


def line_verdict(line: str) -> str:
    """STRUCTURAL / FACTUAL for one raw line (shell-aware)."""
    raw = line.strip()
    if not raw:
        return "STRUCTURAL"
    stripped = strip_line(raw)
    if not stripped:
        return "STRUCTURAL"
    if TRANSITION.match(stripped) or META.search(stripped):
        return "STRUCTURAL"
    if PREDICATE.search(stripped):
        return "FACTUAL"
    # no predicate signal and no template match: a bare noun phrase
    # (a heading's content, a label) — structural ONLY if it carries no
    # digits (already covered) and stays short (long tail = unknown =>
    # conservative FACTUAL)
    return "STRUCTURAL" if len(stripped) <= 16 else "FACTUAL"


def shadow_classify(gate_sentence: str) -> str:
    """EXEMPT only when EVERY line (after \\n pre-split) is structural."""
    lines = (gate_sentence or "").split("\n")
    verdicts = [line_verdict(ln) for ln in lines]
    return "EXEMPT" if all(v == "STRUCTURAL" for v in verdicts) \
        else "MUST_CITE"


# ---- 40-case corpus (C-5 taxonomy) ---------------------------------- #
POSITIVE = [  # pure factual claims -> MUST_CITE
    "百万医疗险通常用于报销符合合同约定的医疗费用。",
    "百万医疗险通常存在合同约定的免赔额。",
    "重疾险的赔付方式是一次性给付保额。",
    "医疗险的等待期一般为30天。",
    "终身寿险的保费通常高于定期寿险。",
    "意外险主要保障意外身故和意外医疗。",
    "健康告知需要如实填写既往病史。",
    "现金价值是保单退保时可领取的金额。",
    "保证续保期间内保险公司不能拒绝续保。",
    "免赔额以下的医疗费用需要自行承担。",
]
NEGATIVE = [  # pure structure/transition/meta -> EXEMPT
    "## 一、免赔额",
    "### 医疗险与重疾险的区别",
    "# 常见问题解答",
    "**重要提示：**",
    "关于续保条件：",
    "下面我们来看两者的区别。",
    "接下来重点说明免赔额。",
    "按照你的要求，我会从三个方面分析。",
    "本次未提供受管证据，仅供参考。",
    "- 免赔额",
]
MIXED = [  # structure + claim -> MUST_CITE (red line)
    "## 免赔额：百万医疗险通常存在合同约定的免赔额。",
    "**等待期：** 某产品等待期为90天。",
    "### 续保\n百万医疗险是否保证续保取决于具体合同约定。",
    "**免赔额：** 百万医疗险通常存在合同约定的免赔额。",
    "## 免赔额\n百万医疗险通常存在免赔额。",
    "关于免赔额：\n百万医疗险通常存在免赔额。",
    "免赔额这一点需要特别注意，百万医疗险通常存在免赔额。",
    "1. 保证续保期间越长（如20年）越稳定",
    "| 免赔额 | 1万元 |",
    "## 现金价值\n保单退保时可领取的金额是现金价值。",
]
ADVERSARIAL = [  # format-disguised claims -> MUST_CITE (red line)
    "## 免赔额\n百万医疗险没有免赔额。",
    "### 重要提示\n百万医疗险一定保证续保。",
    "**结论：** 百万医疗险一定覆盖所有医疗费用。",
    "## 重要\n重疾险确诊即赔不需要任何条件。",
    "* 等待期内出险保险公司必须赔付",
    "2) 意外险覆盖所有疾病治疗费用",
    "### 免责条款\n合同中没有任何免责条款。",
    "**注意：** 如实告知不影响理赔",
    "关于保证续保：\n本产品可以永久保证续保",
    "## 提示\n现金价值等于已交保费",
]


def main() -> int:
    rows = []
    for name, cases, expect in (
            ("Positive", POSITIVE, "MUST_CITE"),
            ("Negative", NEGATIVE, "EXEMPT"),
            ("Mixed", MIXED, "MUST_CITE"),
            ("Adversarial", ADVERSARIAL, "MUST_CITE")):
        ok = 0
        for c in cases:
            got = shadow_classify(c)
            good = got == expect
            ok += good
            rows.append({"group": name, "case": c, "expect": expect,
                         "shadow": got, "pass": good})
        print("[shadow] %-11s %d/10" % (name, ok))
    fails = [r for r in rows if not r["pass"]]

    # ---- C-4 corpus replay (read-only) ---- #
    c4_path = os.path.join(REPO, "tmp", "obs", "c4_violations.json")
    replay = None
    if os.path.isfile(c4_path):
        data = json.load(open(c4_path, encoding="utf-8"))
        n = struct_only = 0
        for r in data:
            for att in r.get("per_attempt_violating_sentences", []):
                for s in att["sentences"]:
                    n += 1
                    if shadow_classify(s["text"]) == "EXEMPT":
                        struct_only += 1
        replay = {"violation_sentences": n,
                  "shadow_structural_only": struct_only,
                  "share_pct": round(100.0 * struct_only / n, 1) if n
                  else 0.0}
        print("[replay] C-4 sentences=%d shadow-structural=%d (%.1f%%)"
              % (n, struct_only, replay["share_pct"]))
    else:
        print("[replay] c4_violations.json not found")

    neg_pass = sum(1 for r in rows if r["group"] == "Negative"
                   and r["pass"])
    exempt_all = [r for r in rows if r["shadow"] == "EXEMPT"]
    prec = (sum(1 for r in exempt_all if r["expect"] == "EXEMPT")
            / len(exempt_all)) if exempt_all else None
    out = {"groups": {g: sum(1 for r in rows if r["group"] == g
                             and r["pass"]) for g in
                      ("Positive", "Negative", "Mixed", "Adversarial")},
           "exemption_recall_pct": neg_pass * 10,
           "exemption_precision_pct": round(100 * prec, 1)
           if prec is not None else None,
           "mixed_safety": "%d/10" % sum(
               1 for r in rows if r["group"] == "Mixed" and r["pass"]),
           "adversarial_safety": "%d/10" % sum(
               1 for r in rows if r["group"] == "Adversarial"
               and r["pass"]),
           "failures": fails, "c4_replay": replay}
    path = os.path.join(REPO, "tmp", "obs", "c5a_shadow.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("written: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
