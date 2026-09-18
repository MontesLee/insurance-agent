"""pytest fixtures for the portfolio suites (mirrors tests/runtime)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402
from _portfolio_common import Checks  # noqa: E402


@pytest.fixture
def c():
    checks = Checks()
    yield checks
    checks.assert_all()
