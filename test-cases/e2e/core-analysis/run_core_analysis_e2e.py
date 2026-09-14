#!/usr/bin/env python3
"""Step 1 — Core Analysis E2E（不使用 Orchestrator，见规格 §13）。

串联：
    ClientState/ClientProfile + RequirementAnalysis + RiskAssessment
        -> coverage-gap-analysis（真实引擎）
        -> solution（真实引擎）

覆盖规格：
  §11 三个案例（完整客户 / 信息不足 / 信息冲突）
  §12 关键 eval 项（requirement 依据、UNKNOWN 保持、幻觉金额、产品泄漏）
  §14 Artifact 可追溯性  Solution -> Gap -> Risk -> Requirement -> ClientState
"""
from __future__ import annotations
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

COVERAGE_INVOKE = REPO_ROOT / ".trae" / "skills" / "coverage-gap-analysis" / "scripts" / "invoke-coverage-gap-analysis.py"
SOLUTION_INVOKE = REPO_ROOT / ".trae" / "skills" / "solution" / "scripts" / "invoke-solution.py"
SOLUTION_RULES = REPO_ROOT / ".trae" / "skills" / "solution" / "resources" / "config" / "solution-mapping.rules.json"

# 缺口层禁止出现任何金额类字段（规格 §6：不允许编造金额）
AMOUNT_KEYS = {
    "gap_amount", "required_coverage", "protected_amount", "unprotected_amount",
    "coverage_amount", "amount", "target_amount",
}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def walk(obj, path=""):
    """产出 (path, key_or_value) 遍历，用于键名/文本扫描。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield (path, obj)


def key_names(obj):
    keys = set()

    def _rec(o):
        if isinstance(o, dict):
            for k, v in o.items():
                keys.add(k)
                _rec(v)
        elif isinstance(o, list):
            for v in o:
                _rec(v)
    _rec(obj)
    return keys


def all_text(obj) -> str:
    buf = []
    for _p, v in walk(obj):
        if isinstance(v, str):
            buf.append(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            buf.append(str(v))
    return "\n".join(buf)


def run_case(case: dict, cover, sol, forbidden_terms: list):
    checks = []

    def chk(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    inp = json.load(open(HERE / case["file"], encoding="utf-8"))
    case_id = case["id"]

    # ---------- Stage 1: Coverage Gap ----------
    gap_art, ok, errs = cover.run(inp)
    chk(f"[{case_id}] gap 输出通过 Canonical 契约校验", ok, "; ".join(errs[:3]))

    g_payload = gap_art.get("payload", {})
    gaps = g_payload.get("gaps", [])
    gap_status = g_payload.get("status")
    chk(f"[{case_id}] gap.payload.status ∈ {case['expect_gap_status']}",
        gap_status in case["expect_gap_status"], f"actual={gap_status}")
    chk(f"[{case_id}] gap 数量 >= {case['expect_min_gaps']}",
        len(gaps) >= case["expect_min_gaps"], f"actual={len(gaps)}")

    # ---------- Stage 2: Solution ----------
    sol_in = {
        "coverage_gap_analysis": gap_art,
        "requirement_analysis": inp.get("requirement_analysis"),
        "risk_assessment": inp.get("risk_assessment"),
        "client_profile": inp.get("client_profile"),
    }
    sol_art, ok2, errs2 = sol.run(sol_in)
    chk(f"[{case_id}] solution 输出通过 Canonical 契约校验", ok2, "; ".join(errs2[:3]))

    s_payload = sol_art.get("payload", {})
    solutions = s_payload.get("solutions", [])
    sol_status = s_payload.get("status")
    chk(f"[{case_id}] solution.payload.status ∈ {case['expect_solution_status']}",
        sol_status in case["expect_solution_status"], f"actual={sol_status}")
    chk(f"[{case_id}] solution 数量 >= {case['expect_min_solutions']}",
        len(solutions) >= case["expect_min_solutions"], f"actual={len(solutions)}")

    # ---------- UNKNOWN 语义 ----------
    unk = [g for g in gaps if g.get("current_coverage", {}).get("status") == "UNKNOWN"]
    if case.get("expect_unknown_gap"):
        chk(f"[{case_id}] 存在 UNKNOWN 覆盖缺口（未猜测已有保障）", len(unk) > 0,
            f"unknown_gaps={len(unk)}")
    if case.get("expect_no_unknown_gap"):
        chk(f"[{case_id}] 不存在 UNKNOWN 覆盖缺口", len(unk) == 0,
            f"unknown_gaps={len(unk)}")

    # ---------- §14 可追溯性 ----------
    gap_ids = {g.get("gap_id") for g in gaps}
    risk_ids = {r.get("risk_id") for r in inp.get("risk_assessment", {}).get("risks", [])}
    req_ids = {r.get("requirement_id") for r in inp.get("requirement_analysis", {}).get("requirements", [])}
    has_client = isinstance(inp.get("client_profile"), dict) and len(inp["client_profile"]) > 0

    if case.get("expect_traceability"):
        # 注意：必须要求「非空 且 属于已知集合」，否则空列表会让 all() 平凡通过（假通过）
        chk(f"[{case_id}] 每个 gap 都有非空 risk 引用且均存在",
            all(g.get("related_risk_ids") and all(rid in risk_ids for rid in g["related_risk_ids"])
                for g in gaps),
            "" if gaps else "no gaps")
        chk(f"[{case_id}] 每个 gap 都有非空 requirement 依据且均存在（§12-2）",
            all(g.get("related_requirement_ids") and all(rid in req_ids for rid in g["related_requirement_ids"])
                for g in gaps),
            "")
        chk(f"[{case_id}] 每个 solution 都有非空 gap 引用且均存在（§12-1）",
            all(s.get("related_gap_ids") and all(gid in gap_ids for gid in s["related_gap_ids"])
                for s in solutions),
            "")
        chk(f"[{case_id}] 链路回溯到 ClientState", has_client, "")

    # ---------- §12-5 幻觉金额 ----------
    gap_keys = key_names(gap_art)
    amount_leak = sorted(gap_keys & AMOUNT_KEYS)
    chk(f"[{case_id}] gap 输出不含任何金额类字段（§6 禁止编造金额）",
        len(amount_leak) == 0, f"发现={amount_leak}")

    # ---------- 冲突不择一 ----------
    for num in case.get("forbid_numbers", []):
        txt = all_text(gap_art) + "\n" + all_text(sol_art)
        chk(f"[{case_id}] 输出未自行选定冲突数字 {num}（§11 Case 003）",
            str(num) not in txt, "")

    # ---------- 产品/保险公司泄漏 ----------
    sol_txt = all_text(sol_art)
    hits = [t for t in forbidden_terms if t and t in sol_txt]
    chk(f"[{case_id}] solution 输出不含产品名/保险公司名（§12-5/6）",
        len(hits) == 0, f"命中={hits}")

    return checks, {"gap_status": gap_status, "sol_status": sol_status,
                    "gaps": len(gaps), "solutions": len(solutions)}


def main():
    manifest = json.load(open(HERE / "manifest.json", encoding="utf-8"))
    rules = json.load(open(SOLUTION_RULES, encoding="utf-8"))
    forbidden_terms = rules.get("forbidden_terms", [])

    cover = load_module(COVERAGE_INVOKE, "_coverage_gap_invoke")
    sol = load_module(SOLUTION_INVOKE, "_solution_invoke")

    all_checks = []
    summaries = {}
    for case in manifest["cases"]:
        try:
            checks, summary = run_case(case, cover, sol, forbidden_terms)
            all_checks += checks
            summaries[case["id"]] = summary
        except Exception as e:  # noqa: BLE001
            all_checks.append((f"[{case['id']}] 运行未抛异常", False, repr(e)))
            summaries[case["id"]] = {"error": repr(e)}

    for name, ok, detail in all_checks:
        mark = "PASS" if ok else "FAIL"
        line = f"[{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    print("\n--- 实际状态汇总 ---")
    for cid, s in summaries.items():
        print(f"{cid}: {s}")

    passed = sum(1 for _n, ok, _d in all_checks if ok)
    total = len(all_checks)
    print(f"\nCORE ANALYSIS E2E: {passed}/{total} passed")
    if passed == total:
        print("RESULT: ALL GREEN")
        sys.exit(0)
    print("RESULT: FAILED")
    sys.exit(1)


if __name__ == "__main__":
    main()
