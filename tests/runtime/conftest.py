"""pytest fixtures for tests/runtime/ — the `c` (Checks) accumulator.

Keeps the suites dual-mode: the same test functions run unchanged under
`pytest tests/runtime -q` and as plain scripts (each suite's main() passes its
own Checks instance).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from _common import Checks  # noqa: E402


@pytest.fixture
def c():
    """Accumulate checks during the test; assert them all when it finishes.

    The post-yield assert is what makes a failed chk() fail the pytest test —
    sections never need to call assert_all() themselves.
    """
    checks = Checks()
    yield checks
    checks.assert_all()
