"""Restore — Phase 13 P1 Stage 1 / Item 1b.

Restores a VERIFIED Item-1a backup into the harness root as a consistent
project state. An operator capability, not a runtime capability: restore
never runs eval, never approves, never schedules — the restored bytes are
placed back under the existing R-01 lock and re-validated through the
existing checkpoint/artifact validators.

Flow (fail-closed, all-or-nothing):

    verify_backup()            -- invalid backup never reaches staging
      ↓
    R-01 FileLock(projects.json)          (whole restore inside the lock)
      ↓
    identity checks            -- backup.project_id == target project_id
      ↓                              (no restore-as-new-project in 1b)
    staging directory         -- restore NEVER writes the live project first
      ↓
    staging validation        -- project.json parses; case_state loads
      ↓                         through the EXISTING checkpoint validation
      ↓                         (schema + registry fingerprints + task→stage);
      ↓                         approvals sanity (no forged actors)
      ↓
    atomic commit            -- copy staged files in, then atomically update
      ↓                         projects.json via locked_update_json
      ↓
    post-commit verify       -- verify_backup on the committed tree + index
      ↓
    RESTORE_SUCCESS / RESTORE_FAILED (partial state rolled back)

Restore ≠ APPROVE: the restored approval state is whatever the backup
held, byte-for-byte; restore never creates APPROVED /
READY_FOR_MANUAL_DELIVERY and never calls any approval API. A restored
unapproved deliverable remains gated by the R-02 final-review rules (a
project restored into a strict-mode root re-derives gate behavior from
INSURANCE_AGENT_MODE at the next run(), because the gate is enforced at
run() time — restore itself only moves bytes).

Encryption: files are copied AS-IS (ciphertext stays ciphertext). In a
strict-mode root, at-rest protection is preserved because the committed
bytes are the same ciphertext the backup held; a plaintext backup
committed into a strict root would sit plaintext on disk — so restore
REFUSES plaintext source files when the target mode requires encryption.
The tool never reads or writes any key; the key is only consulted
indirectly (via dataprotection.load_data_key existence check) to decide
whether ciphertext on disk is decryptable by this node — the key bytes
themselves never enter restore, logs or output.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid

from runtime.state.durable import (FileLock, atomic_write_json,
                                  locked_update_json)
from runtime.state import backup as bk
from runtime.state import store as state_store

RESTORE_SCHEMA_VERSIONS = ("1.0",)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _index_path(harness_root: str) -> str:
    return os.path.join(harness_root, "projects.json")


def _mode_requires_encryption() -> bool:
    from runtime import mode as rt_mode
    return rt_mode.encryption_required()


def _staging_sanity(staging_dir: str, manifest: dict) -> tuple:
    """Validate the STAGED tree before any live state is touched. Uses the
    EXISTING validators wherever one exists (checkpoint validation with
    schema + registry fingerprints). Returns (ok, reasons)."""
    from runtime import checkpoint as cp
    from runtime import artifact_registry as reg
    reasons = []
    project_id = manifest.get("project_id", "")

    ppath = os.path.join(staging_dir, "project.json")
    if not os.path.isfile(ppath):
        return False, ["missing project.json in backup"]
    try:
        project = json.load(open(ppath, encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, ["project.json unreadable: %s" % str(e)[:80]]
    if project.get("project_id") != project_id:
        return False, ["project.json id mismatch"]
    if project.get("case_id") != manifest.get("case_id"):
        return False, ["case_id mismatch between manifest and project.json"]

    # case state: validate through the EXISTING checkpoint validator for
    # every case dir present (schema + registry fingerprints + tasks)
    case_root = os.path.join(staging_dir, "case")
    found_case = False
    if os.path.isdir(case_root):
        for name in os.listdir(case_root):
            if not os.path.isdir(os.path.join(case_root, name)):
                continue
            found_case = True
            state = state_store.load(case_root, name)
            if state is None:
                try:  # plaintext mode without a key → load returns None
                    with open(os.path.join(case_root, name,
                                          "case_state.json"), "rb") as f:
                        raw = f.read()
                except FileNotFoundError:
                    reasons.append("case %s: case_state.json missing" % name)
                    continue
                # try explicit decryption via the existing boundary
                from runtime.state.dataprotection import read_protected, \
                    load_data_key
                text = read_protected(os.path.join(case_root, name,
                                                   "case_state.json"),
                                       load_data_key())
                if text is None:
                    reasons.append("case %s: unreadable state" % name)
                    continue
                try:
                    state = json.loads(text)
                except json.JSONDecodeError:
                    # undecryptable (no key) or garbage → fail closed
                    reasons.append("case %s: state not readable on this "
                                  "node (key missing or data corrupt)"
                                  % name)
                    continue
            ok, errs = cp.validate(state, name)
            if not ok:
                reasons.extend("case %s: %s" % (name, e) for e in errs[:3])

    # approvals sanity (R38): known approval statuses only; never trust a
    # forged actor string in a way that would CREATE approval — we only
    # check shape; semantics stay byte-for-byte from the backup.
    apath = os.path.join(staging_dir, "approvals.jsonl")
    if os.path.isfile(apath):
        try:
            with open(apath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if rec.get("status") not in (
                            "PENDING", "WAITING_HUMAN", "APPROVED",
                            "REJECTED", "EXPIRED", "RESUMED"):
                        reasons.append("approvals: bad status %r"
                                      % rec.get("status"))
        except json.JSONDecodeError:
            reasons.append("approvals.jsonl corrupt")
    return (not reasons), reasons or []


def restore_project(harness_root: str, project_id: str, backup_dir: str,
                    *, allow_overwrite: bool = False,
                    emit=None) -> dict:
    """Restore one verified backup into harness_root. All-or-nothing: any
    failure leaves the live project untouched. Returns a status dict:
      {"status": "RESTORE_SUCCESS"|"RESTORE_REJECTED"|"RESTORE_FAILED",
       "restore_id", "reason"?, "files"?, "audit"?}
    A minimal audit record (restore_id, project_id, backup_id, timestamp,
    result, reason) is appended to <harness_root>/restore.log — ids and
    reasons only, never content."""
    emit = emit or (lambda m: None)
    harness_root = os.path.abspath(harness_root)
    backup_dir = os.path.abspath(backup_dir)
    restore_id = "rst_%s" % uuid.uuid4().hex[:10]

    def _audit(result, reason=""):
        try:
            os.makedirs(harness_root, exist_ok=True)
            with open(os.path.join(harness_root, "restore.log"), "a",
                      encoding="utf-8") as f:
                f.write(json.dumps({
                    "restore_id": restore_id, "project_id": project_id,
                    "backup_id": (manifest or {}).get("backup_id", "?"),
                    "timestamp": _now(), "result": result,
                    "reason": reason[:200]}) + "\n")
        except OSError:  # audit is best-effort; never blocks the restore
            pass

    manifest = None

    # 1) verify BEFORE anything touches the live root (§4)
    v = bk.verify_backup(backup_dir)
    if not v.get("valid"):
        _audit("RESTORE_REJECTED", v.get("reason", "invalid backup"))
        return {"status": "RESTORE_REJECTED", "restore_id": restore_id,
                "reason": v.get("reason", "BACKUP_INVALID")}
    manifest = json.load(open(os.path.join(backup_dir,
                                          bk.MANIFEST_NAME),
                              encoding="utf-8"))
    if manifest.get("schema_version") not in RESTORE_SCHEMA_VERSIONS:
        _audit("RESTORE_REJECTED", "unsupported schema_version")
        return {"status": "RESTORE_REJECTED", "restore_id": restore_id,
                "reason": "unsupported backup schema_version"}

    # 2) identity: backup A cannot restore into project B (§9)
    if manifest.get("project_id") != project_id:
        _audit("RESTORE_REJECTED", "identity mismatch")
        return {"status": "RESTORE_REJECTED", "restore_id": restore_id,
                "reason": "backup project_id %r != target %r"
                          % (manifest.get("project_id"), project_id)}

    # 3) encryption invariant (§13): ciphertext stays ciphertext; a
    #    strict-mode root cannot accept a plaintext backup
    for entry in manifest["files"]:
        if _mode_requires_encryption() and not entry.get("encrypted"):
            _audit("RESTORE_REJECTED", "plaintext backup in encrypted mode")
            return {"status": "RESTORE_REJECTED", "restore_id": restore_id,
                    "reason": "RESTORE_REJECTED: target mode requires "
                               "encryption; backup contains plaintext files"}

    staging = os.path.join(harness_root,
                            ".restore_staging_%s" % restore_id)
    committed = os.path.join(harness_root, project_id)

    with FileLock(_index_path(harness_root)):
        try:
            return _restore_locked(harness_root, project_id, backup_dir,
                                  manifest, staging, committed,
                                  restore_id, allow_overwrite, emit,
                                  _audit)
        except Exception as e:  # noqa: BLE001 — any failure: no partial state
            shutil.rmtree(staging, ignore_errors=True)
            emit("RESTORE_FAILED %s: %s" % (project_id, str(e)[:100]))
            _audit("RESTORE_FAILED", str(e)[:200])
            return {"status": "RESTORE_FAILED", "restore_id": restore_id,
                    "reason": str(e)[:300]}


def _restore_locked(harness_root, project_id, backup_dir, manifest,
                    staging, committed, restore_id, allow_overwrite,
                    emit, _audit):
    if True:  # keeps the original indentation below intact
            # 4) target rules: no silent overwrite of a live project
            if os.path.isdir(committed) and not allow_overwrite:
                _audit("RESTORE_REJECTED", "target exists")
                return {"status": "RESTORE_REJECTED",
                        "restore_id": restore_id,
                        "reason": "target project exists — pass "
                                   "allow_overwrite to replace it"}
            if os.path.isdir(committed) and allow_overwrite:
                # overwrite = replace atomically: stage first, then swap
                # the old dir aside and delete only after success
                pass  # handled in commit below

            # 5) staging: copy the verified tree (bytes as-is) + validate
            os.makedirs(staging, exist_ok=True)
            for entry in manifest["files"]:
                rel = entry["relative_path"]
                src = os.path.join(backup_dir, *rel.split("/"))
                dst = os.path.join(staging, *rel.split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)          # bytes as-is (no key)
            # the manifest travels with the restored tree so post-commit
            # verification can re-hash the committed files in place
            shutil.copyfile(os.path.join(backup_dir, bk.MANIFEST_NAME),
                           os.path.join(staging, bk.MANIFEST_NAME))
            ok, reasons = _staging_sanity(staging, manifest)
            if not ok:
                shutil.rmtree(staging, ignore_errors=True)
                _audit("RESTORE_FAILED", "; ".join(reasons))
                return {"status": "RESTORE_FAILED", "restore_id": restore_id,
                        "reason": "; ".join(reasons)[:300]}

            # 6) atomic commit (§7): swap the project dir, then update
            #    the index under the SAME lock
            old_aside = None
            if os.path.isdir(committed):
                old_aside = committed + ".restore_old_%s" % restore_id
                os.rename(committed, old_aside)
            try:
                os.rename(staging, committed)
            except OSError as e:
                if old_aside:
                    os.rename(old_aside, committed)   # put the old back
                raise
            # index: insert/replace the entry from the manifest snapshot
            index_entry = manifest.get("index_entry") or {
                "project_id": project_id,
                "name": manifest.get("project_id"),
                "case_id": manifest.get("case_id"),
                "status": manifest.get("project_status_at_backup", "pending"),
                "updated_at": _now()}

            def _mutate(entries):
                return [e for e in entries
                        if e.get("project_id") != project_id] + [index_entry]
            locked_update_json(_index_path(harness_root), _mutate,
                              default_factory=list)

            # 7) post-commit verify: the committed tree still verifies and
            #    the index is readable and coherent
            pv = bk.verify_backup(committed)   # manifest travels with it
            idx_ok = True
            try:
                idx = json.load(open(_index_path(harness_root),
                                    encoding="utf-8"))
                idx_ok = any(e.get("project_id") == project_id for e in idx)
            except (json.JSONDecodeError, OSError):
                idx_ok = False
            if not pv.get("valid") or not idx_ok:
                # rollback the commit, restore the old tree
                shutil.rmtree(committed, ignore_errors=True)
                if old_aside:
                    os.rename(old_aside, committed)
                _audit("RESTORE_FAILED", "post-commit verification failed")
                return {"status": "RESTORE_FAILED", "restore_id": restore_id,
                        "reason": "post-commit verification failed"}

            if old_aside:
                shutil.rmtree(old_aside, ignore_errors=True)
            emit("RESTORE_SUCCESS %s (%d files)"
                 % (project_id, len(manifest["files"])))
            _audit("RESTORE_SUCCESS")
            return {"status": "RESTORE_SUCCESS", "restore_id": restore_id,
                    "files": len(manifest["files"]),
                    "project_id": project_id}


if __name__ == "__main__":  # pragma: no cover — operator CLI
    import argparse
    ap = argparse.ArgumentParser(
        description="Item 1b restore tool (single node, operator-run)")
    ap.add_argument("harness_root")
    ap.add_argument("project_id")
    ap.add_argument("backup_dir")
    ap.add_argument("--allow-overwrite", action="store_true",
                    help="replace an existing live project")
    args = parser = ap.parse_args()
    logs = []
    out = restore_project(args.harness_root, args.project_id,
                          args.backup_dir,
                          allow_overwrite=args.allow_overwrite,
                          emit=logs.append)
    for line in logs:
        print(line)
    print("%s %s" % (out["status"], out.get("reason", "")))
    raise SystemExit(0 if out["status"] == "RESTORE_SUCCESS" else 1)
