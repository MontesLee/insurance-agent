"""Client-data protection (Phase 13 R-04).

Round-1 audit measured real client-attribute data written plaintext into
durable state (156 sensitive-term hits in events.jsonl, 312 in
case_state.json), with no retention or deletion story.

Minimal single-node remediation, three layers:

1. EVENT REDACTION — event/log payloads are operational metadata; a
   deny-list filter drops well-known sensitive FIELD NAMES (name/phone/
   email/id/address/income/health...) from any dict before it is written
   to events.jsonl or emitted. Artifacts remain the durable record — in
   the encrypted store, not in the operational log.

2. ENCRYPTION AT REST — CaseState files (case_state.json, artifacts/*.json,
   project.json) are Fernet-encrypted when a data key is configured. Threat
   model: single-node controlled pilot; the boundary is "disk/backup
   theft or accidental copy of the harness root". Key storage: an
   environment variable or a key file OUTSIDE the encrypted tree; never
   in the repository, never beside the data it protects by default.
   Key lifecycle: a generation script; rotating requires re-encrypt.
   Backups: encrypted bytes are copied opaquely — backups never see
   plaintext. Without a key the runtime keeps its documented plaintext
   mode (portfolio/benchmark), clearly reported.

3. RETENTION & DELETION — every project records its finished-at time;
   `delete_project` performs complete, explicit erasure (state, events,
   checkpoints, messages, approvals, control files, lock files) and
   removes the index entry under the R-01 lock.

No KMS, no new dependencies beyond `cryptography` (already installed).
"""
from __future__ import annotations

import base64
import os
import re
from typing import Optional

# ---- 1. event-payload redaction -------------------------------------------- #
# Sensitive FIELD names (values under these keys never enter logs/events).
SENSITIVE_FIELDS = frozenset({
    "name", "full_name", "client_name", "phone", "mobile", "telephone",
    "email", "address", "home_address", "id_number", "identity_number",
    "id_card", "passport", "ssn", "income", "annual_income", "salary",
    "health_status", "health_declaration", "medical_history",
    "diagnosis", "date_of_birth", "birth_date",
    # Phase 17 (T07): financial-account and policy identifiers are
    # sensitive client data — surfaced by the security evaluation
    "bank_card", "card_number", "bank_account", "account_number",
    "policy_number", "policy_no",
})
_SENSITIVE_PATTERN = re.compile(
    r"^(?:name|full_name|client_name|phone|mobile|telephone|email|"
    r"address|home_address|id_number|identity_number|id_card|passport|"
    r"ssn|income|annual_income|salary|health_status|health_declaration|"
    r"medical_history|diagnosis|date_of_birth|birth_date|"
    r"bank_card|card_number|bank_account|account_number|"
    r"policy_number|policy_no)$", re.I)


def redact(value, depth: int = 0):
    """Recursively drop sensitive fields from dicts/lists for LOGS ONLY.

    Artifacts (the durable record) are never passed through this — they go
    to the encrypted store. Returns a new structure; input untouched."""
    if depth > 6:
        return "<max-depth>"
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _SENSITIVE_PATTERN.match(str(k)):
                out[str(k)] = "[REDACTED]"
            else:
                out[str(k)] = redact(v, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v, depth + 1) for v in list(value)[:64]]
    return value


# ---- 2. encryption at rest -------------------------------------------------- #
def load_data_key(explicit: Optional[str] = None) -> Optional[bytes]:
    """Fernet key from (precedence) explicit arg > env var > key file
    INSURANCE_AGENT_KEYFILE (path must be OUTSIDE the harness root).
    Returns None = plaintext mode (documented portfolio/benchmark mode).

    The `cryptography` import is LAZY and only happens when a key is
    actually configured — plaintext mode must run on interpreters that
    don't ship the package (the regression env). A CONFIGURED but
    unusable key still fails closed."""
    raw = explicit
    if raw is None:
        raw = os.environ.get("INSURANCE_AGENT_DATA_KEY")
    if raw is None:
        kf = os.environ.get("INSURANCE_AGENT_KEYFILE")
        if kf and os.path.isfile(kf):
            with open(kf, encoding="utf-8") as f:
                raw = f.read().strip()
    if not raw:
        return None
    from cryptography.fernet import Fernet
    key = raw.encode("utf-8")
    Fernet(key)  # validates; raises on malformed key — fail closed
    return key


def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    from cryptography.fernet import Fernet
    return Fernet(key).encrypt(data)


def decrypt_bytes(token: bytes, key: bytes) -> bytes:
    from cryptography.fernet import Fernet
    return Fernet(key).decrypt(token)


_ENCRYPTED_MAGIC = b"IA1:"


def maybe_encrypt_bytes(data: bytes, key: Optional[bytes]) -> bytes:
    if key is None:
        return data
    return _ENCRYPTED_MAGIC + encrypt_bytes(data, key)


def maybe_decrypt_bytes(data: bytes, key: Optional[bytes]) -> bytes:
    if key is None or not data.startswith(_ENCRYPTED_MAGIC):
        return data  # plaintext mode or legacy plaintext file
    return decrypt_bytes(data[len(_ENCRYPTED_MAGIC):], key)


def write_protected(path: str, text: str, key: Optional[bytes]) -> None:
    """Atomic write of client-data files: encrypted when a key is set,
    plaintext otherwise (documented mode)."""
    from runtime.state.durable import atomic_write_json  # noqa: F401
    data = maybe_encrypt_bytes(text.encode("utf-8"), key)
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    import tempfile as _tf
    fd, tmp = _tf.mkstemp(dir=directory, prefix=".tmp_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        import time as _t
        deadline = _t.time() + 2.0
        while True:
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if _t.time() >= deadline:
                    raise
                _t.sleep(0.05)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_protected(path: str, key: Optional[bytes]) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    return maybe_decrypt_bytes(raw, key).decode("utf-8")


# ---- 3. retention / deletion ------------------------------------------------ #
def delete_project(harness_root: str, project_id: str,
                    key: Optional[bytes] = None) -> dict:
    """Complete, explicit erasure of one project: every durable file under
    <root>/<project_id>/ plus its index entry (under the R-01 lock)."""
    import re as _re
    import shutil
    if not _re.match(r"^[A-Za-z0-9_\-]+$", project_id):
        raise ValueError("invalid project_id")
    from runtime.harness.harness import _index_path
    from runtime.state.durable import locked_update_json
    pdir = os.path.join(harness_root, project_id)
    removed = []
    if os.path.isdir(pdir):
        for root, _dirs, files in os.walk(pdir):
            for f in files:
                removed.append(os.path.relpath(os.path.join(root, f), pdir))
        shutil.rmtree(pdir, ignore_errors=False)
    locked_update_json(
        _index_path(harness_root),
        lambda entries: [e for e in entries
                         if e.get("project_id") != project_id],
        default_factory=list)
    return {"project_id": project_id, "files_deleted": len(removed),
            "index_entry_removed": True}
