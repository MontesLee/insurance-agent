"""Phase 25.1 — observability output-channel isolation (F-GATE-03).

Invariant: stdout is the PRODUCT/DEMO output channel only; the
observability mirror goes to stderr. Proves:

  T1 stdout purity        — no observability JSONL/ids in demo stdout
  T2 observability works  — the same records remain available on stderr
  T3 deterministic output — product stdout identical across N>=3 runs
  T5/T6 obs OFF vs ON     — identical product output (channel split)

stdout and stderr are captured SEPARATELY (subprocess pipes), so the
proof does not depend on the demo's own printing internals.

House convention: script mode (python tests/runtime/test_p25_1_output_channel.py,
exit 0 = green) and pytest (fixture `c` in conftest.py).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, run_sections  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


_OBS = re.compile(r'^\{"timestamp":')
_PRODUCT = ("INSURANCE ANALYSIS", "FINAL", "COMPLETED")


def _run_demo(mode: str = "demo"):
    """Run the real demo in `mode` with stdout/stderr captured apart."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8",
               INSURANCE_AGENT_MODE=mode)
    r = subprocess.run([sys.executable, "-m", "demos.demo_insurance"],
                       capture_output=True, cwd=REPO, env=env, timeout=900)
    return (r.returncode, r.stdout.decode("utf-8", "replace"),
            r.stderr.decode("utf-8", "replace"))


def _obs_records(text: str) -> list:
    return [l for l in text.splitlines() if _OBS.match(l.strip())]


def _norm(t: str) -> str:
    return re.sub(r"proj_[a-f0-9]+", "X", t)


@section
def test_t1_t2_channel_split(c):
    """T1 stdout is product-only; T2 observability still on stderr."""
    rc, out, err = _run_demo("demo")
    c.chk("T1 demo exits 0 (demo mode)", rc == 0, err[-200:])
    c.chk("T1 stdout carries the product output",
          all(m in out for m in _PRODUCT))
    recs_out = _obs_records(out)
    c.chk("T1 stdout contains NO observability JSONL",
          recs_out == [], recs_out[:1])
    for marker in ('"event":', '"duration_ms"', '"timestamp"',
                   "trace_id", "correlation_id", "request_id"):
        c.chk("T1 stdout free of %r" % marker, marker not in out)

    recs_err = _obs_records(err)
    c.chk("T2 observability present on stderr", len(recs_err) >= 1)
    events = []
    for l in recs_err:
        try:
            events.append(json.loads(l).get("event"))
        except ValueError:
            pass
    c.chk("T2 knowledge.search observable on stderr",
          "knowledge.search" in events, events)

    # T2 mechanism: the SAME sink writes to stderr, never stdout, and the
    # record keeps the request/run/task/skill/completion identity.
    from runtime.obs import context as obs_ctx
    from runtime.obs.log import JsonlLogger

    lg = JsonlLogger(path=None, mirror_stderr=True)
    so, se = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        with obs_ctx.start_request(project_id="proj_demo", case_id="case-1"):
            with obs_ctx.span(task_id="task_7",
                              skill_name="report_specialist"):
                lg.emit("run.completed", status="COMPLETED")
    c.chk("T2 mirror wrote NOTHING to stdout", so.getvalue() == "")
    lines = [l for l in se.getvalue().splitlines() if l.strip()]
    c.chk("T2 mirror wrote exactly one record to stderr", len(lines) == 1)
    rec = json.loads(lines[-1]) if lines else {}
    c.chk("T2 stderr record keeps event + status",
          rec.get("event") == "run.completed"
          and rec.get("status") == "COMPLETED")
    c.chk("T2 stderr record keeps the request id (req_)",
          str(rec.get("request_id", "")).startswith("req_"))
    c.chk("T2 stderr record keeps task + skill identity",
          rec.get("task_id") == "task_7"
          and rec.get("skill_name") == "report_specialist")

    off = JsonlLogger(path=None)
    se2 = io.StringIO()
    with contextlib.redirect_stderr(se2):
        off.emit("run.completed", status="COMPLETED")
    c.chk("T2 mirror OFF writes nothing to stderr", se2.getvalue() == "")


@section
def test_t3_deterministic_product_output(c):
    """T3 — product stdout is deterministic across N=3 runs."""
    runs = [_run_demo("demo") for _ in range(3)]
    c.chk("T3 3/3 runs COMPLETED",
          all(all(m in o for m in ("FINAL", "COMPLETED"))
              for _, o, _ in runs))
    outs = [o for _, o, _ in runs]
    c.chk("T3 product stdout identical across 3 runs",
          all(_norm(o) == _norm(outs[0]) for o in outs))
    c.chk("T3 no observability in any run's stdout",
          all(_obs_records(o) == [] for o in outs))


@section
def test_t5_t6_obs_off_on_business_invariance(c):
    """T5 observability OFF / T6 ON — identical product output.

    The mirror is tied to DEMO mode: 'demo' -> mirror ON (stderr),
    'evaluation' -> mirror OFF. The PRODUCT channel must not change."""
    rc_on, on, err_on = _run_demo("demo")            # observability ON
    rc_off, off, err_off = _run_demo("evaluation")   # observability OFF
    c.chk("T5 observability OFF -> valid product output",
          rc_off == 0 and all(m in off for m in _PRODUCT))
    c.chk("T6 observability ON -> valid product output",
          rc_on == 0 and all(m in on for m in _PRODUCT))
    c.chk("T5/T6 product output identical (obs ON == OFF)",
          _norm(on) == _norm(off))
    c.chk("T5 obs OFF -> no mirror on stderr", _obs_records(err_off) == [])
    c.chk("T6 obs ON -> mirror on stderr", len(_obs_records(err_on)) >= 1)


@section
def test_security_redaction_on_stderr(c):
    """§9 — moving the mirror to stderr must not create a leak path."""
    from runtime.obs.log import JsonlLogger

    secrets = {
        "openai_key": "sk-ABCDEFGHIJ1234567890abcdef",
        "ghp_token": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
        "bearer_jwt": ("Bearer eyJhbGciOiJIUzI1NiJ9."
                       "eyJzdWIiOiIxIn0.Zm9vYmFyYmF6"),
        "private_key": "-----BEGIN PRIVATE KEY-----MIIEvQIBADANBg",
    }
    lg = JsonlLogger(path=None, mirror_stderr=True)
    se = io.StringIO()
    with contextlib.redirect_stderr(se):
        lg.emit("llm.call", status="OK",
                authorization=secrets["bearer_jwt"],
                api_key=secrets["openai_key"],
                token=secrets["ghp_token"],
                note="priv=%s" % secrets["private_key"])
    line = se.getvalue()
    c.chk("SEC stderr mirror emitted a record", '"timestamp"' in line)
    for name, val in secrets.items():
        c.chk("SEC raw %s value absent from stderr" % name, val not in line)
    for key in ("authorization", "api_key", "token"):
        c.chk("SEC %s key not emitted verbatim" % key,
              ('"%s":' % key) not in line)


def main() -> int:
    os.chdir(REPO)
    return run_sections(SECTIONS, "p25_1_output_channel_log.txt",
                        "PHASE 25.1 OUTPUT CHANNEL ISOLATION")


if __name__ == "__main__":
    sys.exit(main())
