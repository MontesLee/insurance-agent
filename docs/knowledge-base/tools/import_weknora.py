# -*- coding: utf-8 -*-
"""Import KB-V1 corpus (29 verified docs) into WeKnora as a NEW dataset.

- KB: 'insurance-kb-v1' in tenant 10001 (same tenant as insurance-pilot-2)
- embedding model: builtin-embedding-local (same as insurance-pilot-2 —
  required, else uploads stall in 'processing' forever: Phase-24 gotcha)
- idempotent: KB + per-filename uploads reused on re-run
- verifies per doc: parse_status == completed AND chunk_count > 0
- writes evidence/import_results.json

Auth: Bearer JWT read from tmp/weknora-admin.jwt (or
INSURANCE_AGENT_WEKNORA_JWT env). X-Tenant-ID: 10001.

ZERO production runtime change: creates only WeKnora datasets; does not
touch runtime env/config/keys; runtime keeps pointing at its current KB.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[3]
KB_DIR = Path(__file__).resolve().parents[1]
CORPUS = KB_DIR / "sources" / "corpus"
EVID = KB_DIR / "evidence"

BASE = "http://127.0.0.1:8080"
TENANT = "10001"
KB_NAME = "insurance-kb-v1"
KB_DESC = (
    "Insurance KB v1.0 — 29 verified official documents "
    "(25 L1 laws/regulations + 4 L2 industry standards; L2-04 blocked). "
    "Source manifest: docs/knowledge-base/source-manifest.yaml"
)
EMBED_MODEL = "builtin-embedding-local"
SUMMARY_MODEL = "685eb417-ddb0-4dd6-ab29-5353f841cbaa"  # same as insurance-pilot-2


def auth_headers(jwt: str) -> dict:
    return {
        "Authorization": f"Bearer {jwt}",
        "X-Tenant-ID": TENANT,
    }


def get_or_create_kb(s: requests.Session, jwt: str) -> tuple[str, bool]:
    r = s.get(
        f"{BASE}/api/v1/knowledge-bases",
        headers=auth_headers(jwt),
        timeout=30,
    )
    r.raise_for_status()
    for kb in r.json().get("data") or []:
        if kb.get("name") == KB_NAME:
            return kb["id"], False
    r = s.post(
        f"{BASE}/api/v1/knowledge-bases",
        headers=auth_headers(jwt),
        json={
            "name": KB_NAME,
            "description": KB_DESC,
            "embedding_model": EMBED_MODEL,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"]["id"], True


def kb_detail(s: requests.Session, jwt: str, kbid: str) -> dict:
    r = s.get(f"{BASE}/api/v1/knowledge-bases/{kbid}", headers=auth_headers(jwt), timeout=30)
    r.raise_for_status()
    return r.json().get("data") or {}


def list_kb_docs(s: requests.Session, jwt: str, kbid: str) -> list[dict]:
    r = s.get(
        f"{BASE}/api/v1/knowledge-bases/{kbid}/knowledge",
        params={"limit": 200},
        headers=auth_headers(jwt),
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("data") or []


def upload_doc(s: requests.Session, jwt: str, kbid: str, path: Path) -> dict:
    fname = path.name
    files = {"file": (fname, path.read_bytes(), "text/markdown")}
    r = s.post(
        f"{BASE}/api/v1/knowledge-bases/{kbid}/knowledge/file",
        headers=auth_headers(jwt),
        files=files,
        timeout=120,
    )
    r.raise_for_status()
    return r.json().get("data") or {}


def doc_status(s: requests.Session, jwt: str, kid: str) -> dict:
    r = s.get(
        f"{BASE}/api/v1/knowledge/{kid}", headers=auth_headers(jwt), timeout=30
    )
    r.raise_for_status()
    return r.json().get("data") or {}


def chunk_count(s: requests.Session, jwt: str, kid: str) -> int:
    r = s.get(
        f"{BASE}/api/v1/chunks/{kid}",
        params={"page_size": 1000},
        headers=auth_headers(jwt),
        timeout=30,
    )
    r.raise_for_status()
    return len(r.json().get("data") or [])


def ensure_model_config(s: requests.Session, jwt: str, kbid: str) -> None:
    """WeKnora 2.x: embedding+summary model are set via the
    initialization-config endpoint (discovered from the frontend save
    flow: PUT /api/v1/initialization/config/{kbId}). KB create ignores
    model fields; without a model uploads stall in 'processing'."""
    d = kb_detail(s, jwt, kbid)
    if d.get("embedding_model_id") == EMBED_MODEL:
        return
    r = s.put(
        f"{BASE}/api/v1/initialization/config/{kbid}",
        headers=auth_headers(jwt),
        json={
            "embeddingModelId": EMBED_MODEL,
            "llmModelId": SUMMARY_MODEL,
            "documentSplitting": {
                "chunkSize": 512,
                "chunkOverlap": 80,
                "enableParentChild": False,
            },
        },
        timeout=30,
    )
    r.raise_for_status()
    print(f"model config set: {r.json().get('message')}")


def main() -> int:
    jwt = ""
    jwt_file = REPO / "tmp" / "weknora-admin.jwt"
    if jwt_file.exists():
        jwt = jwt_file.read_text(encoding="utf-8").strip()
    import os

    jwt = os.environ.get("INSURANCE_AGENT_WEKNORA_JWT", jwt)
    if not jwt:
        print("NO JWT available — import BLOCKED")
        return 2

    s = requests.Session()
    # auth check
    r = s.get(f"{BASE}/api/v1/knowledge-bases", headers=auth_headers(jwt), timeout=30)
    if r.status_code == 401:
        print("JWT EXPIRED/INVALID — import BLOCKED (need fresh owner JWT)")
        return 2
    r.raise_for_status()

    kbid, created = get_or_create_kb(s, jwt)
    print(f"KB {KB_NAME}: {kbid} ({'created' if created else 'reused'})")
    ensure_model_config(s, jwt, kbid)
    detail = kb_detail(s, jwt, kbid)
    print(f"KB embedding_model_id: {detail.get('embedding_model_id')}")
    if detail.get("embedding_model_id") != EMBED_MODEL:
        print(
            f"WARNING: embedding model mismatch: {detail.get('embedding_model_id')!r} "
            f"(expected {EMBED_MODEL!r}) — uploads may stall in processing"
        )

    existing = {d.get("file_name"): d for d in list_kb_docs(s, jwt, kbid)}
    print(f"existing docs in KB: {len(existing)}")

    results: dict[str, dict] = {}
    out_path = EVID / "import_results.json"
    if out_path.exists():
        results = json.loads(out_path.read_text(encoding="utf-8"))

    files = sorted(CORPUS.glob("*.md"))
    for i, path in enumerate(files, 1):
        doc_id = path.stem
        prev = results.get(doc_id, {})
        if prev.get("parse_status") == "completed" and prev.get("chunk_count", 0) > 0:
            print(f"[{i}/{len(files)}] {doc_id}: already imported (skip)")
            continue
        rec: dict = {"file": path.name}
        try:
            if path.name in existing:
                kid = existing[path.name]["id"]
                rec["upload"] = "reused"
            else:
                data = upload_doc(s, jwt, kbid, path)
                kid = data.get("id") or data.get("knowledge_id")
                rec["upload"] = "uploaded"
            rec["knowledge_id"] = kid
            # wait for parse
            status = "processing"
            for _ in range(60):  # up to 5 min
                st = doc_status(s, jwt, kid)
                status = st.get("parse_status") or "unknown"
                if status in ("completed", "failed"):
                    break
                time.sleep(5)
            rec["parse_status"] = status
            rec["enabled"] = st.get("enabled")
            rec["chunk_count"] = chunk_count(s, jwt, kid) if status == "completed" else 0
            rec["verified"] = status == "completed" and rec["chunk_count"] > 0
            print(
                f"[{i}/{len(files)}] {doc_id}: {rec['upload']} parse={status} "
                f"chunks={rec['chunk_count']}"
            )
        except Exception as exc:  # noqa: BLE001
            rec["error"] = str(exc)[:300]
            rec["verified"] = False
            print(f"[{i}/{len(files)}] {doc_id}: ERROR {exc}")
        results[doc_id] = rec
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(1.0)

    ok = sum(1 for v in results.values() if v.get("verified"))
    print(f"\nIMPORT SUMMARY: {ok}/{len(files)} verified (completed + chunks>0)")
    out_path.write_text(
        json.dumps(
            {"kb_id": kbid, "kb_name": KB_NAME, "results": results},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return 0 if ok == len(files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
