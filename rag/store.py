"""Knowledge store: ingest markdown KB (heading-aware chunking) + metadata-filtered access.

Storage uses SQLite for provenance/metadata; the actual ranking is done in engine.py so the
store stays backend-agnostic. Pure stdlib (sqlite3 ships with Python).
"""
from __future__ import annotations
import os
import re
import sqlite3
from .models import Chunk

# document_id prefix -> product_type (see mini test KB naming)
PRODUCT_BY_PREFIX = {
    "01": "medical", "02": "critical", "03": "accident",
    "04": "life", "05": "health", "06": "claims",
}


def chunk_markdown(text: str, document_id: str, document_name: str,
                   source_type: str = "internal", source_level: str = "B",
                   product_type: str = "", topic: str = "") -> list:
    """Heading-aware chunking: split on H1/H2/H3 and keep the section path as context.

    Avoids cutting a single rule (e.g. 等待期/既往症) in the middle.
    """
    lines = text.splitlines()
    chunks = []
    buf = []
    cur_heading = "根"
    idx = 0

    def flush():
        nonlocal buf, cur_heading, idx
        if buf:
            content = "\n".join(buf).strip()
            if content:
                chunks.append(Chunk(
                    chunk_id=f"{document_id}_{idx:03d}",
                    document_id=document_id,
                    document_name=document_name,
                    content=content,
                    section=cur_heading,
                    source_type=source_type,
                    source_level=source_level,
                    product_type=product_type,
                    topic=topic,
                ))
                idx += 1
            buf = []

    for ln in lines:
        m = re.match(r"^#{1,3}\s+(.*)$", ln)
        if m:
            flush()
            cur_heading = m.group(1).strip()
        else:
            buf.append(ln)
    flush()
    return chunks


class KnowledgeStore:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS chunks(
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT, document_name TEXT, content TEXT,
                section TEXT, source_type TEXT, source_level TEXT,
                product_type TEXT, topic TEXT,
                created_at TEXT, effective_date TEXT, version TEXT)"""
        )
        self.conn.commit()

    def add_chunks(self, chunks: list):
        for ch in chunks:
            self.conn.execute(
                "INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ch.chunk_id, ch.document_id, ch.document_name, ch.content, ch.section,
                 ch.source_type, ch.source_level, ch.product_type, ch.topic,
                 ch.created_at, ch.effective_date, ch.version))
        self.conn.commit()

    def ingest_file(self, path: str, source_type: str = "internal", source_level: str = "B"):
        text = open(path, encoding="utf-8-sig").read()
        base = os.path.basename(path)
        document_id = os.path.splitext(base)[0]
        m = re.match(r"(\d+)_", document_id)
        product_type = PRODUCT_BY_PREFIX.get(m.group(1), "") if m else ""
        chunks = chunk_markdown(text, document_id, document_id, source_type, source_level, product_type)
        self.add_chunks(chunks)
        return chunks

    def ingest_dir(self, d: str, source_type: str = "internal", source_level: str = "B"):
        allc = []
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith((".md", ".txt")):
                allc += self.ingest_file(os.path.join(d, fn), source_type, source_level)
        return allc

    def all_chunks(self) -> list:
        rows = self.conn.execute("SELECT * FROM chunks").fetchall()
        return [_row_to_chunk(r) for r in rows]

    def get_chunk(self, cid: str):
        r = self.conn.execute("SELECT * FROM chunks WHERE chunk_id=?", (cid,)).fetchone()
        return _row_to_chunk(r) if r else None

    def filtered_chunks(self, filters: dict):
        if not filters:
            return self.all_chunks()
        clauses, params = [], []
        for k, v in filters.items():
            if v:
                clauses.append(f"{k}=?")
                params.append(v)
        sql = "SELECT * FROM chunks" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_chunk(r) for r in rows]


def _row_to_chunk(r) -> Chunk:
    return Chunk(
        r["chunk_id"], r["document_id"], r["document_name"], r["content"],
        r["section"], r["source_type"], r["source_level"], r["product_type"], r["topic"],
        r["created_at"], r["effective_date"], r["version"])
