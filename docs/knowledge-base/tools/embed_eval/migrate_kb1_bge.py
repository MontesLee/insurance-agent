# -*- coding: utf-8 -*-
"""§6 surgical migration: insurance-kb-v1 embeddings nomic -> BGE-M3.

Chunks/documents/metadata are NEVER touched. Steps:
  1. backup the 791 nomic embedding rows (exact-rollback material)
  2. vector per chunk: copied from the official-pipeline eval-KB vector
     where content matches (704), else freshly embedded through the
     production path (WeKnora-app -> weknora-ollama bge-m3)
  3. single transaction: replace embedding rows + flip
     knowledge_bases.embedding_model_id -> 'bge-m3'
  4. verify counts/dimension/model

Usage: python migrate_kb1_bge.py backup | build | apply | verify
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                      # embed_driver import
from embed_driver import embed                     # noqa: E402

REPO = HERE.parents[3]
KB = HERE.parents[1]
EVID = KB / "evidence" / "eval"
KB1 = "44af9ff2-ecef-445e-87c6-cb1458cd4d44"
EVAL = "e38edd35-3d75-441e-9a76-d7ab1466d590"
MODEL_ROW = "bge-m3"
OLLAMA_MODEL = "bge-m3:latest"

BACKUP = EVID / "reembed_nomic_backup.json"
VECTORS = EVID / "reembed_bge_vectors.json"
SQLFILE = REPO / "tmp" / "kb1_bge_migration.sql"


def psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "-i", "WeKnora-postgres", "psql", "-U",
         "postgres", "-d", "WeKnora", "-v", "ON_ERROR_STOP=1"],
        input=sql.encode("utf-8"), capture_output=True, timeout=600)
    out = r.stdout.decode("utf-8", "replace")
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + r.stderr.decode("utf-8",
                                                             "replace")[:400])
    return out


def dump_kb(kbid: str) -> list:
    """Live chunks: (chunk_id, knowledge_id, doc, chunk_index, content)."""
    out = psql("COPY (SELECT c.id, c.knowledge_id, k2.file_name, "
               "c.chunk_index, c.content FROM chunks c JOIN knowledges k2 "
               "ON c.knowledge_id=k2.id WHERE k2.knowledge_base_id='%s' "
               "AND k2.deleted_at IS NULL ORDER BY k2.file_name, "
               "c.chunk_index) TO STDOUT WITH CSV HEADER" % kbid)
    import csv
    rows = list(csv.reader(out.strip().splitlines()[1:]))
    return [{"chunk_id": r[0], "knowledge_id": r[1], "doc": r[2],
             "idx": int(r[3]), "content": r[4]} for r in rows if len(r) == 5]


def step_backup() -> None:
    out = psql("COPY (SELECT e.chunk_id, e.source_id, e.source_type, "
               "e.knowledge_id, e.dimension, e.embedding::text, "
               "e.is_enabled, e.content FROM embeddings e WHERE "
               "e.knowledge_base_id='%s') TO STDOUT WITH CSV HEADER" % KB1)
    Path(BACKUP).write_text(out, encoding="utf-8")
    n = len(out.strip().splitlines()) - 1
    print("backup rows:", n, "->", BACKUP)
    print("(live 791 + soft-deleted-chunk orphans from Task-1 PDF "
          "re-upload iterations — all preserved in backup; orphans are "
          "inert and removed by the migration DELETE)")
    assert n >= 791, "expected >=791 backup rows, got %d" % n


def step_build() -> None:
    kb1_chunks = dump_kb(KB1)
    assert len(kb1_chunks) == 791, len(kb1_chunks)
    # eval-KB vectors by content md5 (official pipeline output)
    out = psql("COPY (SELECT md5(c.content), e.embedding::text FROM "
               "embeddings e JOIN chunks c ON e.chunk_id=c.id JOIN "
               "knowledges k2 ON c.knowledge_id=k2.id WHERE "
               "k2.knowledge_base_id='%s' AND k2.deleted_at IS NULL) "
               "TO STDOUT WITH CSV HEADER" % EVAL)
    import csv
    eval_vec = {}
    for r in csv.reader(out.strip().splitlines()[1:]):
        if len(r) == 2:
            eval_vec[r[0]] = r[1]

    todo = [c for c in kb1_chunks
            if hashlib.md5(c["content"].encode("utf-8")).hexdigest()
            not in eval_vec]
    print("copy-from-eval: %d | fresh-embed: %d"
          % (791 - len(todo), len(todo)))
    fresh = {}
    if todo:
        t0 = time.time()
        res = embed(OLLAMA_MODEL, [c["content"] for c in todo], batch=8)
        for c, v in zip(todo, res["vectors"]):
            fresh[c["chunk_id"]] = "[" + ",".join(
                repr(float(x)) for x in v) + "]"
        print("embedded %d chunks in %.0fs (dim=%s)"
              % (len(todo), time.time() - t0, len(res["vectors"][0])))
        assert len(res["vectors"][0]) == 1024, "dimension mismatch"

    rows = []
    for c in kb1_chunks:
        md5 = hashlib.md5(c["content"].encode("utf-8")).hexdigest()
        vec = eval_vec.get(md5) or fresh[c["chunk_id"]]
        rows.append({"chunk_id": c["chunk_id"],
                     "knowledge_id": c["knowledge_id"],
                     "content": c["content"], "vector": vec})
    VECTORS.write_text(json.dumps(
        {"built_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows},
        ensure_ascii=False), encoding="utf-8")
    print("vectors ready:", len(rows), "->", VECTORS)


def _sq(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def step_apply() -> None:
    vec = json.loads(VECTORS.read_text(encoding="utf-8"))["rows"]
    assert len(vec) == 791, len(vec)
    L = ["BEGIN;",
         "DELETE FROM embeddings WHERE knowledge_base_id=%s;" % _sq(KB1)]
    for r in vec:
        L.append(
            "INSERT INTO embeddings (source_id, source_type, chunk_id, "
            "knowledge_id, knowledge_base_id, content, dimension, "
            "embedding, is_enabled) VALUES (%s, 0, %s, %s, %s, %s, 1024, "
            "'%s'::halfvec, true);"
            % (_sq(str(uuid.uuid4())), _sq(r["chunk_id"]),
               _sq(r["knowledge_id"]), _sq(KB1), _sq(r["content"]),
               r["vector"]))
    L.append("UPDATE knowledge_bases SET embedding_model_id=%s WHERE "
             "id=%s;" % (_sq(MODEL_ROW), _sq(KB1)))
    L.append("COMMIT;")
    SQLFILE.write_text("\n".join(L), encoding="utf-8")
    print("sql file:", SQLFILE, "(%d lines)" % len(L))
    t0 = time.time()
    out = psql(SQLFILE.read_text(encoding="utf-8"))
    print("applied in %.0fs" % (time.time() - t0))
    print(out.strip().splitlines()[-1] if out.strip() else "(no output)")


def step_verify() -> None:
    out = psql(
        "SELECT (SELECT count(*) FROM knowledges k2 WHERE "
        "k2.knowledge_base_id='%s' AND k2.deleted_at IS NULL), "
        "(SELECT count(*) FROM chunks c JOIN knowledges k2 ON "
        "c.knowledge_id=k2.id WHERE k2.knowledge_base_id='%s' AND "
        "k2.deleted_at IS NULL), "
        "(SELECT count(*) FROM embeddings e WHERE "
        "e.knowledge_base_id='%s'), "
        "(SELECT count(DISTINCT e.dimension) || ':' || "
        "max(e.dimension) FROM embeddings e WHERE "
        "e.knowledge_base_id='%s'), "
        "(SELECT embedding_model_id FROM knowledge_bases WHERE id='%s');"
        % (KB1, KB1, KB1, KB1, KB1))
    print("docs|chunks|embeddings|dims:max|model ->", out.strip())


if __name__ == "__main__":
    {"backup": step_backup, "build": step_build, "apply": step_apply,
     "verify": step_verify}[sys.argv[1]]()
