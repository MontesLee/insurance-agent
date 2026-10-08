"""B4 gate report (Phase 28.B4) — never hide a mismatch.

Writes docs/production/reports/router-equivalence-report.md (spec
Phase 4): case count, pass/fail, and every mismatch under the five
fixed categories (execution/artifact/grounding/evidence/safety
difference). CLI:

    python -m runtime.evaluation.router_equivalence.report \
        [--out docs/production/reports/router-equivalence-report.md]
"""
from __future__ import annotations

import argparse
import os

CATEGORIES = ("execution_difference", "artifact_difference",
              "grounding_difference", "evidence_difference",
              "safety_difference")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


def build_report_text(report) -> str:
    total = len(report.results)
    lines = ["# Router Equivalence Report — B4 Gate (Phase 28.B4)", ""]
    lines.append("Generated: %s · SHADOW-ONLY (no authority switched; "
                 "legacy vs candidate flag runs of the REAL server)"
                 % report.generated_at)
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("- cases: **%d** · PASS **%d** · RED **%d**"
                 % (total, report.passed, report.red))
    cat_counts = {}
    for r in report.results:
        for c in r.categories:
            cat_counts[c] = cat_counts.get(c, 0) + 1
    if cat_counts:
        lines.append("- mismatch categories: " + ", ".join(
            "**%s: %d**" % (c, cat_counts[c])
            for c in CATEGORIES if c in cat_counts))
    else:
        lines.append("- mismatch categories: none")
    lines.append("")

    lines.append("## Per-case results")
    lines.append("")
    lines.append("| case | verdict | categories | notes |")
    lines.append("|---|---|---|---|")
    for r in report.results:
        notes = "; ".join(r.notes) if r.notes else ""
        lines.append("| %s | **%s** | %s | %s |" % (
            r.case_id, r.verdict,
            ", ".join(r.categories) if r.categories else "—",
            notes.replace("|", "/")))
    lines.append("")

    reds = [r for r in report.results if r.verdict == "RED"]
    if reds:
        lines.append("## Mismatches (never hidden)")
        lines.append("")
        for r in reds:
            lines.append("### %s — RED" % r.case_id)
            for cat, detail in r.mismatches:
                lines.append("- `%s`: %s" % (cat, detail))
            lines.append("")
    else:
        lines.append("## Mismatches")
        lines.append("")
        lines.append("None. Every case passed its equivalence class "
                     "checks (E1 normalized byte-equivalence / E2 "
                     "contract invariants).")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(
        REPO_ROOT, "docs", "production", "reports",
        "router-equivalence-report.md"))
    args = parser.parse_args()
    from runtime.evaluation.router_equivalence.runner import run_gate
    report = run_gate()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(build_report_text(report))
    print("wrote %s (%d cases, %d RED)" % (args.out, len(report.results),
                                           report.red))
    return 1 if report.red else 0


if __name__ == "__main__":
    raise SystemExit(main())
