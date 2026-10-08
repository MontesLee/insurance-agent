# -*- coding: utf-8 -*-
"""Embedding driver: batches of texts -> vectors, via the WeKnora-app
container's python3 (which resolves weknora-ollama DNS). Zero
infrastructure change; ollama is reached in-container over the docker
network.

Usage (host):
  python embed_driver.py <model> <input_json> <output_json>
    input_json:  {"texts": ["...", ...]}
    output_json: {"model": ..., "dim": ..., "vectors": [[...], ...],
                  "elapsed_s": ..., "batches": n}
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

CONTAINER = "WeKnora-app"
OLLAMA = "http://weknora-ollama:11434/api/embed"
BATCH = 16

# runs INSIDE the container: reads base64 json from stdin, posts batches,
# writes base64 json to stdout
_INNER = r'''
import base64, json, sys, time, urllib.request
payload = json.loads(base64.b64decode(sys.stdin.read()))
model, texts, batch = payload["model"], payload["texts"], payload.get("batch", 16)
OLLAMA = "http://weknora-ollama:11434/api/embed"
vectors, t0 = [], time.time()
for i in range(0, len(texts), batch):
    part = texts[i:i+batch]
    body = json.dumps({"model": model, "input": part}).encode("utf-8")
    req = urllib.request.Request(OLLAMA, data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read().decode("utf-8"))
    embs = out.get("embeddings") or []
    if len(embs) != len(part):
        raise SystemExit("batch %d mismatch: %d != %d" % (i, len(embs), len(part)))
    vectors.extend(embs)
sys.stdout.write(base64.b64encode(json.dumps(
    {"model": model, "vectors": vectors, "elapsed_s": time.time()-t0}
).encode("utf-8")).decode("ascii"))
'''


def embed(model: str, texts: list[str], batch: int = BATCH) -> dict:
    payload = base64.b64encode(
        json.dumps({"model": model, "texts": texts, "batch": batch}, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    t0 = time.time()
    proc = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "python3", "-c", _INNER],
        input=payload.encode("ascii"),
        capture_output=True,
        timeout=7200,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"docker exec failed: {proc.stderr.decode('utf-8', 'replace')[:400]}")
    out = json.loads(base64.b64decode(proc.stdout.strip()))
    out["host_wall_s"] = time.time() - t0
    out["n"] = len(texts)
    out["dim"] = len(out["vectors"][0]) if out["vectors"] else 0
    return out


if __name__ == "__main__":
    model, inp, outp = sys.argv[1], sys.argv[2], sys.argv[3]
    texts = json.loads(Path(inp).read_text(encoding="utf-8"))["texts"]
    res = embed(model, texts)
    Path(outp).write_text(json.dumps(res), encoding="utf-8")
    print(
        json.dumps(
            {
                "model": model,
                "n": res["n"],
                "dim": res["dim"],
                "elapsed_s": round(res["elapsed_s"], 1),
                "ms_per_text": round(res["elapsed_s"] * 1000 / max(1, res["n"]), 1),
            },
            ensure_ascii=False,
        )
    )
