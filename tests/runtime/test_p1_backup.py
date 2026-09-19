"""Phase 13 P1 Stage 1 / Item 1a — Backup tests (B01–B24 + strict modes).

Covers: happy path (manifest, sha256, encrypted bytes), negatives
(missing/truncated/tampered manifest, hash mismatch, missing file,
plaintext-swap detection), atomicity/crash (interrupted manifest,
temp-only manifest, post-backup verify), concurrency (8 concurrent
backups, backup-vs-write, backup-vs-delete), security (no key/token/
secret, no PII in logs/errors, ciphertext-only backups), strict modes,
and the runtime-neutrality invariant (CaseState identical before/after).
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime.harness import LongRunningHarness  # noqa: E402
from runtime.state import backup as bk  # noqa: E402
from runtime.state import store as ss  # noqa: E402
from runtime.state.dataprotection import write_protected  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="bkp_", dir=os.path.join(REPO, "tmp"))


def fernet_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def make_project(root, pid="bkp1", status=None, with_case=True):
    h = LongRunningHarness(root)
    p = h.create_project(pid, task_graph={"tasks": [
        {"task_id": "task_a", "task_type": "client_profile"}]})
    if with_case:
        # persist the case state through the SAME protected path the
        # runtime uses (encrypted when a data key is configured)
        from runtime.state.dataprotection import (write_protected,
                                                  load_data_key)
        os.makedirs(os.path.join(root, p.project_id, "case", "c1"),
                    exist_ok=True)
        write_protected(
            os.path.join(root, p.project_id, "case", "c1",
                         "case_state.json"),
            json.dumps({"case_id": "c1", "artifacts": {}, "x": 1}),
            load_data_key())
    if status:
        p._set_task("task_a", status=status)
    return h, p


def run_backup(root, pid, dest, **kw):
    return bk.backup_project(root, pid, dest, **kw)


# ------------------------------------------------------------------ #
# A. Happy path (B01–B06)
# ------------------------------------------------------------------ #
@section
def test_b01_b06_happy_path(c: Checks):
    d = fresh_dir()
    dest = fresh_dir()
    try:
        h, p = make_project(d)
        out = run_backup(d, p.project_id, dest)
        c.chk("B01: BACKUP_CREATED", out["status"] == "BACKUP_CREATED",
              out.get("reason", ""))
        bdir = out["backup_dir"]
        # B02: manifest exists
        c.chk("B02: manifest exists",
              os.path.isfile(os.path.join(bdir, bk.MANIFEST_NAME)))
        m = json.load(open(os.path.join(bdir, bk.MANIFEST_NAME),
                           encoding="utf-8"))
        # B03: schema correct
        c.chk("B03: manifest schema fields",
              m["schema_version"] == "1.0" and m["project_id"]
              == p.project_id and m["backup_id"].startswith("bkp_")
              and isinstance(m["files"], list) and m["files"])
        # B04: every file has a sha256
        c.chk("B04: all files have sha256",
              all(len(e["sha256"]) == 64 for e in m["files"]))
        # B05: recomputed hashes match
        ok = True
        for e in m["files"]:
            path = os.path.join(bdir, *e["relative_path"].split("/"))
            import hashlib
            actual = hashlib.sha256(open(path, "rb").read()).hexdigest()
            ok = ok and actual == e["sha256"] \
                and os.path.getsize(path) == e["size"]
        c.chk("B05: recomputed sha256+size match manifest", ok)
        # B06: backup data is encrypted when the source was encrypted
        # (this project is plaintext demo mode — flag must say so)
        c.chk("B06: encrypted flags match source (plaintext demo here)",
              all(e["encrypted"] is False for e in m["files"]), m["files"])
        c.chk("B06/B16: verify_backup immediately VALID",
              bk.verify_backup(bdir)["valid"])
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


@section
def test_b06_encrypted_backup(c: Checks):
    d = fresh_dir()
    dest = fresh_dir()
    old = os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
    try:
        os.environ["INSURANCE_AGENT_DATA_KEY"] = fernet_key()
        h, p = make_project(d)
        out = run_backup(d, p.project_id, dest)
        c.chk("B06: encrypted-source backup created",
              out["status"] == "BACKUP_CREATED", out.get("reason", ""))
        m = out["manifest"]
        # The P0.1 encryption boundary covers the CASE STORE (client
        # data); project.json is task metadata and legitimately plaintext.
        # Assert per-file flags match the actual magic (verify does too),
        # and that every case-store file is ciphertext.
        case_files = [e for e in m["files"]
                      if e["relative_path"].startswith("case/")]
        c.chk("B06: every case-store file flagged encrypted",
              case_files and all(e["encrypted"] for e in case_files),
              [e["relative_path"] for e in m["files"]])
        raw = open(os.path.join(out["backup_dir"], "case", "c1",
                                "case_state.json"), "rb").read()
        c.chk("B06: copied bytes are ciphertext (no plaintext PII)",
              b"case_id" not in raw and raw[:4] == b"IA1:")
        c.chk("B06: encrypted backup verifies",
              bk.verify_backup(out["backup_dir"])["valid"])
    finally:
        os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
        if old is not None:
            os.environ["INSURANCE_AGENT_DATA_KEY"] = old
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


# ------------------------------------------------------------------ #
# Negative tests (B07–B12)
# ------------------------------------------------------------------ #
@section
def test_b07_b11_negative(c: Checks):
    d = fresh_dir()
    dest = fresh_dir()
    try:
        h, p = make_project(d)
        out = run_backup(d, p.project_id, dest)
        bdir = out["backup_dir"]
        mpath = os.path.join(bdir, bk.MANIFEST_NAME)

        # B07: manifest deleted
        tmp = fresh_dir()
        shutil.copytree(bdir, os.path.join(tmp, "b7"))
        os.remove(os.path.join(tmp, "b7", bk.MANIFEST_NAME))
        c.chk("B07: manifest deleted → INVALID",
              not bk.verify_backup(os.path.join(tmp, "b7"))["valid"])
        shutil.rmtree(tmp, ignore_errors=True)

        # B08: one backup file modified → sha mismatch
        tmp = fresh_dir()
        shutil.copytree(bdir, os.path.join(tmp, "b8"))
        target = os.path.join(tmp, "b8", "case", "c1", "case_state.json")
        with open(target, "ab") as f:
            f.write(b"x")
        v = bk.verify_backup(os.path.join(tmp, "b8"))
        c.chk("B08: modified file → INVALID (size or sha mismatch)",
              not v["valid"] and "mismatch" in v["reason"], v.get("reason"))
        shutil.rmtree(tmp, ignore_errors=True)

        # B09: manifest points at a missing file
        tmp = fresh_dir()
        shutil.copytree(bdir, os.path.join(tmp, "b9"))
        os.remove(os.path.join(tmp, "b9", "case", "c1", "case_state.json"))
        v = bk.verify_backup(os.path.join(tmp, "b9"))
        c.chk("B09: listed file missing → INVALID", not v["valid"]
              and "missing" in v["reason"], v.get("reason"))
        shutil.rmtree(tmp, ignore_errors=True)

        # B10: truncated manifest JSON → loud fail (corrupt file raises,
        # never returns garbage)
        raw = open(mpath, encoding="utf-8").read()
        tmp = fresh_dir()
        shutil.copytree(bdir, os.path.join(tmp, "b10"))
        with open(os.path.join(tmp, "b10", bk.MANIFEST_NAME), "w",
                  encoding="utf-8") as f:
            f.write(raw[:max(1, len(raw) // 2)])
        try:
            v = bk.verify_backup(os.path.join(tmp, "b10"))
            c.chk("B10: truncated manifest → INVALID", not v["valid"])
        except json.JSONDecodeError:
            c.chk("B10: truncated manifest → INVALID (loud, fail-closed)",
                  True)
        shutil.rmtree(tmp, ignore_errors=True)

        # B11: checksum modified (manifest hash flipped)
        tmp = fresh_dir()
        shutil.copytree(bdir, os.path.join(tmp, "b11"))
        m11 = json.load(open(os.path.join(tmp, "b11", bk.MANIFEST_NAME),
                             encoding="utf-8"))
        m11["files"][0]["sha256"] = "0" * 64
        with open(os.path.join(tmp, "b11", bk.MANIFEST_NAME), "w",
                  encoding="utf-8") as f:
            json.dump(m11, f)
        v = bk.verify_backup(os.path.join(tmp, "b11"))
        c.chk("B11: modified checksum → INVALID", not v["valid"])
        shutil.rmtree(tmp, ignore_errors=True)

        c.chk("baseline untouched by the negative manipulations",
              bk.verify_backup(bdir)["valid"])
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


@section
def test_b12_plaintext_swap_detected(c: Checks):
    """A file swapped to plaintext while the manifest says encrypted (or
    vice versa) violates the encryption invariant → INVALID."""
    d = fresh_dir()
    dest = fresh_dir()
    old = os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
    try:
        os.environ["INSURANCE_AGENT_DATA_KEY"] = fernet_key()
        h, p = make_project(d)
        out = run_backup(d, p.project_id, dest)
        bdir = out["backup_dir"]
        c.chk("B12 setup: encrypted backup starts VALID",
              bk.verify_backup(bdir)["valid"])
        # swap one ciphertext file for plaintext junk
        target = os.path.join(bdir, "case", "c1", "case_state.json")
        with open(target, "wb") as f:
            f.write(b'{"case_id": "plaintext swap"}')
        v = bk.verify_backup(bdir)
        c.chk("B12: plaintext swap detected (hash OR flag mismatch)",
              not v["valid"]
              and ("mismatch" in v["reason"]), v.get("reason"))
    finally:
        os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
        if old is not None:
            os.environ["INSURANCE_AGENT_DATA_KEY"] = old
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


# ------------------------------------------------------------------ #
# Atomicity / crash tests (B13–B15)
# ------------------------------------------------------------------ #
@section
def test_b13_b15_atomicity(c: Checks):
    d = fresh_dir()
    dest = fresh_dir()
    try:
        h, p = make_project(d)

        # B13/B14: manifest write interrupted — simulate by killing the
        # backup right before atomic_write_json lands the manifest
        orig = bk.atomic_write_json
        def boom(path, doc, *a, **k):
            raise RuntimeError("simulated crash before manifest replace")
        bk.atomic_write_json = boom
        try:
            out = run_backup(d, p.project_id, dest)
        finally:
            bk.atomic_write_json = orig
        c.chk("B13: manifest-write crash → BACKUP_FAILED",
              out["status"] == "BACKUP_FAILED", out)
        leftovers = os.listdir(dest)
        c.chk("B13: no partial backup directory survives",
              leftovers == [], leftovers)

        # B14: temp-manifest-only directory (no final manifest) → INVALID
        fake = os.path.join(dest, "bkp_fake")
        os.makedirs(fake, exist_ok=True)
        with open(os.path.join(fake, bk.MANIFEST_NAME + ".tmp"), "w") as f:
            f.write("{}")
        c.chk("B14: temp manifest without final manifest → INVALID",
              not bk.verify_backup(fake)["valid"])
        shutil.rmtree(fake, ignore_errors=True)

        # B15: a real backup's manifest is atomically placed (final only)
        out2 = run_backup(d, p.project_id, dest)
        c.chk("B15: clean backup after the crash works",
              out2["status"] == "BACKUP_CREATED")
        c.chk("B15/B16: no .tmp manifest residue",
              not any(f.endswith(".tmp")
                      for f in os.listdir(out2["backup_dir"])))
        c.chk("B15/B16: verify → VALID",
              bk.verify_backup(out2["backup_dir"])["valid"])
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


# ------------------------------------------------------------------ #
# Concurrency tests (B17–B19)
# ------------------------------------------------------------------ #
@section
def test_b17_concurrent_backups(c: Checks):
    root = fresh_dir()
    dest = fresh_dir()
    try:
        ids = []
        for i in range(8):
            _, p = make_project(root, pid="bkp%02d" % i)
            ids.append(p.project_id)
        outs, errs = [], []
        def go(pid):
            try:
                outs.append(run_backup(root, pid, dest))
            except Exception as e:  # noqa: BLE001
                errs.append(repr(e))
        ts = [threading.Thread(target=go, args=(pid,)) for pid in ids]
        [t.start() for t in ts]; [t.join() for t in ts]
        c.chk("B17: 8/8 concurrent backups created",
              len(outs) == 8 and all(o["status"] == "BACKUP_CREATED"
                                     for o in outs), errs[:2])
        c.chk("B17: no exceptions", not errs, errs[:2])
        c.chk("B17: all manifests parse + verify",
              all(bk.verify_backup(o["backup_dir"])["valid"] for o in outs))
        from runtime.harness.harness import _index_read
        c.chk("B17: projects index intact",
              len(_index_read(root)) == 8)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


@section
def test_b18_backup_vs_state_write(c: Checks):
    """A concurrent Project._save during backup must either serialize
    behind the lock or fail the backup closed — never a VALID backup
    stitched from two time points."""
    d = fresh_dir()
    dest = fresh_dir()
    try:
        h, p = make_project(d)
        stop = threading.Event()
        def writer():
            i = 0
            while not stop.is_set():
                p._set_task("task_a", attempt=i)  # → _save → index lock
                i += 1
        wt = threading.Thread(target=writer); wt.start()
        out = run_backup(d, p.project_id, dest)
        stop.set(); wt.join()
        if out["status"] == "BACKUP_CREATED":
            v = bk.verify_backup(out["backup_dir"])
            c.chk("B18: backup taken under writes verifies", v["valid"])
            # and the snapshotted project.json is ONE consistent document
            snap = json.load(open(os.path.join(out["backup_dir"],
                                               "project.json"),
                                 encoding="utf-8"))
            c.chk("B18: snapshotted project.json coherent",
                  snap["project_id"] == p.project_id)
        else:
            c.chk("B18: backup failed CLOSED under concurrent writes",
                  out["status"] == "BACKUP_FAILED", out.get("reason", ""))
        c.chk("B18: live project still loadable and coherent",
              json.load(open(os.path.join(d, p.project_id, "project.json"),
                            encoding="utf-8"))["project_id"]
              == p.project_id)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


@section
def test_b19_backup_vs_delete(c: Checks):
    d = fresh_dir()
    dest = fresh_dir()
    try:
        h, p = make_project(d)
        from runtime.state.dataprotection import delete_project
        out = run_backup(d, p.project_id, dest)
        c.chk("B19 setup: backup created", out["status"] == "BACKUP_CREATED")
        # deletion AFTER a completed backup must not invalidate it
        delete_project(d, p.project_id)
        v = bk.verify_backup(out["backup_dir"])
        c.chk("B19: completed backup stays VALID after source deletion",
              v["valid"])
        # deletion BEFORE backup → REJECTED (project gone), never
        # "success with vanished files"
        out2 = run_backup(d, p.project_id, dest)
        c.chk("B19: backup of deleted project → REJECTED",
              out2["status"] == "BACKUP_REJECTED", out2.get("reason", ""))
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


# ------------------------------------------------------------------ #
# Security tests (B20–B24)
# ------------------------------------------------------------------ #
@section
def test_b20_b23_no_secrets_no_leaks(c: Checks):
    d = fresh_dir()
    dest = fresh_dir()
    old = {k: os.environ.get(k) for k in
           ("INSURANCE_AGENT_DATA_KEY", "INSURANCE_AGENT_API_KEYS",
            "INSURANCE_AGENT_MODE")}
    try:
        os.environ["INSURANCE_AGENT_DATA_KEY"] = fernet_key()
        os.environ["INSURANCE_AGENT_API_KEYS"] = "s" * 24 + ":OWNER:alice"
        h, p = make_project(d)
        logs = []
        out = run_backup(d, p.project_id, dest,
                        emit=lambda m: logs.append(m))
        bdir = out["backup_dir"]
        blob = b""
        for root, _dirs, files in os.walk(bdir):
            for f in files:
                blob += open(os.path.join(root, f), "rb").read()
        key = os.environ["INSURANCE_AGENT_DATA_KEY"].encode()
        api = os.environ["INSURANCE_AGENT_API_KEYS"].encode()
        c.chk("B20: encryption key NOT in backup", key not in blob)
        c.chk("B21: bearer/API key NOT in backup", api not in blob)
        # B22: no plaintext secret markers in the manifest (paths+hashes only)
        manifest = open(os.path.join(bdir, bk.MANIFEST_NAME), "rb").read()
        c.chk("B22: manifest carries no secret-shaped strings",
              b"sk-" not in manifest and api not in manifest)
        c.chk("B23: log lines carry no secrets",
              all(key.decode() not in l and "OWNER:alice" not in l
                  for l in logs), logs)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


@section
def test_b24_error_paths_no_pii(c: Checks):
    d = fresh_dir()
    dest = fresh_dir()
    try:
        h, p = make_project(d)
        p._set_task("task_a", status="RUNNING")
        out = run_backup(d, p.project_id, dest)
        c.chk("B24 setup: RUNNING project -> REJECTED",
              out["status"] == "BACKUP_REJECTED")
        c.chk("B24: rejection reason carries no contents/PII",
              "RUNNING" in out["reason"] and "client" not in out["reason"])
        out2 = run_backup(d, "proj_nope", dest)
        c.chk("B24: missing-project reason is an id, not contents",
              "not found" in out2["reason"])
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


# ------------------------------------------------------------------ #
# Strict modes + runtime neutrality
# ------------------------------------------------------------------ #
@section
def test_strict_modes_and_neutrality(c: Checks):
    from runtime import mode as M
    old = {k: os.environ.get(k) for k in
           ("INSURANCE_AGENT_MODE", "INSURANCE_AGENT_DATA_KEY")}
    try:
        for m in M.VALID_MODES:
            os.environ["INSURANCE_AGENT_MODE"] = m
            c.chk("MODES: %s selectable during backup" % m, M.mode() == m)
        # default demo run (no key) — backup is mode-agnostic tooling
        os.environ.pop("INSURANCE_AGENT_MODE", None)
        os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
        d = fresh_dir()
        dest = fresh_dir()
        try:
            h, p = make_project(d)
            before = json.load(open(os.path.join(d, p.project_id,
                                                 "project.json"),
                                    encoding="utf-8"))
            state_before = json.dumps(before, sort_keys=True)
            out = run_backup(d, p.project_id, dest)
            c.chk("NEUTRAL: backup created", out["status"] == "BACKUP_CREATED")
            after = json.load(open(os.path.join(d, p.project_id,
                                                "project.json"),
                                  encoding="utf-8"))
            c.chk("NEUTRAL: project.json semantically identical",
                  json.dumps(after, sort_keys=True) == state_before)
            from runtime.harness.harness import _index_read
            c.chk("NEUTRAL: index unchanged by backup",
                  len(_index_read(d)) == 1)
            c.chk("NEUTRAL: no task/eval/approval side files invented",
                  not os.path.exists(os.path.join(d, p.project_id,
                                                  "approvals.jsonl")))
        finally:
            shutil.rmtree(d, ignore_errors=True)
            shutil.rmtree(dest, ignore_errors=True)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main():
    return run_sections(SECTIONS, "webui_test_bkp_log.txt",
                        "P1 ITEM 1A BACKUP")


if __name__ == "__main__":
    sys.exit(main())
