# R-04 Data-Protection Verification (Phase 13 P0 Remediation)

Verified by `tests/runtime/test_p0_r04.py`. Threat model: single-node
controlled pilot; the boundary is "disk/backup theft or accidental copy
of the harness root".

## 1. Event/log redaction (always on)

`redact()` drops deny-listed FIELD names (name/phone/email/id/address/
income/health…) from every dict appended to `events.jsonl` /
`checkpoints.jsonl` / `approvals.jsonl` etc. Verified: synthetic PII
values (name, phone, income) never appear in events.jsonl; the harness's
own human-input event records the KEY only, never the value. Artifacts
remain the durable record — stored in the (encryptable) case store, not
the operational log. Limitation, stated: field-NAME-based — a sensitive
value smuggled under an innocuous key in free text is not classified
(content scanning is heuristic and out of minimal scope).

## 2. Encryption at rest (opt-in via key)

- Key source precedence: explicit arg > `INSURANCE_AGENT_DATA_KEY` env >
  `INSURANCE_AGENT_KEYFILE` (path must be OUTSIDE the harness root —
  verified keyfile-outside-tree usage; the key never ships in the repo).
- Boundary: CaseState `case_state.json` + `artifacts/*.json` (the client
  data). Ciphertext carries an `IA1:` magic; readers transparently handle
  legacy plaintext (documented migration: re-save re-encrypts).
- Key lifecycle: owner generates (Fernet), stores outside the tree,
  rotates by re-encrypting. Malformed key FAILS CLOSED (raises; never
  silently degrades to plaintext) — verified.
- Backup behavior: backups copy ciphertext only (verified — a copied
  encrypted file contains no PII).
- The `cryptography` import is lazy: plaintext mode (no key) runs on
  interpreters without the package — this kept the workbuddy regression
  python green (see remediation report §"issue found & fixed").
- Verified round-trip: save → ciphertext on disk → load → identical
  plaintext.

## 3. Retention & deletion

`delete_project(harness_root, project_id)` performs complete explicit
erasure: every file under the project dir + the index entry (removed
under the R-01 lock). Verified: dir gone, index empty, path-traversal
project ids refused. Retention policy: project dirs record timestamps;
enforcement of a max-age purge is a P1 (the erasure primitive it needs
now exists and is tested).

## 4. What remains P1 (deliberately not in this round)

- Field-level classification of artifact contents (vs. log redaction).
- Automated retention sweep. -  Erasure audit log.
- Provider-side deletion (covered by R-05's operator procedure).
