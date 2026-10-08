"""Intent shadow report — corpus runner + live calibration (28.A-1 + 28.A-2).

Usage:
    python -m runtime.intent.report [--out docs/production/reports/xxx.md]
                                    [--shadow [PATH]]

Default (no --shadow): run the SHADOW pipeline (classify + route, no
dispatch) over the fixed labeled corpus and write the mandated statistics
(requests / intent distribution / confidence distribution / unknown ratio /
modify-without-context ratio / agreement with the legacy path).

--shadow [PATH]: read recorded shadow traffic (default
tmp/intent-shadow/shadow.jsonl — populated by the wired server) and write
a CALIBRATION report: source distribution (rule/llm/hybrid), confidence
distribution by source, resolver outcomes, unknown / clarification ratios,
latency percentiles, and legacy-vs-shadow disagreement typing. The report
MEASURES only — thresholds live in config/intent-rules.yaml (HD-1 floor
quoted from there, provisional pending live-data calibration).
"""
from __future__ import annotations

import argparse
import os
from collections import Counter

from runtime.agent_registry import load_registry
from runtime.intent.classifier import classify, load_rules
from runtime.intent.shadow import LEGACY_TO_INTENT  # noqa: F401 (re-export)
from runtime.router import route

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

CORPUS = [
    # (message, expected_v1_intent, expected_legacy_enum)
    ("夫妻35岁，一个孩子，帮我规划保险", "insurance_plan", "CLIENT_ADVISORY"),
    ("我35岁，有两个孩子，想看看家庭保险怎么配置", "insurance_plan", "CLIENT_ADVISORY"),
    ("家里有房贷200万，年收入50万，怎么做保障方案", "insurance_plan", "CLIENT_ADVISORY"),
    ("帮我给孩子买保险，预算一万以内", "insurance_plan", "CLIENT_ADVISORY"),
    ("一家三口想配置保险", "insurance_plan", "CLIENT_ADVISORY"),
    ("百万医疗险是什么", "insurance_qa", "GENERAL_KNOWLEDGE"),
    ("重疾险和百万医疗险有什么区别", "insurance_qa", "GENERAL_KNOWLEDGE"),
    ("等待期是什么意思", "insurance_qa", "GENERAL_KNOWLEDGE"),
    ("医保和百万医疗险是什么关系", "insurance_qa", "GENERAL_KNOWLEDGE"),
    ("健康告知是什么", "insurance_qa", "GENERAL_KNOWLEDGE"),
    ("给孩子买重疾险前应该先考虑什么", "insurance_qa", "GENERAL_GUIDANCE"),
    ("健康满分怎么样", "product_qa", "PRODUCT_LOOKUP"),
    ("这款产品的等待期多久", "product_qa", "PRODUCT_LOOKUP"),
    ("P001是什么产品", "product_qa", "PRODUCT_LOOKUP"),
    ("那个产品多少钱", "product_qa", "PRODUCT_LOOKUP"),
    ("这个产品值得买吗", "product_qa", "PRODUCT_LOOKUP"),
    ("把刚才孩子的重疾险保额从50万改成30万", "modify_existing_plan", "TASK_EXECUTION"),
    ("把保额调整到30万", "modify_existing_plan", "TASK_EXECUTION"),
    ("方案里的医疗险换成另一款", "modify_existing_plan", "TASK_EXECUTION"),
    ("今天天气怎么样，适合出去玩吗", "unknown_insurance_intent", None),
    ("帮我写一首诗", "unknown_insurance_intent", None),
    ("你好", "unknown_insurance_intent", None),
]


def run_corpus(out_jsonl: str) -> list:
    """Run the shadow pipeline over the corpus; persist records; return them."""
    from runtime.intent import shadow as shadow_mod
    registry = load_registry()
    records = []
    with open(out_jsonl, "w", encoding="utf-8") as fh:
        for i, (msg, _expected, _legacy) in enumerate(CORPUS):
            ir = classify(msg, conversation_context=None,
                          conversation_id="corpus", active_case_id=None)
            rd = route(ir, registry)
            rec = shadow_mod.record(run_id="corpus_%03d" % i, chat_id=None,
                                    text=msg, intent_result=ir, route=rd,
                                    actual_execution="existing-agent",
                                    file=out_jsonl)
            rec["_expected"] = _expected
            records.append(rec)
    return records


