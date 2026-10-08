"""B4 gate data model (Phase 28.B4).

GoldenCase — one comparable turn, loaded from tests/golden/
router_cases.json (validated against schema/router-golden-case.schema.json;
the JSON file is the single source, so the schema contract test and the
runner can never drift apart). Script items map onto FakeLLMProvider's
script protocol: "plain text" | {"tool","args"} | {"error": msg}.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_CASES_PATH = os.path.join(REPO_ROOT, "tests", "golden",
                                  "router_cases.json")


@dataclass
class GoldenCase:
    case_id: str
    intent: str                    # expected v1 intent
    message: str
    equivalence_class: str         # "E1" | "E2"
    equivalence_type: str          # finer label: grounded_answer /
                                   # insufficient_evidence / kb_unavailable /
                                   # llm_unavailable / hallucinated_citation /
                                   # d6_missing_fact / plan_artifact_equality /
                                   # clarification / safe_fallback ...
    expected: dict = field(default_factory=dict)
                                   # {"grounding_status"| "failure_reason" |
                                   #  "intent" | "clarification_required" | ...}
    script: list = field(default_factory=list)   # FakeLLM script items
    context: list = field(default_factory=list)  # seeded chat history
    flags: dict = field(default_factory=dict)    # candidate-side env
    service: str = "default"       # "default" | "dead"
    fixture_source: str = ""
    notes: str = ""


@dataclass
class SideCapture:
    side: str                      # "legacy" | "candidate"
    run_id: str
    status: str = ""
    events: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)    # normalized payloads
    qa_context: Optional[dict] = None
    shadow_record: Optional[dict] = None
    chat_messages: list = field(default_factory=list)
    error: str = ""


@dataclass
class CaseResult:
    case_id: str
    verdict: str                   # "PASS" | "RED"
    mismatches: list = field(default_factory=list)   # [(category, detail)]
    notes: list = field(default_factory=list)

    @property
    def categories(self) -> list:
        return sorted({c for c, _ in self.mismatches})


@dataclass
class GateReport:
    results: list = field(default_factory=list)      # list[CaseResult]
    generated_at: str = ""

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.verdict == "PASS")

    @property
    def red(self) -> int:
        return sum(1 for r in self.results if r.verdict == "RED")


def load_cases(path: Optional[str] = None) -> list:
    with open(path or DEFAULT_CASES_PATH, encoding="utf-8") as fh:
        doc = json.load(fh)
    cases = doc["cases"] if isinstance(doc, dict) else doc
    return [GoldenCase(**{**c,
                         "script": list(c.get("script") or []),
                         "context": list(c.get("context") or []),
                         "flags": dict(c.get("flags") or {}),
                         "expected": dict(c.get("expected") or {})})
            for c in cases]
