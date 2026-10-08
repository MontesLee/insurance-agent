# -*- coding: utf-8 -*-
"""Create the isolated eval KB (bge-m3 arm) and upload the IDENTICAL
29 files as insurance-kb-v1 (27 corpus .md + 2 official PDFs).

Isolation: new dataset only; insurance-pilot-2 / insurance-kb-v1
untouched. Reversible: delete KB + model row 'bge-m3-eval'.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[4]
KB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KB / "tools"))

BASE = "http://127.0.0.1:8080"
TENANT = "10001"
KB_NAME = "insurance-kb-v1-eval-bge-m3"
EMBED = "bge-m3-eval"
SUMMARY = "685eb417-ddb0-4dd6-ab29-5353f841cbaa"

CORPUS = KB / "sources" / "corpus"
PDFS = KB / "sources" / "raw"


def H(jwt):
    return {"Authorization": f"Bearer {jwt}", "X-Tenant-ID": TENANT}


def main() -> int:
    jwt = (REPO / "tmp" / "weknora-admin.jwt").read_text(encoding="utf-8").strip()
    s = requests.Session()

    kbs = s.get(f"{BASE}/api/v1/knowledge-bases", headers=H(jwt), timeout=30).json()["data"]
    kb = next((k for k in kbs if k["name"] == KB_NAME), None)
    if kb:
        kbid = kb["id"]
        print("reusing KB", kbid)
    else:
        r = s.post(f"{BASE}/api/v1/knowledge-bases", headers=H(jwt),
                   json={"name": KB_NAME,
                         "description": "KB-V1 embedding A/B eval (bge-m3 arm) — isolated copy of insurance-kb-v1 corpus; never production"},
                   timeout=30)
        r.raise_for_status()
        kbid = r.json()["data"]["id"]
        print("created KB", kbid)

    r = s.put(f"{BASE}/api/v1/initialization/config/{kbid}", headers=H(jwt),
              json={"embeddingModelId": EMBED, "llmModelId": SUMMARY,
                    "documentSplitting": {"chunkSize": 512, "chunkOverlap": 80,
                                          "enableParentChild": False}},
              timeout=30)
    r.raise_for_status()
    print("model config:", r.json().get("message"))

    existing = {}
    page = 1
    while True:
        batch = s.get(f"{BASE}/api/v1/knowledge-bases/{kbid}/knowledge",
                      params={"limit": 20, "page": page}, headers=H(jwt), timeout=30).json()["data"] or []
        if not batch:
            break
        for d in batch:
            existing[d["file_name"]] = d
        if len(batch) < 20:
            break
        page += 1
    print("existing docs:", len(existing))

    files = sorted(CORPUS.glob("*.md"))
    # identical to delivered KB: L2-01/L2-02 use official PDFs
    files = [f for f in files if f.stem not in ("L2-01", "L2-02")]
    files += [PDFS / "L2-01-pdf.pdf", PDFS / "L2-02-pdf.pdf"]
    # rename pdfs to match delivered naming
    upload_names = {PDFS / "L2-01-pdf.pdf": "L2-01.pdf", PDFS / "L2-02-pdf.pdf": "L2-02.pdf"}

    results = {}
    out = KB / "evidence" / "eval" / "import_eval_bgem3.json"
    if out.exists():
        results = json.loads(out.read_text(encoding="utf-8"))

    t0 = time.time()
    for i, f in enumerate(files, 1):
        fname = upload_names.get(f, f.name)
        if fname in existing and results.get(fname, {}).get("verified"):
            print(f"[{i}/{len(files)}] {fname}: skip (verified)")
            continue
        rec = {"file": fname}
        try:
            if fname in existing:
                kid = existing[fname]["id"]
            else:
                ctype = "application/pdf" if fname.endswith(".pdf") else "text/markdown"
                r = s.post(f"{BASE}/api/v1/knowledge-bases/{kbid}/knowledge/file",
                           headers=H(jwt),
                           files={"file": (fname, f.read_bytes(), ctype)},
                           timeout=300)
                r.raise_for_status()
                kid = r.json()["data"]["id"]
            rec["knowledge_id"] = kid
            status = "processing"
            for _ in range(120):  # up to 10 min per doc
                st = s.get(f"{BASE}/api/v1/knowledge/{kid}", headers=H(jwt), timeout=30).json()["data"]
                status = st.get("parse_status")
                if status in ("completed", "failed"):
                    break
                time.sleep(5)
            rec["parse_status"] = status
            if status == "completed":
                ch = s.get(f"{BASE}/api/v1/chunks/{kid}", params={"page_size": 1000},
                           headers=H(jwt), timeout=60).json()["data"] or []
                rec["chunk_count"] = len(ch)
            rec["verified"] = status == "completed" and rec.get("chunk_count", 0) > 0
            print(f"[{i}/{len(files)}] {fname}: {status} chunks={rec.get('chunk_count')}")
        except Exception as exc:  # noqa: BLE001
            rec["error"] = str(exc)[:200]
            rec["verified"] = False
            print(f"[{i}/{len(files)}] {fname}: ERROR {str(exc)[:120]}")
        results[fname] = rec
        out.write_text(json.dumps({"kb_id": kbid, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = sum(1 for v in results.values() if v.get("verified"))
    print(f"\nEVAL KB IMPORT: {ok}/{len(files)} verified in {round(time.time()-t0)}s")
    print("kb_id:", kbid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
