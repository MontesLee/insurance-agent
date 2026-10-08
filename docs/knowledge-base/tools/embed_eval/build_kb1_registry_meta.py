# -*- coding: utf-8 -*-
"""Build knowledge/pilot/registry/kb1_sources.json (29 entries) from
docs/knowledge-base/source-manifest.yaml — registry metadata for the
KB-V1 corpus (§11). Field shape mirrors pilot_sources.json."""
import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[4]
MANIFEST = REPO / "docs/knowledge-base/source-manifest.yaml"
OUT = REPO / "knowledge/pilot/registry/kb1_sources.json"

m = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

TYPE_MAP = {"law": "law"}
rows = []
for stem in sorted(m):
    e = m[stem]
    if not e.get("runtime_enabled", True) \
            or e.get("current_status") == "BLOCKED":
        continue                      # L2-04 BLOCKED — not in the KB
    layer = e.get("layer")
    if stem == "L1-01":
        stype, auth = "law", "S"          # 法律（全国人大）
    elif layer == "L1":
        stype, auth = "regulation", "A"   # 监管规章/规范性文件
    else:
        stype, auth = "industry_standard", "B"  # 行业规范
    eff = str(e.get("effective_date") or "")
    import re as _re
    _dm = _re.search(r"\d{4}-\d{2}-\d{2}", eff)    # first clean ISO date
    if not _dm:                                     # fall back to publication
        eff = str(e.get("publication_date") or "")
        _dm = _re.search(r"\d{4}-\d{2}-\d{2}", eff)
    eff = _dm.group(0) if _dm else ""
    rows.append({
        "document_id": stem,
        "source_id": "kbv1-" + stem,
        "source_name": e["title"],
        "source_type": stype,
        "authority_level": auth,
        "jurisdiction": "CN",
        "version": str(e.get("version") or ""),
        "effective_from": eff or None,
        "effective_to": None,
        "status": "ACTIVE",
        "license_status": "ALLOWED",
        "license_note": "官方公开发布文件（%s）" % (
            e.get("document_number") or e.get("source_organization")),
        "canonical_uri": e.get("official_url") or "",
        "retrieved_at": str(e.get("retrieval_date") or ""),
        "copy_status": "PARTIAL_VERBATIM",
        "publisher": e.get("source_organization") or "",
        "official_url": e.get("official_url") or "",
        "document_number": e.get("document_number") or "",
        "checksum": e.get("checksum") or "",
        "manifest_path": "docs/knowledge-base/source-manifest.yaml",
    })

OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1),
               encoding="utf-8")
print("wrote", OUT, len(rows), "entries")
by = {}
for r in rows:
    by[r["authority_level"]] = by.get(r["authority_level"], 0) + 1
print("authority:", by)
