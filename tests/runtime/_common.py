"""Shared helpers for the Web UI Phase 1 runtime tests (tests/runtime/).

Builds a fully isolated FastAPI test stack (own bus, own run root under tmp/) so the
tests never touch the default in-process bus or another suite's artifacts.

Dual-mode note: every suite here runs BOTH as a plain script (repo convention:
`python tests/runtime/test_*.py`, exit 0 = green, printed verdict for
tmp/run_regression.py) and under pytest (`pytest tests/runtime -q`), via the
`c` fixture defined in conftest.py / supplied by each suite's main().
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))  # tests/runtime -> repo root
for p in (REPO,):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient  # noqa: E402

from runtime.event_bus import EventBus  # noqa: E402
from runtime.server import RunManager, create_app  # noqa: E402

RUN_ROOT = os.path.join(REPO, "tmp", "webui-tests")


class Checks:
    """Check accumulator shared by script mode and pytest mode.

    pytest:  each test function receives a fresh instance (conftest fixture `c`)
             and ends with assert_all(), so failures fail the pytest test.
    script:  main() passes its own instance section-by-section, aggregates the
             [PASS]/[FAIL] lines and prints the suite verdict.
    """

    def __init__(self):
        self.lines = []
        self.failures = []

    def chk(self, name, ok, detail="") -> bool:
        ok = bool(ok)
        self.lines.append("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                                         ("  -- " + str(detail)) if (detail and not ok) else ""))
        if not ok:
            self.failures.append("%s%s" % (name, ("  -- " + str(detail)) if detail else ""))
        return ok

    def assert_all(self):
        if self.failures:
            raise AssertionError("%d failed check(s):\n%s"
                                 % (len(self.failures), "\n".join(self.failures)))

    @property
    def passed(self) -> int:
        return len(self.lines) - len(self.failures)

    @property
    def failed(self) -> int:
        return len(self.failures)


def make_client(run_root: str = None):
    """(client, manager, bus) — isolated per call, so parallel cases never collide."""
    bus = EventBus()
    root = run_root or os.path.join(RUN_ROOT, "rt-%s" % uuid.uuid4().hex[:6])
    mgr = RunManager(bus=bus, run_root=root)
    app = create_app(mgr)
    return TestClient(app), mgr, bus


def wait_terminal(client: TestClient, run_id: str, timeout: float = 120.0) -> dict:
    """Poll GET /api/runs until the run leaves queued/running. Returns the final Run."""
    deadline = time.time() + timeout
    run = None
    while time.time() < deadline:
        run = client.get("/api/runs/%s" % run_id).json()
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(0.1)
    return run


def parse_sse(lines) -> list:
    """Parse `data:` payloads out of raw SSE lines."""
    return [json.loads(l[len("data: "):]) for l in lines if l.startswith("data: ")]


def stream_events(client: TestClient, url: str, headers: dict = None) -> list:
    """GET an SSE endpoint to completion and return the parsed event dicts."""
    with client.stream("GET", url, headers=headers or {}) as r:
        if r.status_code != 200:
            raise AssertionError("stream %s -> %s" % (url, r.status_code))
        raw = [l for l in r.iter_lines()]
    return parse_sse(raw)


def run_sections(sections, log_name: str, title: str) -> int:
    """Script-mode driver: run each section with a fresh Checks, print the suite
    verdict (parsed by tmp/run_regression.py), write the log, return exit code."""
    all_lines, passed, failed = [], 0, 0
    for fn in sections:
        c = Checks()
        try:
            fn(c)
        except AssertionError as e:
            all_lines.append("-- section %s FAILED" % fn.__name__)
            all_lines.extend(str(e).splitlines())
        all_lines.extend(c.lines)
        passed += c.passed
        failed += c.failed
    all_lines += ["", "%s: %d/%d checks passed" % (title, passed, passed + failed),
                  "RESULT: %s" % ("ALL GREEN" if failed == 0 else "FAILURES PRESENT")]
    text = "\n".join(all_lines)
    print(text)
    with open(os.path.join(REPO, "tmp", log_name), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 0 if failed == 0 else 1

