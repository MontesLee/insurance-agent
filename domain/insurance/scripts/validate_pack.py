#!/usr/bin/env python3
"""Domain Pack 校验（不变量 + 门禁）。

校验 domain/insurance 作为共享领域包的完整性：
  1. pack.yaml 合法、含必填字段
  2. 每个 references/*.md 带版本化标记（version / effective_date / source_level / code）
  3. taxonomy 一致性：product_types ↔ alias_to_code ↔ rag.PRODUCT_BY_PREFIX ↔ evidence-request domains
  4. evidence_types 合法且能被 evidence-request 规则覆盖
  5. source_levels 含 S/A/B/C/D
  6. overlays 默认空（enabled=false 时不得有非 README/.gitkeep 内容）—— 防 overlay 泄漏
  7. references 可被 rag.store 摄取（每文件 ≥1 chunk，总计 >0）
  8. 检索冒烟：代表性 domain 查询返回非空结果

退出码：全过 0，任一失败 1。
"""
from __future__ import annotations
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(PACK_ROOT))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, HERE)

import yaml  # PyYAML
from knowledge.rag.store import KnowledgeStore, PRODUCT_BY_PREFIX  # noqa: E402

# 复用本包引擎装配
from build_domain_engine import build_domain_engine, ingest_pack  # noqa: E402

REFERENCES_DIR = os.path.join(PACK_ROOT, "references")
PACK_YAML = os.path.join(PACK_ROOT, "pack.yaml")
OVERLAYS_DIR = os.path.join(PACK_ROOT, "overlays")
EVIDENCE_RULES = os.path.join(
    REPO_ROOT, ".trae", "skills", "evidence", "resources", "config", "evidence-request.rules.json"
)

MARKER_RE = re.compile(r"<!--\s*domain-pack:\s*(.*?)\s*-->")
KV_RE = re.compile(r"(\w+)=(\S+)")


def parse_marker(text: str) -> dict:
    m = MARKER_RE.search(text)
    if not m:
        return {}
    return dict(KV_RE.findall(m.group(1)))


