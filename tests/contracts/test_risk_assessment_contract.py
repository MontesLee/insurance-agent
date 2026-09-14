"""RiskAssessment contract test: representative RiskAnalysisOutput -> adapter -> schema.

Note: risk-analysis engine is PowerShell-driven and not executed here; the risk_assessment
canonical payload is permissive, so this validates the adapter boundary with a representative
sample (see tests/contracts/fixtures/risk_assessment.json).
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from adapters.risk_analysis_adapter import to_canonical
from _common import load_fixture, validate


def run():
    data = load_fixture("risk_assessment.json")
    artifact = to_canonical(data)
    ok, msgs = validate(artifact, "risk-assessment.schema.json")
    return ("risk-assessment", ok, "valid" if ok else "; ".join(msgs))
