"""Backup — Phase 13 P1 Stage 1 / Item 1a.

An operator capability, NOT a runtime capability: backup never creates
tasks, changes task/CaseState/approval state, or touches eval/repair/
replan/HITL/HOTL/MessageBus. It copies already-persisted bytes.

Design contract (stage1-plan §Item 1):

  * Consistency — a backup runs under the EXISTING R-01 index lock
    (`FileLock(projects.json)`) for its whole duration, and only for
    quiescent projects: any task RUNNING (or project mid-run) is
    REJECTED fail-closed. After copying, the source's volatile files are
    re-hashed; if anything moved mid-copy the backup is DELETED and
    reported FAILED — never a snapshot stitched from two time points.

  * Verifiability — every copied file lands in a manifest with size +
    sha256 + an encrypted flag (re-derived from the `IA1:` ciphertext
    magic; the tool never touches the key). `verify_backup()` re-checks
    existence, size, hash AND magic-vs-flag consistency.

  * Atomicity — the manifest is written LAST through the existing
    `atomic_write_json` (temp + fsync + replace). A directory without a
    complete manifest is by definition not a backup.

  * Encryption — reuses P0.1 unchanged. Encrypted sources are copied as
    opaque ciphertext (backup never needs the key); plaintext DEMO sources
    are copied as plaintext, and the manifest records which is which.

Statuses: BACKUP_CREATED / BACKUP_REJECTED / BACKUP_FAILED (with a
reason; BACKUP_INVALID is the verify-side verdict).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
import uuid
from typing import Optional

from runtime.state.durable import FileLock, atomic_write_json, read_json_retry

MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = "1.0"
_MAGIC = b"IA1:"          # dataprotection ciphertext magic
_VOLATILE = ("project.json",)   # re-hashed post-copy for consistency
# skip lock files and our own outputs
_SKIP_SUFFIXES = (".lock",)
_SKIP_NAMES = (MANIFEST_NAME,)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_encrypted(data: bytes) -> bool:
    return data[:len(_MAGIC)] == _MAGIC


def _index_path(harness_root: str) -> str:
    return os.path.join(harness_root, "projects.json")


def _project_quiescent(project) -> tuple:
    """(ok, reason). Fail-closed: only quiescent projects are backed up.
    A mid-run project snapshot cannot be proven consistent, so we refuse
    rather than ship a mixed snapshot."""
    if any(t.get("status") == "RUNNING" for t in project.tasks):
        return False, "RUNNING tasks exist — backup requires a quiescent project"
    if project.status == "running":
        return False, "project is mid-run"
    return True, ""


def backup_project(harness_root: str, project_id: str, dest_dir: str,
                   *, emit=None) -> dict:
    """Snapshot ONE project into <dest_dir>/<backup_id>/ under the R-01
    index lock. Returns a status dict:
      {"status": "BACKUP_CREATED"|"BACKUP_REJECTED"|"BACKUP_FAILED",
       "backup_id", "backup_dir"?, "reason"?, "files"?, "manifest"?}
    Fail-closed everywhere; a rejected/failed backup leaves no partial
    directory behind."""
    emit = emit or (lambda msg: None)
    from runtime.harness.harness import load_project, _index_read

    harness_root = os.path.abspath(harness_root)
    dest_dir = os.path.abspath(dest_dir)
    if not os.path.isdir(harness_root):
        return {"status": "BACKUP_REJECTED", "reason": "harness root not found"}

    backup_id = "bkp_%s" % uuid.uuid4().hex[:10]
    backup_dir = os.path.join(dest_dir, backup_id)

    # The index lock serializes us against every Project._save (index
    # upsert), delete_project, and any other backup — the whole snapshot
    # happens inside the critical section (Q1/Q2/Q3 in the stage1 plan).
    with FileLock(_index_path(harness_root)):
        project = load_project(harness_root, project_id)
        if project is None:
            return {"status": "BACKUP_REJECTED",
                    "reason": "project not found: %s" % project_id}
        ok, reason = _project_quiescent(project)
        if not ok:
            return {"status": "BACKUP_REJECTED", "reason": reason}

        index_entry = next(
            (e for e in _index_read(harness_root)
             if e.get("project_id") == project_id), None)

        pdir = os.path.join(harness_root, project_id)
        # collect + copy under the lock; re-verify volatile sources after
        entries = []
        post_check = {}
        os.makedirs(backup_dir, exist_ok=True)
        try:
            for root, _dirs, files in os.walk(pdir):
                for name in sorted(files):
                    if name.endswith(_SKIP_SUFFIXES) or name in _SKIP_NAMES:
                        continue
                    rel = os.path.relpath(os.path.join(root, name), pdir)
                    with open(os.path.join(root, name), "rb") as f:
                        data = f.read()
                    target = os.path.join(backup_dir, rel)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                    entries.append({
                        "relative_path": rel.replace(os.sep, "/"),
                        "size": len(data),
                        "sha256": _sha256(data),
                        "encrypted": _is_encrypted(data),
                    })
                    if rel in _VOLATILE:
                        post_check[rel] = _sha256(data)

            # consistency re-check (Q3): if anything moved mid-copy, fail
            for rel, copied_hash in post_check.items():
                with open(os.path.join(pdir, rel), "rb") as f:
                    if _sha256(f.read()) != copied_hash:
                        raise RuntimeError(
                            "INCONSISTENT_SNAPSHOT: %s changed during backup"
                            % rel)

            manifest = {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "backup_id": backup_id,
                "project_id": project_id,
                "case_id": project.case_id,
                "created_at": _now(),
                "files": entries,
                "index_entry": index_entry,
                "project_status_at_backup": project.status,
            }
            # manifest LAST, atomically (temp + fsync + replace). Until
            # this lands, the directory is not a valid backup.
            atomic_write_json(os.path.join(backup_dir, MANIFEST_NAME),
                              manifest)
        except Exception as e:  # noqa: BLE001 — any failure deletes the
            # partial copy: an incomplete backup must never look valid
            shutil.rmtree(backup_dir, ignore_errors=True)
            emit("BACKUP_FAILED %s: %s" % (project_id, str(e)[:120]))
            return {"status": "BACKUP_FAILED", "reason": str(e)[:300],
                    "backup_id": backup_id}

    emit("BACKUP_CREATED %s (%d files)" % (project_id, len(entries)))
    return {"status": "BACKUP_CREATED", "backup_id": backup_id,
            "backup_dir": backup_dir, "files": len(entries),
            "manifest": manifest}


def backup_root(harness_root: str, dest_dir: str, *, emit=None) -> dict:
    """Back up EVERY project in the root. Each project gets its own
    locked snapshot; a rejected/failed project is reported and does not
    abort the others."""
    from runtime.harness.harness import _index_read
    results = []
    for entry in _index_read(harness_root):
        pid = entry.get("project_id")
        results.append(backup_project(harness_root, pid, dest_dir,
                                     emit=emit))
    return {"status": "BACKUP_CREATED", "backups": results,
            "created": sum(1 for r in results
                           if r["status"] == "BACKUP_CREATED"),
            "rejected": sum(1 for r in results
                            if r["status"] == "BACKUP_REJECTED"),
            "failed": sum(1 for r in results
                          if r["status"] == "BACKUP_FAILED")}


def verify_backup(backup_dir: str) -> dict:
    """Fail-closed validity check. A backup is VALID only if the manifest
    exists, parses, lists every present file with matching size + sha256,
    and each file's ciphertext magic matches its recorded encrypted flag.
    Returns {"valid": bool, "reason"/"files": ...}."""
    manifest_path = os.path.join(backup_dir, MANIFEST_NAME)
    if not os.path.isdir(backup_dir):
        return {"valid": False, "reason": "BACKUP_INVALID: no backup directory"}
    manifest = read_json_retry(manifest_path)
    if manifest is None:
        return {"valid": False,
                "reason": "BACKUP_INVALID: manifest missing or unreadable"}
    for field in ("schema_version", "backup_id", "project_id", "files"):
        if field not in manifest:
            return {"valid": False,
                    "reason": "BACKUP_INVALID: manifest field %r missing" % field}
    if not isinstance(manifest["files"], list) or not manifest["files"]:
        return {"valid": False, "reason": "BACKUP_INVALID: manifest lists no files"}

    listed = set()
    for entry in manifest["files"]:
        rel = entry.get("relative_path", "")
        if not rel or ".." in rel.split("/"):
            return {"valid": False,
                    "reason": "BACKUP_INVALID: bad relative_path in manifest"}
        path = os.path.join(backup_dir, *rel.split("/"))
        if not os.path.isfile(path):
            return {"valid": False,
                    "reason": "BACKUP_INVALID: listed file missing: %s" % rel}
        with open(path, "rb") as f:
            data = f.read()
        if len(data) != entry.get("size", -1):
            return {"valid": False,
                    "reason": "BACKUP_INVALID: size mismatch: %s" % rel}
        if _sha256(data) != entry.get("sha256"):
            return {"valid": False,
                    "reason": "BACKUP_INVALID: sha256 mismatch: %s" % rel}
        if _is_encrypted(data) != bool(entry.get("encrypted")):
            return {"valid": False,
                    "reason": "BACKUP_INVALID: encryption flag mismatch: %s" % rel}
        listed.add(rel)

    # unlisted stray files (excluding the manifest) invalidate too
    for root, _dirs, files in os.walk(backup_dir):
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), backup_dir) \
                .replace(os.sep, "/")
            if rel != MANIFEST_NAME and rel not in listed:
                return {"valid": False,
                        "reason": "BACKUP_INVALID: unlisted file: %s" % rel}
    return {"valid": True, "files": len(listed),
            "backup_id": manifest["backup_id"],
            "project_id": manifest["project_id"]}


if __name__ == "__main__":  # pragma: no cover — operator CLI
    import argparse
    ap = argparse.ArgumentParser(
        description="Item 1a backup tool (single node, operator-run)")
    ap.add_argument("harness_root")
    ap.add_argument("dest_dir")
    ap.add_argument("project_id", nargs="?", default=None,
                    help="project id, or omit with --all for every project")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--verify", metavar="BACKUP_DIR",
                    help="only verify an existing backup directory")
    args = ap.parse_args()
    if args.verify:
        out = verify_backup(args.verify)
        print("VALID" if out["valid"] else out.get("reason", "INVALID"))
        raise SystemExit(0 if out["valid"] else 1)
    if bool(args.project_id) == bool(args.all):
        raise SystemExit("specify exactly one of project_id or --all")
    out = (backup_root(args.harness_root, args.dest_dir) if args.all
           else backup_project(args.harness_root, args.project_id,
                              args.dest_dir))
    if "backups" in out:
        print("created=%(created)d rejected=%(rejected)d failed=%(failed)d"
              % out)
        code = 0 if out["failed"] == 0 else 1
    else:
        print("%s %s" % (out["status"], out.get("reason", "")))
        code = 0 if out["status"] == "BACKUP_CREATED" else 1
    raise SystemExit(code)
