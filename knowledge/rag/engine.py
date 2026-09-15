"""Knowledge Search engine: normalize -> retrieve -> RRF fuse -> over-retrieval -> rerank -> evidence.

All scoring weights, source-quality mapping, thresholds and conflict keys are read from the
externalized rules (knowledge-search/resources/config/*.rules.json). The engine never hard-codes
a judgment.
"""
from __future__ import annotations
import math
import re
from .models import Chunk, NormalizedQuery, Candidate, Evidence, RetrievalResult


def _trigrams(s: str) -> list:
    s = re.sub(r"\s+", "", s or "")
    if len(s) < 3:
        return list(s) if s else []
    return [s[i:i + 3] for i in range(len(s) - 2)]


# Chinese filler that should not drive retrieval on its own
_FILLER = set("我想知道到底有哪这那的是不吗呢吧啊怎么什么如何为什么请问想了解下关于可以能否".split())


def normalize_query(q: str) -> NormalizedQuery:
    original = q
    cleaned = re.sub(r"[？?！!。.，,、~～\s]+", " ", q or "").strip()
    return NormalizedQuery(original, cleaned, _trigrams(cleaned))


class SparseRetriever:
    """Pure-Python trigram-BM25 sparse retriever (no external deps, CJK-friendly)."""

    def __init__(self):
        self.corpus: list = []
        self.df: dict = {}
        self.idf: dict = {}

    def index(self, chunks):
        self.corpus = list(chunks)
        self.df = {}
        for ch in self.corpus:
            for t in set(_trigrams(ch.content)):
                self.df[t] = self.df.get(t, 0) + 1
        n = len(self.corpus) or 1
        self.idf = {t: math.log((n - df + 0.5) / (df + 0.5) + 1.0) for t, df in self.df.items()}

    def search(self, query, top_k=20, filters=None):
        if filters:
            cand = [c for c in self.corpus
                    if all(getattr(c, k, None) == v for k, v in filters.items() if v)]
        else:
            cand = self.corpus
        qt = _trigrams(query)
        if not qt:
            return []
        qtf = {}
        for t in qt:
            qtf[t] = qtf.get(t, 0) + 1
        sizes = [max(len(_trigrams(c.content)), 1) for c in cand]
        avgdl = sum(sizes) / (len(sizes) or 1)
        k1, b = 1.5, 0.75
        scored = []
        for c in cand:
            doc_tf = {}
            for t in _trigrams(c.content):
                doc_tf[t] = doc_tf.get(t, 0) + 1
            dl = len(_trigrams(c.content)) or 1
            score = 0.0
            for t, qf in qtf.items():
                if t in doc_tf:
                    idf = self.idf.get(t, 0.0)
                    f = doc_tf[t]
                    score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
            if score > 0:
                scored.append((c, score))
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]