def _check(name, ok, detail=""):
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main():
    checks = []
    problems = []

    # ---- 1. pack.yaml 合法性 ----
    try:
        with open(PACK_YAML, encoding="utf-8") as f:
            pack = yaml.safe_load(f)
        checks.append(_check("pack.yaml 可解析为 YAML", True))
    except Exception as e:  # noqa: BLE001
        checks.append(_check("pack.yaml 可解析为 YAML", False, str(e)))
        print("\nRESULT: FAILED (pack.yaml 无法解析)")
        sys.exit(1)

    for key in ("pack_id", "version", "product_types", "alias_to_code",
                "evidence_types", "source_levels", "rag_seed", "overlays"):
        checks.append(_check(f"pack.yaml 含必填字段 `{key}`", key in pack,
                             "" if key in pack else "缺失"))

    # ---- 2. references 版本化标记 ----
    ref_files = sorted(f for f in os.listdir(REFERENCES_DIR) if f.endswith(".md"))
    for fn in ref_files:
        meta = parse_marker(open(os.path.join(REFERENCES_DIR, fn), encoding="utf-8").read())
        ok = bool(meta.get("version")) and bool(meta.get("effective_date")) \
            and bool(meta.get("source_level")) and bool(meta.get("code"))
        checks.append(_check(f"reference 版本化: {fn}", ok,
                             "缺 version/effective_date/source_level/code 之一" if not ok else f"v={meta.get('version')}"))

    # ---- 3. taxonomy 一致性 ----
    ptypes = {p["code"]: p for p in pack.get("product_types", [])}
    alias_to_code = pack.get("alias_to_code", {})

    # 3a. 每个 product_type 的 evidence_alias 经 alias_to_code 必须回到自身 code
    for p in pack.get("product_types", []):
        code, alias = p["code"], p.get("evidence_alias")
        if alias:
            ok = alias_to_code.get(alias) == code
            checks.append(_check(f"taxonomy: alias {alias} -> {code}", ok,
                                 "" if ok else f"alias_to_code 指向 {alias_to_code.get(alias)}"))
    # 3b. alias_to_code 的所有 value 必须已声明
    for alias, code in alias_to_code.items():
        checks.append(_check(f"taxonomy: alias_to_code[{alias}] 已声明 {code}", code in ptypes,
                             "" if code in ptypes else "code 未声明"))

    # 3c. 与 rag.PRODUCT_BY_PREFIX 对齐（rag 内部代码必须被本包声明）
    for prefix, rag_code in PRODUCT_BY_PREFIX.items():
        checks.append(_check(f"taxonomy: rag.PRODUCT_BY_PREFIX {prefix}->{rag_code} 已声明",
                             rag_code in ptypes,
                             "" if rag_code in ptypes else "本包未声明该 code"))

    # 3d. 与 evidence-request 的 domain 对齐
    if os.path.exists(EVIDENCE_RULES):
        ev = json.load(open(EVIDENCE_RULES, encoding="utf-8"))
        ev_domains = list(ev.get("domain_query_template", {}).keys())
        for d in ev_domains:
            ok = d in alias_to_code and alias_to_code[d] in ptypes
            checks.append(_check(f"taxonomy: evidence domain `{d}` 可解析为已声明 code", ok,
                                 "" if ok else "无法经 alias_to_code 映射到本包 code"))

    # ---- 4. evidence_types 合法 ----
    allowed_purposes = {"SOLUTION_VALIDATION", "PRODUCT_VALIDATION", "POLICY_FACT",
                        "MEDICAL_FACT", "REGULATORY_FACT", "COMPARISON", "OTHER"}
    for et in pack.get("evidence_types", []):
        ok = et.get("code") and et.get("purpose") in allowed_purposes
        checks.append(_check(f"evidence_type: {et.get('code')}", ok,
                             "" if ok else f"purpose={et.get('purpose')} 非法"))
    if os.path.exists(EVIDENCE_RULES):
        ev = json.load(open(EVIDENCE_RULES, encoding="utf-8"))
        ev_purpose_defaults = set(ev.get("purpose_default_evidence_type", {}).values())
        pack_ev_codes = {et["code"] for et in pack.get("evidence_types", [])}
        for code in ev_purpose_defaults:
            checks.append(_check(f"evidence_type: evidence-request 用到的 {code} 已声明",
                                 code in pack_ev_codes,
                                 "" if code in pack_ev_codes else "本包未声明"))

    # ---- 5. source_levels ----
    for lvl in ("S", "A", "B", "C", "D"):
        checks.append(_check(f"source_level 含 `{lvl}`", lvl in pack.get("source_levels", {})))

    # ---- 6. overlay 不泄漏 ----
    ov = pack.get("overlays", {})
    if not ov.get("enabled", False):
        allowed = {"README.md", ".gitkeep"}
        extras = []
        if os.path.isdir(OVERLAYS_DIR):
            for root, dirs, files in os.walk(OVERLAYS_DIR):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), OVERLAYS_DIR)
                    if rel not in allowed:
                        extras.append(rel)
                for d in dirs:
                    extras.append(d + "/")
        checks.append(_check("overlay 不泄漏（enabled=false 时无额外内容）", len(extras) == 0,
                             "" if not extras else f"发现: {extras}；需先在 pack.yaml 登记 overlay"))
    else:
        checks.append(_check("overlay 已启用且登记", len(ov.get("available", [])) > 0,
                             "" if ov.get("available") else "enabled=true 但 available 为空"))

    # ---- 7. references 可被 rag 摄取 ----
    store = KnowledgeStore()
    ingest_pack(store, REFERENCES_DIR)
    total = len(store.all_chunks())
    checks.append(_check("rag 摄取：总计 chunk > 0", total > 0, f"{total} chunks"))
    for fn in ref_files:
        meta = parse_marker(open(os.path.join(REFERENCES_DIR, fn), encoding="utf-8").read())
        # 验证该文件被摄取且 product_type 与标记 code 一致
        doc_id = os.path.splitext(fn)[0]
        rows = [c for c in store.all_chunks() if c.document_id == doc_id]
        ok = len(rows) > 0 and all(c.product_type == meta.get("code") for c in rows)
        checks.append(_check(f"rag 摄取: {fn} → product_type={meta.get('code')}", ok,
                             "" if ok else f"chunk={len(rows)} 或 product_type 不匹配"))

    # ---- 8. 检索冒烟 ----
    try:
        engine = build_domain_engine(REFERENCES_DIR)
        smoke_domains = {
            "medical": "百万医疗险 保障范围 免赔额",
            "critical_illness": "重疾险 确诊给付 保额",
            "accident": "意外险 伤残分级 意外医疗",
            "life": "定期寿险 保障期限 家庭责任",
        }
        for dom, q in smoke_domains.items():
            res = engine.search(q, top_k=3)
            ok = res.status != "retrieval_error" and len(res.results) > 0
            detail = f"status={res.status}, n={len(res.results)}"
            checks.append(_check(f"检索冒烟: [{dom}] {q}", ok, detail))
    except Exception as e:  # noqa: BLE001
        checks.append(_check("检索冒烟：引擎可构建并执行", False, str(e)))

    # ---- 汇总 ----
    passed = sum(1 for c in checks if c)
    total_n = len(checks)
    print(f"\nDOMAIN PACK VALIDATION: {passed}/{total_n} passed")
    if passed == total_n:
        print("RESULT: ALL GREEN")
        sys.exit(0)
    else:
        print("RESULT: FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