def build_report(records: list, title: str = "Intent Shadow Report") -> str:
    total = len(records)
    dist = Counter(r["predicted_intent"] for r in records)
    src = Counter(r["confidence_source"] for r in records)
    unknown = dist.get("unknown_insurance_intent", 0)
    modify = [r for r in records if r["predicted_intent"] == "modify_existing_plan"]
    modify_no_ctx = [r for r in modify if r["clarification_required"]]

    confs = sorted((r["confidence"] for r in records), reverse=True)
    buckets = {"1.0 (rule)": 0, "0.8-1.0": 0, "0.6-0.8": 0, "<0.6": 0}
    for c in confs:
        if c >= 1.0:
            buckets["1.0 (rule)"] += 1
        elif c >= 0.8:
            buckets["0.8-1.0"] += 1
        elif c >= 0.6:
            buckets["0.6-0.8"] += 1
        else:
            buckets["<0.6"] += 1

    labeled = [r for r in records if r.get("_expected") is not None]
    correct = sum(1 for r in labeled if r["predicted_intent"] == r["_expected"])
    # agreement vs legacy mapping (corpus labels)
    agree = 0
    agree_n = 0
    for i, r in enumerate(records):
        legacy = CORPUS[i][2]
        if legacy is None:
            continue
        agree_n += 1
        if r["predicted_intent"] == LEGACY_TO_INTENT[legacy]:
            agree += 1

    lines = ["# %s" % title, ""]
    lines.append("Generated: %s · Phase 28.A-1 · SHADOW mode (no dispatch; "
                 "actual execution unchanged)" % _now_iso())
    lines.append("")
    lines.append("## 请求数量")
    lines.append("")
    lines.append("- corpus requests: **%d** (labeled corpus; live traffic "
                 "accumulates in tmp/intent-shadow/shadow.jsonl once the "
                 "server restarts with the module wired)" % total)
    lines.append("")
    lines.append("## Intent 分布")
    lines.append("")
    lines.append("| intent | count | ratio |")
    lines.append("|---|---|---|")
    for intent in ("insurance_qa", "product_qa", "insurance_plan",
                   "modify_existing_plan", "unknown_insurance_intent"):
        n = dist.get(intent, 0)
        lines.append("| %s | %d | %.0f%% |" % (intent, n, 100.0 * n / total))
    lines.append("")
    lines.append("## Confidence 分布")
    lines.append("")
    lines.append("| bucket | count | source |")
    lines.append("|---|---|---|")
    for b, n in buckets.items():
        lines.append("| %s | %d | %s |" % (b, n, dict(src)))
    lines.append("")
    lines.append("## 关键比例")
    lines.append("")
    lines.append("- unknown 比例: **%d/%d (%.0f%%)**" % (unknown, total, 100.0 * unknown / total))
    lines.append("- modify 缺 active-case context 比例: **%d/%d** (all forced "
                 "clarification_required=true per ADR-019 M1 — expected until "
                 "ADR-024 persistence lands)" % (len(modify_no_ctx), len(modify)))
    lines.append("- corpus 正确率 (predicted vs expected v1 label): **%d/%d**" % (correct, len(labeled)))
    lines.append("- 与现有执行路径一致率 (legacy-mapped labels): **%d/%d (%.0f%%)**" % (agree, agree_n, 100.0 * agree / max(1, agree_n)))
    lines.append("")
    lines.append("## Known limitations")
    lines.append("")
    lines.append("- Corpus-based shadow run (deterministic, offline). Live "
                 "traffic agreement (shadow record legacy_intent, filled by "
                 "runtime/intent/shadow.annotate after each real agent turn) "
                 "starts accumulating after the next server restart.")
    lines.append("- LLM candidate path not exercised (rules-only fast path; "
                 "provider wiring deferred — see phase-28a1-report.md).")
    lines.append("- Conversation context is passed through but not yet used "
                 "as classification signal (message-only rules in v1).")
    lines.append("")
    return "\n".join(lines)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _pct(values: list, p: float):
    """Simple percentile (nearest-rank) over a sorted-able list; None if empty."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


def load_shadow_records(path: str) -> list:
    from runtime.intent import shadow as shadow_mod
    return [r for r in shadow_mod.iter_records(path)]


def build_calibration_report(records: list,
                             title: str = "Intent Calibration Report") -> str:
    """Live-shadow calibration statistics (Phase 28.A-2 spec Step 2.3).

    Measurement only — no thresholds are decided here; the HD-1 floor is
    quoted from config/intent-rules.yaml and marked provisional until
    calibrated on live traffic.
    """
    total = len(records)
    lines = ["# %s" % title, ""]
    lines.append("Generated: %s · Phase 28.A-2 · SHADOW traffic (no "
                 "dispatch; actual execution unchanged)" % _now_iso())
    lines.append("")
    if not total:
        lines.append("_No shadow records found — live calibration starts "
                     "after a server restart with the shadow block wired._")
        return "\n".join(lines)

    src = Counter(r.get("confidence_source") for r in records)
    res = Counter(r.get("resolver") or "(pre-28.A-2)" for r in records)
    unknown = sum(1 for r in records
                  if r.get("predicted_intent") == "unknown_insurance_intent")
    clarify = sum(1 for r in records if r.get("clarification_required"))
    annotated = [r for r in records if r.get("mismatch_type") is not None]
    comparable = [r for r in records if r.get("legacy_intent")]
    agree = sum(1 for r in comparable if not r.get("mismatch_type"))

    # confidence x source cross-tab (schema enum: rule|llm|hybrid)
    buckets = ["1.0", ">=0.8", ">=0.6", "<0.6"]

    def bucket(c):
        if c is None:
            return None
        if c >= 1.0:
            return "1.0"
        if c >= 0.8:
            return ">=0.8"
        if c >= 0.6:
            return ">=0.6"
        return "<0.6"

    cross = {s: {b: 0 for b in buckets} for s in ("rule", "llm", "hybrid")}
    for r in records:
        b = bucket(r.get("confidence"))
        s = r.get("confidence_source")
        if b and s in cross:
            cross[s][b] += 1

    lat = [r["latency_ms"] for r in records
           if isinstance(r.get("latency_ms"), (int, float))]

    try:
        floor = float(load_rules().get("thresholds", {})
                      .get("high_risk_llm_min_confidence", 0.75))
        floor_note = ("externalized floor (config/intent-rules.yaml): "
                      "**%.2f** — provisional (HD-1) until calibrated on "
                      "live traffic" % floor)
    except Exception:  # noqa: BLE001
        floor_note = "floor: rules file unreadable (reported as-is)"

    mm = Counter()
    for r in annotated:
        for t in (r.get("mismatch_type") or []):
            mm[t] += 1

    lines.append("## 请求数量")
    lines.append("")
    lines.append("- shadow records: **%d** (annotated: %d; legacy-comparable: %d)"
                 % (total, len(annotated), len(comparable)))
    lines.append("")
    lines.append("## Confidence 分布（按 source）")
    lines.append("")
    lines.append("| source | %s | total |" % " | ".join(buckets))
    lines.append("|---|" + "---|" * (len(buckets) + 1))
    for s in ("rule", "llm", "hybrid"):
        n = sum(cross[s].values())
        lines.append("| %s | %s | %d |" % (
            s, " | ".join(str(cross[s][b]) for b in buckets), n))
    lines.append("")
    lines.append("## Resolver 结果分布")
    lines.append("")
    for k, n in res.most_common():
        lines.append("- %s: **%d**" % (k, n))
    lines.append("")
    lines.append("## 关键比例")
    lines.append("")
    lines.append("- unknown 比例: **%d/%d (%.0f%%)**"
                 % (unknown, total, 100.0 * unknown / total))
    lines.append("- clarification 比例: **%d/%d (%.0f%%)**"
                 % (clarify, total, 100.0 * clarify / total))
    lines.append("- 新旧一致率 (legacy-comparable): **%d/%d (%.0f%%)**"
                 % (agree, len(comparable),
                    100.0 * agree / max(1, len(comparable))))
    lines.append("")
    lines.append("## Latency（classify+route，毫秒）")
    lines.append("")
    if lat:
        lines.append("- 样本 %d · p50 **%s** · p95 **%s** · max **%s**"
                     % (len(lat), _pct(lat, 50), _pct(lat, 95), max(lat)))
    else:
        lines.append("- 无 latency 记录（28.A-2 前的旧记录无此字段）")
    lines.append("")
    lines.append("## Disagreement 类型（annotated 记录）")
    lines.append("")
    if annotated:
        for t in ("intent_difference", "confidence_difference",
                  "missing_context"):
            lines.append("- %s: **%d**" % (t, mm.get(t, 0)))
    else:
        lines.append("- 尚无 annotated 记录（annotate 覆盖率待 live 流量）")
    lines.append("")
    lines.append("## 阈值口径")
    lines.append("")
    lines.append("- %s；本报告只测量分布，不在此定阈值。" % floor_note)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--shadow", nargs="?", const=os.path.join(
        REPO_ROOT, "tmp", "intent-shadow", "shadow.jsonl"), default=None,
        help="read recorded shadow traffic instead of running the corpus")
    args = parser.parse_args()
    if args.shadow:
        out = args.out or os.path.join(
            REPO_ROOT, "docs", "production", "reports",
            "intent-calibration-report.md")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        records = load_shadow_records(args.shadow)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(build_calibration_report(records))
        print("wrote %s (%d shadow records from %s)"
              % (out, len(records), args.shadow))
        return 0
    out = args.out or os.path.join(
        REPO_ROOT, "docs", "production", "reports", "intent-shadow-report.md")
    out_jsonl = os.path.join(REPO_ROOT, "tmp", "intent-shadow",
                             "corpus-latest.jsonl")
    os.makedirs(os.path.dirname(out_jsonl), exist_ok=True)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    records = run_corpus(out_jsonl)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build_report(records))
    print("wrote %s (%d records; corpus jsonl: %s)"
          % (out, len(records), out_jsonl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