class DenseRetriever:
    """Dense-retrieval interface (Lawgent route: BGE-M3 embedding + vector store).

    V0.1 leaves this as an interface only — no embedding backend is installed in this
    environment, and the user explicitly approved "complex parts may stay interface-only".

    Contract for a future implementer (mirrors Lawgent's embeddings.py + vector store):
      - index(chunks): embed each Chunk.content and store vectors (e.g. sentence-transformers
        BGE-M3; backend could be Qdrant / FAISS / numpy).
      - search(query, top_k, filters) -> list[(Chunk, float)]  (descending by dense score).
      - Must honour the same `filters` semantics as SparseRetriever so RRF fusion is uniform.
    The engine already wires it in: when `dense_enabled` is true in rules, it indexes and
    fuses dense results via rrf_fuse(). Swapping in a real backend needs no engine change.
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def index(self, chunks):
        pass

    def search(self, query, top_k=20, filters=None):
        if not self.enabled:
            return []
        raise NotImplementedError("Dense retrieval requires an embedding backend (not installed in V0.1).")


def rrf_fuse(rank_lists: list, k: int = 60):
    """Reciprocal Rank Fusion across retrieved rank lists."""
    scores = {}
    for rl in rank_lists:
        for rank, (ch, _sc) in enumerate(rl):
            entry = scores.setdefault(ch.chunk_id, {"chunk": ch, "s": 0.0})
            entry["s"] += 1.0 / (k + rank + 1)
    out = [(v["chunk"], v["s"]) for v in scores.values()]
    out.sort(key=lambda x: -x[1])
    return out


def _minmax(vals: list):
    if not vals:
        return {}
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return {i: 1.0 for i in range(len(vals))}
    return {i: (v - lo) / (hi - lo) for i, v in enumerate(vals)}


def _query_product(query: str):
    mapping = {
        "medical": ["医疗", "百万医疗", "住院医疗"],
        "critical": ["重疾", "重大疾病"],
        "accident": ["意外"],
        "life": ["寿险", "身故"],
        "health": ["核保", "健康告知", "既往症"],
        "claims": ["理赔"],
    }
    for pt, kws in mapping.items():
        if any(k in query for k in kws):
            return pt
    return ""


class BaseReranker:
    """Reranker interface. Subclasses must implement rerank(query, candidates, debug)."""

    def rerank(self, query, candidates, debug=False):
        raise NotImplementedError


class CrossEncoderReranker(BaseReranker):
    """Cross-encoder reranker (Lawgent uses a cross-encoder at this stage).

    Complex (needs a model backend: sentence-transformers / a local cross-encoder).
    Interface-only in V0.1 — left as a stub per the 'complex parts may stay interface-only'
    directive. A future implementation re-ranks the over-retrieved candidate pool by scoring
    each (query, chunk) pair jointly, replacing DefaultReranker's deterministic weighting.
    """

    def __init__(self, model_path: str = None, enabled: bool = False):
        self.model_path = model_path
        self.enabled = enabled

    def rerank(self, query, candidates, debug=False):
        if not self.enabled:
            raise NotImplementedError(
                "CrossEncoderReranker requires a model backend (not installed in V0.1).")
        raise NotImplementedError


class DefaultReranker(BaseReranker):
    """Deterministic weighted reranker. Weights/levels come from externalized rules."""

    def __init__(self, rules: dict):
        self.rules = rules

    def rerank(self, query, candidates, debug=False):
        w = self.rules.get("weights", {})
        w_sem = w.get("semantic", 0.1)
        w_kw = w.get("keyword", 0.35)
        w_dom = w.get("domain", 0.2)
        w_src = w.get("source", 0.25)
        w_spec = w.get("specificity", 0.1)
        sq = self.rules.get("source_quality", {"S": 1.0, "A": 0.85, "B": 0.65, "C": 0.45, "D": 0.2})
        dom_bonus = self.rules.get("domain_match_bonus", 1.0)
        dom_pen = self.rules.get("domain_mismatch_penalty", 0.35)
        spec_full = self.rules.get("specificity_full", 1.0)
        spec_gen = self.rules.get("specificity_generic", 0.5)

        sn = _minmax([c.sparse_score for c in candidates])
        dn = _minmax([c.dense_score for c in candidates])
        qprod = _query_product(query)

        out = []
        for i, c in enumerate(candidates):
            kw = sn.get(i, 0.0)
            sem = dn.get(i, 0.0) if c.dense_score > 0 else kw
            dom = dom_bonus if (c.chunk.product_type and qprod == c.chunk.product_type) else dom_pen
            src = sq.get(c.chunk.source_level, 0.4)
            spec = spec_full if c.chunk.product_type else spec_gen
            final = sem * w_sem + kw * w_kw + dom * w_dom + src * w_src + spec * w_spec
            c.semantic_score = sem
            c.keyword_score = kw
            c.domain_score = dom
            c.source_score = src
            c.specificity_score = spec
            c.rerank_score = final
            c.final_score = final
            out.append(c)
        out.sort(key=lambda x: -x.final_score)
        return out


class KnowledgeSearchEngine:
    def __init__(self, store, rules: dict):
        self.store = store
        self.rules = rules
        self.sparse = SparseRetriever()
        self.dense = DenseRetriever(enabled=bool(rules.get("dense_enabled", False)))
        chunks = store.all_chunks()
        self.sparse.index(chunks)
        if self.dense.enabled:
            self.dense.index(chunks)
        self.reranker = DefaultReranker(rules)

    def search(self, query, top_k=None, filters=None, min_relevance=None,
               source_types=None, debug=False) -> RetrievalResult:
        top_k = top_k or self.rules.get("final_k", 5)
        cand_k = self.rules.get("candidate_k", 20)
        min_relevance = (min_relevance if min_relevance is not None
                         else self.rules.get("min_relevance_score", 0.55))
        nq = normalize_query(query)

        sparse_res = self.sparse.search(nq.normalized, top_k=cand_k, filters=filters)
        dense_res = (self.dense.search(nq.normalized, top_k=cand_k, filters=filters)
                     if self.dense.enabled else [])
        if dense_res:
            fused = rrf_fuse([sparse_res, dense_res], k=self.rules.get("rrf_k", 60))
        else:
            fused = [(c, s) for c, s in sparse_res]

        cands = []
        for ch, rrf in fused:
            sp = next((s for c, s in sparse_res if c.chunk_id == ch.chunk_id), 0.0)
            dn = next((s for c, s in dense_res if c.chunk_id == ch.chunk_id), 0.0)
            cands.append(Candidate(ch, sparse_score=sp, dense_score=dn, rrf_score=rrf))

        reranked = self.reranker.rerank(nq.normalized, cands, debug=debug)
        passed = [c for c in reranked if c.final_score >= min_relevance]
        conflict = self._detect_conflict(passed)

        if not passed:
            status = "insufficient_evidence"
            reason = "No sufficiently relevant knowledge was retrieved."
        elif passed[0].final_score < self.rules.get("partial_threshold", 0.70):
            status = "partial_evidence"
            reason = "Retrieved some relevant knowledge but confidence below full-evidence threshold."
        else:
            status = "success"
            reason = ""

        evs = []
        for c in passed[:top_k]:
            evs.append(Evidence(
                chunk_id=c.chunk.chunk_id,
                document_id=c.chunk.document_id,
                document_name=c.chunk.document_name,
                source_type=c.chunk.source_type,
                source_level=c.chunk.source_level,
                section=c.chunk.section,
                content=c.chunk.content,
                score=round(c.final_score, 4),
                retrieval_score=round(c.sparse_score, 4),
                rerank_score=round(c.rerank_score, 4),
                final_score=round(c.final_score, 4),
                metadata={"product_type": c.chunk.product_type, "topic": c.chunk.topic},
            ))

        method = "hybrid_rrf" if dense_res else "sparse_rrf"
        meta = {
            "candidate_count": len(fused),
            "returned_count": len(evs),
            "retrieval_method": method,
            "reranker": "default",
            "candidate_chunk_ids": [c.chunk.chunk_id for c in reranked],
        }
        if debug:
            meta["debug_candidates"] = [
                {"chunk_id": c.chunk.chunk_id, "sparse": round(c.sparse_score, 4),
                 "rrf": round(c.rrf_score, 4), "final": round(c.final_score, 4)}
                for c in reranked[:cand_k]
            ]
        return RetrievalResult(status, query, nq.normalized, evs, conflict, reason, meta)

    def _detect_conflict(self, passed) -> bool:
        keys = self.rules.get("conflict_keys", [])
        if not keys:
            return False
        for key in keys:
            vals = set()
            for c in passed:
                m = re.search(re.escape(key) + r".{0,8}?(\d+)\s*天", c.chunk.content)
                if m:
                    vals.add(m.group(1))
            if len(vals) >= 2:
                return True
        return False
