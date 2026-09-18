"""Shared helpers for the Phase-12 portfolio acceptance tests.

Imports the CHECKS machinery from tests/runtime (house convention) and adds
a UTF-8-safe subprocess runner for the demos."""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for p in (REPO, os.path.join(REPO, "tests", "runtime")):
    if p not in sys.path:
        sys.path.insert(0, p)

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "_runtime_common", os.path.join(REPO, "tests", "runtime", "_common.py"))
_mod = _ilu.module_from_spec(_spec)
sys.modules.setdefault("_runtime_common", _mod)
_spec.loader.exec_module(_mod)
Checks = _mod.Checks
run_sections = _mod.run_sections


def run_cmd(args, timeout=900):
    """Run `python <args>` in the repo with UTF-8 stdio; returns
    (rc, stdout, stderr) all str."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable] + args, capture_output=True,
                       cwd=REPO, timeout=timeout, env=env)
    return (r.returncode, r.stdout.decode("utf-8", errors="replace"),
            r.stderr.decode("utf-8", errors="replace"))
