"""Evidence closure gate (Phase 28.C-1 / ADR-022 — deterministic CODE).

Runs BEFORE delivery, on the generated answer text. The LLM never
self-audits; this module is the sole judge of citation closure.

Rules (config/qa-grounding-rules.yaml, externalized):
  1. every citation label used in the answer must exist in the turn's
     evidence_map (cited ⊆ evidence — a hallucinated [E9] is a violation);
  2. every sentence ASSERTING an insurance fact (fact-marker vocabulary)
     must carry at least one in-evidence citation within that sentence;
  3. the answer must be non-empty.

On failure the caller may regenerate ONCE (gate.max_regenerations) with
the violations as feedback; a second failure refuses the turn
(citation_gate_rejected) — an honest failure beats an ungrounded answer.
"""
from __future__ import annotations

import os
import re
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
RULES_PATH = os.path.join(REPO_ROOT, "config", "qa-grounding-rules.yaml")

_rules_cache = None


def load_rules(path: Optional[str] = None, refresh: bool = False) -> dict:
    global _rules_cache
    if _rules_cache is not None and not refresh and path is None:
        return _rules_cache
    import yaml  # noqa: WPS433 — lazy, same style as classifier.py
    with open(path or RULES_PATH, encoding="utf-8") as fh:
        rules = yaml.safe_load(fh)
    _validate_rules(rules, path or RULES_PATH)
    if path is None:
        _rules_cache = rules
    return rules


def _validate_rules(rules: dict, src: str) -> None:
    if not isinstance(rules, dict) or rules.get("version") != 1:
        raise ValueError("%s: version must be 1" % src)
    gate = rules.get("gate") or {}
    if not isinstance(gate.get("fact_markers"), list) or not gate["fact_markers"]:
        raise ValueError("%s: gate.fact_markers missing" % src)
    if not isinstance(gate.get("sentence_separators"), list):
        raise ValueError("%s: gate.sentence_separators missing" % src)
    if not isinstance((rules.get("citation") or {}).get("pattern"), str):
        raise ValueError("%s: citation.pattern missing" % src)


def _sentence_pattern(rules: dict) -> str:
    seps = rules["gate"]["sentence_separators"]
    return "[" + "".join(re.escape(s) for s in seps) + "]+"


def split_sentences(text: str, rules: Optional[dict] = None) -> list:
    """Deterministic sentence split over the externalized separators."""
    r = rules or load_rules()
    parts = re.split(_sentence_pattern(r), text or "")
    return [p.strip() for p in parts if p.strip()]


def extract_citations(text: str, rules: Optional[dict] = None) -> list:
    """All citation labels in the text, in order of appearance
    (e.g. 'E1'). Uses the externalized citation pattern."""
    r = rules or load_rules()
    fmt = r["citation"]["label_format"]
    return [fmt % int(m) for m in re.findall(r["citation"]["pattern"],
                                             text or "")]


def is_fact_sentence(sentence: str, rules: Optional[dict] = None) -> bool:
    """Deterministic fact-assertion detection: any fact marker present."""
    r = rules or load_rules()
    return any(m in sentence for m in r["gate"]["fact_markers"])


def check(answer: str, evidence_map: dict,
          rules: Optional[dict] = None) -> dict:
    """Judge citation closure. Returns
    {"ok": bool, "violations": [str], "cited": [label, ...]}.

    violations vocabulary (machine-readable, bounded to 10):
      answer:empty                     no usable text
      answer:too_long                  exceeds gate.max_answer_chars
      citation:not_in_evidence:<lbl>   label absent from evidence_map
      fact_sentence:no_citation:<idx>  fact-asserting sentence w/o citation
    """
    r = rules or load_rules()
    pat = r["citation"]["pattern"]
    violations: list = []
    text = answer or ""

    if not text.strip():
        return {"ok": False, "violations": ["answer:empty"], "cited": []}
    max_chars = int(r["gate"].get("max_answer_chars", 4000))
    if len(text) > max_chars:
        violations.append("answer:too_long:%d" % len(text))

    used = extract_citations(text, r)
    for lbl in dict.fromkeys(used):                     # first-seen order
        if lbl not in evidence_map:
            violations.append("citation:not_in_evidence:%s" % lbl)

    for i, seg in enumerate(split_sentences(text, r)):
        if is_fact_sentence(seg, r) and not re.findall(pat, seg):
            violations.append("fact_sentence:no_citation:%d" % i)

    return {"ok": not violations,
            "violations": violations[:10],
            "cited": sorted(set(used), key=lambda x: int(x[1:]))}
