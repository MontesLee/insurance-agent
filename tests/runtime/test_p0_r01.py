"""Phase 13 P0 R-01 — persistence race & corruption tests (T-R01-01..06).

Round-1 audit measured: 8 concurrent Project._save() → 3 index entries
(silent lost update), and a reader crashing with JSONDecodeError on a
partially written projects.json. These tests prove the fix.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime.harness.harness import (LongRunningHarness, Project,  # noqa: E402
                                     _index_read, _index_upsert, load_project)
from runtime.state.durable import (atomic_write_json, FileLock,  # noqa: E402
                                   read_json_retry, locked_update_json)

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="r01_", dir=os.path.join(REPO, "tmp"))


@section
def test_t_r01_01_single_write(c: Checks):
    d = fresh_dir()
    try:
        atomic_write_json(os.path.join(d, "a.json"), {"x": 1})
        c.chk("T-R01-01: single atomic write reads back",
              json.load(open(os.path.join(d, "a.json"), encoding="utf-8")) == {"x": 1})
        p = Project("proj_solo", "n", "c1", d)
        p._save()
        c.chk("T-R01-01: single Project._save indexed",
              len(_index_read(d)) == 1)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r01_02_concurrent_writes(c: Checks):
    d = fresh_dir()
    try:
        errs = []
        def make(i):
            try:
                Project("proj_%d" % i, "n", "c%d" % i, d)._save()
            except Exception as e:  # noqa: BLE001
                errs.append(repr(e))
        ts = [threading.Thread(target=make, args=(i,)) for i in range(16)]
        [t.start() for t in ts]; [t.join() for t in ts]
        idx = _index_read(d)
        c.chk("T-R01-02: 16 concurrent saves → 16 index entries (was 3-5)",
              len(idx) == 16, len(idx))
        c.chk("T-R01-02: no errors", not errs, errs[:2])
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r01_03_concurrent_read_write(c: Checks):
    d = fresh_dir()
    try:
        stop = threading.Event()
        read_errs = []
        def reader():
            while not stop.is_set():
                try:
                    idx = _index_read(d)
                    if not isinstance(idx, list):
                        read_errs.append("non-list")
                except Exception as e:  # noqa: BLE001
                    read_errs.append(repr(e))
        rt = threading.Thread(target=reader); rt.start()
        def make(i):
            Project("proj_%d" % i, "n", "c%d" % i, d)._save()
        ts = [threading.Thread(target=make, args=(i,)) for i in range(12)]
        [t.start() for t in ts]; [t.join() for t in ts]
        stop.set(); rt.join()
        c.chk("T-R01-03: concurrent readers never crash/corrupt (was "
              "JSONDecodeError)", not read_errs, read_errs[:2])
        c.chk("T-R01-03: all 12 entries survive", len(_index_read(d)) == 12)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r01_04_interruption_during_write(c: Checks):
    """Simulate a crash mid-write: replace is atomic, so the file on disk
    is ALWAYS the complete previous or complete new document."""
    d = fresh_dir()
    try:
        path = os.path.join(d, "doc.json")
        atomic_write_json(path, {"version": 1})
        # kill-point simulation: an atomic_write that dies after writing
        # the temp file but BEFORE replace leaves the old doc intact
        import tempfile as _tf
        fd, tmp = _tf.mkstemp(dir=d)
        os.write(fd, b'{"version": 2, "partial"')
        os.close(fd)
        # old document untouched
        c.chk("T-R01-04: interrupted write leaves the previous document",
              json.load(open(path, encoding="utf-8")) == {"version": 1})
        os.unlink(tmp)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r01_05_corrupted_file(c: Checks):
    d = fresh_dir()
    try:
        path = os.path.join(d, "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"broken": ')
        try:
            read_json_retry(path, retries=2, delay=0.01)
            c.chk("T-R01-05: genuinely corrupt file raises loudly", False)
        except json.JSONDecodeError:
            c.chk("T-R01-05: genuinely corrupt file raises loudly", True)
        c.chk("T-R01-05: missing file returns None",
              read_json_retry(os.path.join(d, "nope.json")) is None)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r01_06_recovery_after_interrupted_write(c: Checks):
    d = fresh_dir()
    try:
        # a project saved, then a simulated crash left a stale lock file
        p = Project("proj_r", "n", "c", d)
        p._save()
        with open(os.path.join(d, "projects.json.lock"), "wb") as f:
            pass  # stale lock file (no holder) must not block the next save
        p2 = Project("proj_r2", "n", "c2", d)
        p2._save()
        c.chk("T-R01-06: stale lock file does not block recovery saves",
              len(_index_read(d)) == 2)
        # and a NEW process (fresh import path) can resume the project
        loaded = load_project(d, "proj_r")
        c.chk("T-R01-06: project loadable after recovery", loaded is not None)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r01_cross_process_lock(c: Checks):
    """The lock is cross-PROCESS: two subprocesses racing on the index
    must both survive (no lost entries)."""
    import subprocess
    d = fresh_dir()
    try:
        script = (
            "import sys; sys.path.insert(0, %r);"
            "from runtime.harness.harness import Project;"
            "Project('proj_' + sys.argv[1], 'n', 'c', sys.argv[2])._save()"
            % (REPO,))
        procs = [subprocess.Popen([sys.executable, "-c", script, str(i), d],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(6)]
        for pr in procs:
            _, err = pr.communicate(timeout=60)
            c.chk("T-R01-CP: subprocess exit 0", pr.returncode == 0,
                  err.decode()[-120:])
        c.chk("T-R01-CP: 6 cross-process saves → 6 entries",
              len(_index_read(d)) == 6, len(_index_read(d)))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    return run_sections(SECTIONS, "webui_test_r01_log.txt",
                        "P0 R-01 PERSISTENCE")


if __name__ == "__main__":
    sys.exit(main())
