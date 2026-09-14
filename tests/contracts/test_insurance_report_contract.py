"""InsuranceReport contract test: real ReportGenerationResult -> report_generation adapter -> schema.

The report engine output (from the report-generation dataset complete_client case) is wrapped
into the InsuranceReport contract. Report Generation owns no business judgment — only
collect / normalize / render / validate.
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from adapters.report_generation_adapter import to_canonical
from _common import load_fixture, validate


def run():
    data = load_fixture("report_generation.json")
    artifact = to_canonical(data)
    ok, msgs = validate(artifact, "insurance-report.schema.json")
    return ("insurance-report", ok, "valid" if ok else "; ".join(msgs))
