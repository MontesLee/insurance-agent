# -*- coding: utf-8 -*-
"""§6: full BGE-M3 re-embedding of insurance-kb-v1.

Sequence (single variable = embedding model):
  1. pre-snapshot live chunks via SQL (doc, chunk_index, content)
  2. PUT /initialization/config/{kbid}  embeddingModelId=bge-m3
     (llmModelId + documentSplitting preserved VERBATIM)
  3. POST /knowledge/batch-reparse  (all 29 knowledge ids)
  4. poll until all 29 docs re-parsed (status completed, chunk counts
     stable across two polls)
  5. post-snapshot + verification (docs=29, chunks=791, embeddings=791,
     dim=1024, content multiset identical to pre-snapshot)

Usage: python reembed_kb1.py snap | config | reparse | verify
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
KB = HERE.parents[1]
EVID = KB / "evidence" / "eval"
BASE = "http://127.0.0.1:8080"
TENANT = "10001"
KBID = "44af9ff2-ecef-445e-87c6-cb1458cd4d44"
EMBED = "bge-m3"
LLM = "685eb417-ddb0-4dd6-ab29-5353f841cbaa"
SPLIT = {"chunkSize": 512, "chunkOverlap": 80, "separators": None}

PRE = EVID / "reembed_pre_chunks.json"
POST = EVID / "reembed_post_chunks.json"


def H(jwt):
    return {"Authorization": "Bearer " + jwt, "X-Tenant-ID": TENANT,
            "Content-Type": "application/json"}


def jwt() -> str:
    return (REPO / "tmp" / "weknora-admin.jwt").read_text(
        encoding="utf-8").strip()


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body \
        is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=H(jwt()),
                                 method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def sql_snap(path: Path) -> dict:
    q = ("COPY (SELECT k2.file_name AS doc, c.chunk_index, c.content FROM "
         "chunks c JOIN knowledges k2 ON c.knowledge_id=k2.id "
         "WHERE k2.knowledge_base_id='%s' AND k2.deleted_at IS NULL "
         "ORDER BY k2.file_name, c.chunk_index) TO STDOUT WITH CSV HEADER"
         % KBID)
    r = subprocess.run(["docker", "exec", "WeKnora-postgres", "psql",
                        "-U", "postgres", "-d", "WeKnora", "-c", q],
                       capture_output=True, timeout=120,
                       encoding="utf-8", errors="replace")
    lines = r.stdout.strip().splitlines()
    header, rows = lines[0], lines[1:]
    docs = {}
    import csv
    for row in csv.reader(rows):
        if len(row) >= 3:
            docs.setdefault(row[0], []).append(row[2])
    snap = {"taken_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "docs": len(docs),
            "chunks": sum(len(v) for v in docs.values()),
            "content": {d: v for d, v in docs.items()}}
    path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return snap


def verify():
    r = subprocess.run(
        ["docker", "exec", "WeKnora-postgres", "psql", "-U", "postgres",
         "-d", "WeKnora", "-t", "-A", "-F", "|", "-c",
         "SELECT (SELECT count(*) FROM knowledges k2 WHERE "
         "k2.knowledge_base_id='%s' AND k2.deleted_at IS NULL), "
         "(SELECT count(*) FROM chunks c JOIN knowledges k2 ON "
         "c.knowledge_id=k2.id WHERE k2.knowledge_base_id='%s' AND "
         "k2.deleted_at IS NULL), "
         "(SELECT count(*) FROM embeddings e JOIN chunks c ON "
         "e.chunk_id=c.id JOIN knowledges k2 ON c.knowledge_id=k2.id "
         "WHERE k2.knowledge_base_id='%s' AND k2.deleted_at IS NULL), "
         "(SELECT embedding_model_id FROM knowledge_bases WHERE id='%s')"
         % (KBID, KBID, KBID, KBID)],
        capture_output=True, timeout=120,
        encoding="utf-8", errors="replace")
    print("docs|chunks|embeddings|model:", r.stdout.strip())
    return r.stdout.strip()


def main() -> int:
    step = sys.argv[1]
    if step == "snap":
        s = sql_snap(PRE)
        print("PRE:", s["docs"], "docs", s["chunks"], "chunks")
    elif step == "config":
        cur = api("GET", "/api/v1/initialization/config/" + KBID)
        print("current:", json.dumps(cur.get("data") or cur,
                                     ensure_ascii=False)[:200])
        put = api("PUT", "/api/v1/initialization/config/" + KBID,
                  {"embeddingModelId": EMBED, "llmModelId": LLM,
                   "documentSplitting": SPLIT})
        print("PUT ->", json.dumps(put, ensure_ascii=False)[:200])
        after = api("GET", "/api/v1/initialization/config/" + KBID)
        d = after.get("data") or after
        print("after embedding modelName:",
              (d.get("embedding") or {}).get("modelName"))
    elif step == "reparse":
        lst = api("GET", "/api/v1/knowledge-bases/%s/knowledge?limit=100"
                  % KBID)
        docs = (lst.get("data") or {}).get("contents") \
            or lst.get("data") or []
        ids = [d["id"] for d in docs]
        print("docs to reparse:", len(ids))
        out = api("POST", "/api/v1/knowledge/batch-reparse",
                  {"kb_id": KBID, "ids": ids, "process_config": {}})
        print("batch-reparse ->",
              json.dumps(out, ensure_ascii=False)[:300])
    elif step == "poll":
        stable = 0
        last = None
        for i in range(120):
            time.sleep(30)
            lst = api("GET", "/api/v1/knowledge-bases/%s/knowledge?limit=100"
                      % KBID)
            docs = (lst.get("data") or {}).get("contents") \
                or lst.get("data") or []
            st = {}
            for d in docs:
                st[d.get("status") or "?"] = st.get(d.get("status")
                                                    or "?", 0) + 1
            cur = (len(docs), json.dumps(st, sort_keys=True))
            n = verify()
            print("[%2d] %d docs %s | %s" % (i, cur[0], cur[1], n),
                  flush=True)
            if cur == last and cur[0] == 29 \
                    and "completed" in st and len(st) == 1:
                stable += 1
                if stable >= 2:
                    print("STABLE — reparse finished")
                    return 0
            else:
                stable = 0
            last = cur
        print("TIMEOUT waiting for stable reparse")
        return 1
    elif step == "verify":
        pre = json.loads(PRE.read_text(encoding="utf-8"))
        post = sql_snap(POST)
        print("PRE %d docs %d chunks | POST %d docs %d chunks"
              % (pre["docs"], pre["chunks"], post["docs"], post["chunks"]))
        same_docs = set(pre["content"]) == set(post["content"])
        diff = []
        for d in sorted(set(pre["content"]) | set(post["content"])):
            a = pre["content"].get(d) or []
            b = post["content"].get(d) or []
            if a != b:
                diff.append({"doc": d, "pre": len(a), "post": len(b),
                             "changed_chunks": sum(
                                 1 for x, y in zip(a, b) if x != y)
                             + abs(len(a) - len(b))})
        out = {"docs_equal": same_docs,
               "pre": {"docs": pre["docs"], "chunks": pre["chunks"]},
               "post": {"docs": post["docs"], "chunks": post["chunks"]},
               "content_identical": not diff, "diffs": diff[:10]}
        (EVID / "reembed_verify.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print("docs_equal:", same_docs, "content_identical:", not diff)
        if diff:
            for d in diff[:6]:
                print("  DIFF", d)
        verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
