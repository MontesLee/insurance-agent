#!/usr/bin/env python3
"""WeKnora projection-registry sync — Phase 18 (operator tool, env-gated).

Builds the AGENT-side governance projection of a live WeKnora corpus:

  governance metadata (authority/license/window/version/jurisdiction)
      = the AGENT registries (pilot_sources / fixtures_sources) — TRUTH
  chunk identity + content hashes
      = the REAL WeKnora chunking (fetched via GET /api/v1/chunks/{kid})

Also prepares the smoke surfaces for the live tests (an empty KB and an
UNREGISTERED-document KB) and records environment ids (no secrets) in
weknora_environment.json.

Usage (env): INSURANCE_AGENT_WEKNORA_URL, INSURANCE_AGENT_WEKNORA_JWT
(admin session for KB creation/upload). Idempotent: existing KBs and
already-uploaded filenames are reused.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

URL = os.environ.get("INSURANCE_AGENT_WEKNORA_URL", "").rstrip("/")
JWT = os.environ.get("INSURANCE_AGENT_WEKNORA_JWT", "")
FIXTURES_KB = os.path.join(REPO, ".trae", "skills", "knowledge-search",
                           "evals", "fixtures", "kb")

OUT_DIR = os.path.join(HERE, "registry")
SCRATCH_DOC = os.path.join(HERE, "weknora_scratch_unregistered.md")


def _req(method, path, body=None, auth=None, form=None):
    headers = {}
    if auth:
        headers["Authorization"] = "Bearer " + auth
    data = None
    if form is not None:
        import uuid
        b = "-" * 0
        boundary = "b" + uuid.uuid4().hex
        lines = []
        for k, v in form.items():
            lines.append("--%s" % boundary)
            lines.append('Content-Disposition: form-data; name="%s"' % k)
            lines.append("")
            lines.append(v if isinstance(v, str) else v.decode("utf-8"))
        for k, (fname, blob) in (body or {}).items():
            lines.append("--%s" % boundary)
            lines.append('Content-Disposition: form-data; name="%s"; '
                         'filename="%s"' % (k, fname))
            lines.append("Content-Type: text/markdown")
            lines.append("")
            lines.append(blob.decode("utf-8"))
        lines.append("--%s--" % boundary)
        data = "\r\n".join(lines).encode("utf-8")
        headers["Content-Type"] = "multipart/form-data; boundary=%s" % boundary
        body = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(URL + path, data=data, headers=headers,
                                 method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_or_create_kb(name, description):
    for kb in (_req("GET", "/api/v1/knowledge-bases", auth=JWT)
               .get("data") or []):
        if kb.get("name") == name:
            return kb["id"], False
    out = _req("POST", "/api/v1/knowledge-bases",
               {"name": name, "description": description}, auth=JWT)
    return out["data"]["id"], True


def upload_if_absent(kbid, path):
    fname = os.path.basename(path)
    existing = _req("GET", "/api/v1/knowledge-bases/%s/knowledge?limit=100"
                    % kbid, auth=JWT).get("data") or []
    for k in existing:
        if k.get("file_name") == fname:
            return k["id"], False
    with open(path, "rb") as f:
        blob = f.read()
    import uuid
    boundary = "b" + uuid.uuid4().hex
    parts = []
    parts.append("--%s" % boundary)
    parts.append('Content-Disposition: form-data; name="file"; '
                 'filename="%s"' % fname)
    parts.append("Content-Type: text/markdown")
    parts.append("")
    parts.append(blob.decode("utf-8"))
    parts.append("--%s--" % boundary)
    data = "\r\n".join(parts).encode("utf-8")
    req = urllib.request.Request(
        URL + "/api/v1/knowledge-bases/%s/knowledge/file" % kbid, data=data,
        headers={"Authorization": "Bearer " + JWT,
                 "Content-Type": "multipart/form-data; boundary=%s"
                 % boundary}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    return out["data"]["id"], True


def wait_parsed(kbid, kid, tries=40):
    for _ in range(tries):
        st = _req("GET", "/api/v1/knowledge/%s" % kid, auth=JWT) \
            .get("data", {}).get("parse_status")
        if st in ("completed", "failed"):
            return st
        time.sleep(5)
    return "timeout"


def fetch_chunks(kid):
    chunks = _req("GET", "/api/v1/chunks/%s?page_size=1000" % kid,
                  auth=JWT).get("data") or []
    return chunks


def projection_for(kbid, sources_path):
    """entries = agent governance metadata + WeKnora chunk hashes."""
    base = {e["document_id"]: e for e in
            json.load(open(sources_path, encoding="utf-8"))}
    entries, report = [], []
    for k in (_req("GET", "/api/v1/knowledge-bases/%s/knowledge?limit=100"
                   % kbid, auth=JWT).get("data") or []):
        stem = os.path.splitext(k.get("file_name") or "")[0]
        if stem not in base:
            report.append(("UNREGISTERED-SIDE", stem, "skipped"))
            continue
        chunks = fetch_chunks(k["id"])
        entry = dict(base[stem])
        entry["content_hashes"] = {
            c["id"]: hashlib.sha256((c.get("content") or "")
                                    .encode("utf-8")).hexdigest()
            for c in chunks if c.get("id")}
        entries.append(entry)
        report.append(("OK", stem, len(entry["content_hashes"])))
    return entries, report


def main():
    assert URL and JWT, "set INSURANCE_AGENT_WEKNORA_URL and _JWT"
    os.makedirs(OUT_DIR, exist_ok=True)
    env_info = {"url": URL}

    # 1) fixtures corpus (deterministic business corpus, weknora backend)
    fx_kb, _ = get_or_create_kb("agent-fixtures",
                                "deterministic fixtures corpus (synced)")
    env_info["fixtures_kb"] = fx_kb
    for fn in sorted(os.listdir(FIXTURES_KB)):
        if fn.endswith(".md"):
            kid, created = upload_if_absent(fx_kb,
                                            os.path.join(FIXTURES_KB, fn))
            if created:
                st = wait_parsed(fx_kb, kid)
                print("fixtures upload %s -> %s" % (fn, st))

    # 2) pilot corpus documents (already ingested by env prep; ensure)
    pilot_kb = os.environ.get("INSURANCE_AGENT_WEKNORA_PILOT_KB", "")
    if pilot_kb:
        env_info["pilot_kb"] = pilot_kb

    # 3) smoke surfaces: empty KB + one UNREGISTERED scratch doc
    with open(SCRATCH_DOC, "w", encoding="utf-8") as f:
        f.write("# 未注册测试文档(SYNTHETIC — 不得进入治理)\n\n"
                "> 本文档不在 Agent Governance Registry 中;"
                "任何来自本文档的检索命中必须被 DENY。\n\n"
                "量子色动力学规范群与德甲联赛积分榜毫无关系,仅用于验证"
                "未注册文档拒绝路径。\n")
    smoke_kb, _ = get_or_create_kb("smoke-unregistered",
                                   "empty + unregistered-doc KB for "
                                   "live tests")
    env_info["smoke_kb"] = smoke_kb
    upload_if_absent(smoke_kb, SCRATCH_DOC)

    # 4) build projections
    fx_entries, fx_report = projection_for(
        fx_kb, os.path.join(REPO, "knowledge", "governance", "fixtures",
                            "fixtures_sources.json"))
    json.dump(fx_entries, open(os.path.join(
        OUT_DIR, "weknora_fixtures_registry.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)
    print("fixtures projection: %d entries" % len(fx_entries))

    if pilot_kb:
        pl_entries, pl_report = projection_for(
            pilot_kb, os.path.join(HERE, "registry", "pilot_sources.json"))
        json.dump(pl_entries, open(os.path.join(
            OUT_DIR, "weknora_pilot_registry.json"), "w",
            encoding="utf-8"), ensure_ascii=False, indent=1)
        print("pilot projection: %d entries" % len(pl_entries))

    json.dump(env_info, open(os.path.join(OUT_DIR, "weknora_environment.json"),
                             "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("environment sidecar written (no secrets)")


if __name__ == "__main__":
    sys.exit(main())
