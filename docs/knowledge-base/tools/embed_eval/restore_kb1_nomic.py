# -*- coding: utf-8 -*-
"""Restore insurance-kb-v1 embeddings to the backed-up nomic state
(EXACT-ROLLBACK for the kb-v1 dataset itself; NOT needed for production
rollback, which is the runtime env KB-id revert to insurance-pilot-2).

Reads evidence/eval/reembed_nomic_backup.json (8419 rows: 791 live +
orphans) and generates + applies the restore transaction:
  DELETE bge rows -> INSERT nomic rows (original source_ids, dims)
  -> knowledge_bases.embedding_model_id = 'builtin-embedding-local'

Usage: python restore_kb1_nomic.py generate | apply
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
KB = HERE.parents[1]
EVID = KB / "evidence" / "eval"
KB1 = "44af9ff2-ecef-445e-87c6-cb1458cd4d44"
BACKUP = EVID / "reembed_nomic_backup.json"
SQLFILE = REPO / "tmp" / "kb1_nomic_restore.sql"


def _sq(s):
    return "'" + str(s).replace("'", "''") + "'"


def generate() -> None:
    lines = BACKUP.read_text(encoding="utf-8").strip().splitlines()
    rows = list(csv.reader(lines[1:]))
    L = ["BEGIN;",
         "DELETE FROM embeddings WHERE knowledge_base_id=%s;" % _sq(KB1)]
    for r in rows:
        # chunk_id, source_id, source_type, knowledge_id, dimension,
        # embedding_text, is_enabled, content
        L.append(
            "INSERT INTO embeddings (source_id, source_type, chunk_id, "
            "knowledge_id, knowledge_base_id, content, dimension, "
            "embedding, is_enabled) VALUES (%s, %s, %s, %s, %s, %s, %s, "
            "'%s'::halfvec, %s);"
            % (_sq(r[1]), r[2], _sq(r[0]), _sq(r[3]), _sq(KB1),
               _sq(r[7]), r[4], r[5], "true" if r[6] == "t" else "false"))
    L.append("UPDATE knowledge_bases SET embedding_model_id="
             "'builtin-embedding-local' WHERE id=%s;" % _sq(KB1))
    L.append("COMMIT;")
    SQLFILE.write_text("\n".join(L), encoding="utf-8")
    print("restore sql:", SQLFILE, "(%d rows)" % len(rows))


def apply() -> None:
    r = subprocess.run(
        ["docker", "exec", "-i", "WeKnora-postgres", "psql", "-U",
         "postgres", "-d", "WeKnora", "-v", "ON_ERROR_STOP=1"],
        input=SQLFILE.read_bytes(), capture_output=True, timeout=600)
    print(r.stdout.decode("utf-8", "replace").strip()[-200:])
    if r.returncode != 0:
        print("FAILED:", r.stderr.decode("utf-8", "replace")[:300])


if __name__ == "__main__":
    {"generate": generate, "apply": apply}[sys.argv[1]]()
