#!/usr/bin/env python3
"""Run the 3 Python-based skill eval suites (no logic modified in Phase 1).

Imports each skill's dataset runner and captures its native stdout summary.
Writes tests/contracts/_py_eval_log.txt.
"""
import contextlib
import io
import os
import sys

REPO = "D:/Workspace/insurance-agent"
RUNS = [
    ("report-generation", "run_report_dataset.py"),
    ("recommendation", "run_recommendation_dataset.py"),
    ("knowledge-search", "run_knowledge_search_dataset.py"),
]

summary = []
for skill, script in RUNS:
    p = os.path.join(REPO, ".trae", "skills", skill, "scripts")
    if p not in sys.path:
        sys.path.insert(0, p)
    mod = __import__(script[:-3])
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            mod.main()
    except SystemExit as e:  # main() calls sys.exit
        code = e.code if isinstance(e.code, int) else 0
    out = buf.getvalue()
    green = ("ALL GREEN" in out) or (code == 0 and "FAIL" not in out)
    tail = out.strip().splitlines()[-6:]
    summary.append((skill, green, code, "\n".join(tail)))

lines = []
all_green = True
for skill, green, code, tail in summary:
    lines.append(f"=== {skill} (exit={code}) ===")
    lines.append("PASS" if green else "FAIL")
    lines.append(tail)
    lines.append("")
    if not green:
        all_green = False

lines.append("PY EVALS: " + ("ALL GREEN" if all_green else "FAILURES PRESENT"))
with open(os.path.join(REPO, "tests", "contracts", "_py_eval_log.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("PY EVALS:", "ALL GREEN" if all_green else "FAILURES PRESENT")
