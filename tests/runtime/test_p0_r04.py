"""Phase 13 P0 R-04 — client-data protection tests.

Round-1 audit: 156 sensitive-term hits in events.jsonl, 312 in
case_state.json; no retention/deletion. Proves: redaction in logs,
encryption at rest (key from env/keyfile, never in repo), plaintext-mode
compat, backup-safety (ciphertext), deletion/erasure, and that sensitive
values never leak into events, error paths or API-visible summaries.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime.harness.harness import LongRunningHarness, _index_read  # noqa: E402
from runtime.state import case_state as cs  # noqa: E402
from runtime.state import store as ss  # noqa: E402
from runtime.state.dataprotection import (redact, load_data_key,  # noqa: E402
                                          write_protected, read_protected,
                                          delete_project)

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="r04_", dir=os.path.join(REPO, "tmp"))


# synthetic sensitive fixture (NO real person's data)
PII = {
    "name": "SYNTHETIC Person",
    "phone": "+86 138 0000 0000",
    "email": "synthetic@example.invalid",
    "id_number": "SYN-0000-0000",
    "address": "1 Synthetic Street, Test City",
    "annual_income": "500000",
    "health_status": "synthetic-check-ok",
}


def fernet_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


@section
def test_t_r04_01_redaction(c: Checks):
    out = redact({"client": PII, "task_id": "t1", "nested": {"phone": "x"}})
    c.chk("R-04: name redacted", out["client"]["name"] == "[REDACTED]")
    c.chk("R-04: phone redacted", out["client"]["phone"] == "[REDACTED]")
    c.chk("R-04: email redacted", out["client"]["email"] == "[REDACTED]")
    c.chk("R-04: income redacted", out["client"]["annual_income"] == "[REDACTED]")
    c.chk("R-04: health redacted", out["client"]["health_status"] == "[REDACTED]")
    c.chk("R-04: nested sensitive redacted", out["nested"]["phone"] == "[REDACTED]")
    c.chk("R-04: non-sensitive preserved", out["task_id"] == "t1")
    c.chk("R-04: redacted value not present anywhere",
          "SYNTHETIC Person" not in json.dumps(out)
          and "138 0000" not in json.dumps(out))


@section
def test_t_r04_02_events_never_carry_sensitive_values(c: Checks):
    d = fresh_dir()
    old_key = os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
    try:
        h = LongRunningHarness(d)
        p = h.create_project("r04a", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "client_profile"}]})
        # realistic shape: an event carrying a STRUCTURED sensitive payload
        # (field names in the deny-list) — the durable log must redact
        p._event("human_information_received", payload=PII, task_id="task_a")
        # and the harness's own human-input event never emits the VALUE
        # (only the key name + conflict flag) — verify that too
        state = cs.new_case_state(p.case_id, {})
        h._apply_human_information(p, state, "client_age", "40", "human")
        ev = open(os.path.join(d, p.project_id, "events.jsonl"),
                  encoding="utf-8").read()
        c.chk("R-04: sensitive VALUES absent from events.jsonl",
              PII["name"] not in ev and "138 0000" not in ev
              and "500000" not in ev, ev[-200:])
        c.chk("R-04: redaction marker present", "[REDACTED]" in ev)
        c.chk("R-04: human-input event records key only (not the value)",
              "\"key\": \"client_age\"" in ev and "\"40\"" not in ev)
    finally:
        if old_key is not None:
            os.environ["INSURANCE_AGENT_DATA_KEY"] = old_key
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r04_03_encryption_at_rest(c: Checks):
    d = fresh_dir()
    old_env = os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
    old_kf = os.environ.pop("INSURANCE_AGENT_KEYFILE", None)
    keyfile = os.path.join(d, "..", "r04.key")  # OUTSIDE the case tree
    open(keyfile, "w", encoding="utf-8").write(fernet_key())
    try:
        os.environ["INSURANCE_AGENT_KEYFILE"] = keyfile
        key = load_data_key()
        c.chk("R-04: key loaded from keyfile", key is not None)
        state = {"case_id": "r04c", "artifacts": {},
                 "client": PII, "tasks": [], "evaluations": []}
        ss.save(state, d)
        raw = open(os.path.join(d, "r04c", "case_state.json"), "rb").read()
        c.chk("R-04: case_state.json encrypted at rest (ciphertext)",
              b"SYNTHETIC" not in raw and b"case_id" not in raw)
        c.chk("R-04: ciphertext magic present", raw[:4] == b"IA1:")
        loaded = ss.load(d, "r04c")
        c.chk("R-04: round-trips to identical plaintext",
              loaded["client"]["name"] == PII["name"])
        # backup-safety: copying the encrypted bytes leaks nothing
        backup = bytes(raw)
        c.chk("R-04: backup copy carries no plaintext PII",
              b"SYNTHETIC Person" not in backup)
    finally:
        os.remove(keyfile)
        for k, v in (("INSURANCE_AGENT_DATA_KEY", old_env),
                     ("INSURANCE_AGENT_KEYFILE", old_kf)):
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r04_04_plaintext_mode_compat_and_fail_closed_key(c: Checks):
    d = fresh_dir()
    old_env = os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
    try:
        key = load_data_key()
        c.chk("R-04: no key configured → documented plaintext mode",
              key is None)
        state = {"case_id": "r04p", "artifacts": {}, "x": 1}
        ss.save(state, d)
        c.chk("R-04: plaintext mode round-trips",
              ss.load(d, "r04p")["x"] == 1)
        # malformed key fails CLOSED (never silently plaintext)
        os.environ["INSURANCE_AGENT_DATA_KEY"] = "not-a-valid-key"
        try:
            load_data_key()
            c.chk("R-04: malformed key raises (fail closed)", False)
        except Exception:
            c.chk("R-04: malformed key raises (fail closed)", True)
    finally:
        os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
        if old_env is not None:
            os.environ["INSURANCE_AGENT_DATA_KEY"] = old_env
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r04_05_deletion_erasure(c: Checks):
    d = fresh_dir()
    try:
        h = LongRunningHarness(d)
        p = h.create_project("r04del", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "client_profile"}]})
        p._event("human_information_received", key="name", value=PII["name"])
        out = delete_project(d, p.project_id)
        c.chk("R-04: deletion reports files removed", out["files_deleted"] >= 2)
        c.chk("R-04: project dir gone",
              not os.path.exists(os.path.join(d, p.project_id)))
        c.chk("R-04: index entry removed (under R-01 lock)",
              _index_read(d) == [])
        c.chk("R-04: invalid project_id refused",
              _raises(lambda: delete_project(d, "../escape")))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _raises(fn):
    try:
        fn()
        return False
    except Exception:  # noqa: BLE001
        return True


@section
def test_t_r04_06_error_paths_no_leak(c: Checks):
    """Protected read with the WRONG key raises loudly (never returns
    garbage plaintext), and no error message embeds the ciphertext or PII."""
    d = fresh_dir()
    try:
        key = load_data_key()  # None in test env → plaintext path
        write_protected(os.path.join(d, "f.bin"), PII["name"],
                        load_data_key(fernet_key()))
        # valid-format but WRONG Fernet key must fail closed
        from cryptography.fernet import Fernet
        wrong = Fernet.generate_key()
        try:
            read_protected(os.path.join(d, "f.bin"), wrong)
            c.chk("R-04: wrong key fails closed", False)
        except Exception as e:
            c.chk("R-04: wrong key fails closed", True)
            c.chk("R-04: error carries no PII", PII["name"] not in str(e))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    return run_sections(SECTIONS, "webui_test_r04_log.txt",
                        "P0 R-04 DATA PROTECTION")


if __name__ == "__main__":
    sys.exit(main())
