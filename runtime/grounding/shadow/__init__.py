"""28.K.28-II-SHADOW — Claim→Evidence Support shadow layer (K.28-II
design §4-7, owner baseline OD-1..OD-8).

SHADOW ONLY — zero production authority. Nothing in runtime/grounding/
production (gate.py / loop.py / context.py) imports this package; the
package is exercised exclusively by tools/claim_shadow_eval.py and
tests. It never mutates the event bus, artifacts, or any runtime state.

Deterministic surface layer ("A-layer" per design §7-D): claim typing
(OD-1 six classes), sentence-first atomicity with deterministic clause
split (OD-2), and support judgment (OD-3 four states) based on
number/entity anchoring, product linkage, effective-window temporal
filter (OD-6 reuse of R5 fields) and contradiction detection (OD-5:
detect + fail-closed, no invented precedence). LLM comparison lives in
llm_shadow.py and NEVER influences the deterministic result (OD-11).
"""
from runtime.grounding.shadow.claims import (  # noqa: F401
    classify_claim, split_claims)
from runtime.grounding.shadow.support import (  # noqa: F401
    judge_support, DELIVERY_POLICY_HOLD, simulate_delivery)
