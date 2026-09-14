"""RequirementAnalysis contract test: real RequirementAnalysisOutput -> adapter -> schema."""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from adapters.requirement_analysis_adapter import to_canonical
from _common import load_fixture, validate


def run():
    data = load_fixture("requirement_analysis.json")
    artifact = to_canonical(data)
    ok, msgs = validate(artifact, "requirement-analysis.schema.json")
    return ("requirement-analysis", ok, "valid" if ok else "; ".join(msgs))
