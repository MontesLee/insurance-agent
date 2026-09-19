"""Durable file primitives (Phase 13 R-01).

Round-1 audit measured two defects in the JSON persistence layer:

  1. projects.json index: read-modify-rewrite with no coordination —
     8 concurrent saves silently lost updates (3-5 entries survived).
  2. non-atomic rewrites — a concurrent reader crashed with
     JSONDecodeError on a partially written file.

Fixes (minimal, single-process/single-node scope):

  * atomic_write_json() — write to a temp file in the SAME directory,
    fsync, then os.replace() (atomic on POSIX and Windows). Readers see
    either the old or the new complete document, never a partial one.
  * FileLock — advisory inter-process lock (msvcrt.locking on Windows,
    fcntl.flock on POSIX) around read-modify-write sections, plus a
    per-path thread lock so threads in one process also serialize.
  * read_json_retry() — tolerant read for legacy/corrupt files: retries
    briefly (a concurrent atomic replace can momentarily hold the old
    file open), then raises a loud error instead of returning garbage.

No databases, no new dependencies — this stays within the project's
single-node durable-JSON design and keeps every existing call shape.
"""
from __future__ import annotations

import errno
import json
import os
import tempfile
import threading
import time
from typing import Optional

_RETRY_SECONDS = 2.0


def atomic_write_json(path: str, doc, indent: int = 2) -> None:
    """Atomically write `doc` as JSON to `path` (temp + fsync + replace).

    On Windows, os.replace to a destination a reader currently has open
    raises PermissionError; short-lived readers release quickly, so the
    replace is retried within a bounded window."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        deadline = time.time() + _RETRY_SECONDS
        while True:
            try:
                os.replace(tmp, path)  # atomic on Windows and POSIX
                return
            except PermissionError:
                if time.time() >= deadline:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json_retry(path: str, retries: int = 40, delay: float = 0.05):
    """Read JSON, tolerating a concurrent atomic replace (a brief
    PermissionError on Windows, or a transiently missing/locked file).
    Raises the last error loudly if genuinely corrupt."""
    last = None
    for _ in range(retries):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except PermissionError as e:  # replace-in-flight on Windows
            last = e
            time.sleep(delay)
        except json.JSONDecodeError as e:  # partially written legacy file
            last = e
            time.sleep(delay)
    raise last


class FileLock:
    """Advisory cross-process + cross-thread lock for one path.

    Held section should be short (read-modify-write of one file). Usage:

        with FileLock(path):
            entries = read_json_retry(path) or []
            ...mutate...
            atomic_write_json(path, entries)

    Re-entrant per THREAD (Item 1b restore holds the index lock for the
    whole restore and then updates the index through locked_update_json):
    the RLock admits the same thread again, and the OS-level byte lock
    is only taken on the OUTERMOST acquisition (msvcrt/fcntl range locks
    are not re-entrant across handles even within one process).
    """

    _thread_locks: dict = {}
    _registry_lock = threading.Lock()
    _os_holders: dict = {}      # lock_path -> {thread_id: depth}

    def __init__(self, path: str):
        self.path = path
        self._lock_path = path + ".lock"
        with FileLock._registry_lock:
            lock = FileLock._thread_locks.get(self._lock_path)
            if lock is None:
                lock = threading.RLock()
                FileLock._thread_locks[self._lock_path] = lock
        self._tlock = lock
        self._fh = None

    def _acquire_os(self):
        import sys
        os.makedirs(os.path.dirname(os.path.abspath(self._lock_path)) or ".",
                    exist_ok=True)
        self._fh = open(self._lock_path, "a+b")
        deadline = time.time() + _RETRY_SECONDS
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError as e:
                if e.errno not in (errno.EACCES, errno.EAGAIN,
                                   errno.EDEADLK, errno.EWOULDBLOCK):
                    raise
                if time.time() >= deadline:
                    raise TimeoutError(
                        "could not acquire lock for %s" % self._lock_path)
                time.sleep(0.05)

    def _release_os(self):
        import sys
        try:
            if sys.platform == "win32":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        self._tlock.acquire()
        reentrant = False
        with FileLock._registry_lock:
            holders = FileLock._os_holders.setdefault(self._lock_path, {})
            tid = threading.get_ident()
            if holders.get(tid, 0) > 0:
                holders[tid] += 1          # same thread already owns the
                reentrant = True          # OS lock — skip re-acquiring it
            else:
                holders[tid] = 1
        if reentrant:
            return self
        try:
            self._acquire_os()
            return self
        except BaseException:
            with FileLock._registry_lock:
                FileLock._os_holders.get(self._lock_path, {}).pop(
                    threading.get_ident(), None)
            self._tlock.release()
            raise

    def __exit__(self, *exc):
        try:
            with FileLock._registry_lock:
                holders = FileLock._os_holders.get(self._lock_path, {})
                tid = threading.get_ident()
                depth = holders.get(tid, 0)
                if depth <= 1:
                    if depth == 1:
                        holders.pop(tid, None)
                    if depth:
                        self._release_os()
        finally:
            self._tlock.release()
        return False


def locked_update_json(path: str, mutator, default_factory=list):
    """Read-modify-write one JSON file under its lock, atomically."""
    with FileLock(path):
        doc = read_json_retry(path)
        if doc is None:
            doc = default_factory() if callable(default_factory) else default_factory
        out = mutator(doc)
        if out is not None:
            doc = out
        atomic_write_json(path, doc)
        return doc
