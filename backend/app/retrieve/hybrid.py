from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from rank_bm25 import BM25Okapi

from app.config import Settings
from app.database import all_chunks_for_retrieval, all_figure_index_rows, get_conn
from app.retrieve.vector_store import VectorStore


def _tokenize(s: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in s).split() if t]


def _visual_intent(q: str) -> bool:
    qlow = q.lower()
    keys = (
        "figure",
        "fig.",
        "diagram",
        "chart",
        "plot",
        "image",
        "table",
        "graph",
        "illustration",
        "picture",
        "visual",
    )
    return any(k in qlow for k in keys)


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = 60,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = defaultdict(float)
    for ids in ranked_lists:
        for rank, doc_id in enumerate(ids):
            scores[doc_id] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


class HybridRetriever:
    def __init__(self, settings: Settings, store: VectorStore, db_path):
        self.settings = settings
        self.store = store
        self.db_path = db_path

    def retrieve(
        self,
        query: str,
        document_ids: Optional[list[str]] = None,
        include_figures: Optional[bool] = None,
        top_k_text: Optional[int] = None,
        top_k_figures: Optional[int] = None,
    ) -> dict[str, Any]:
        if include_figures is None:
            include_figures = _visual_intent(query)

        chunks = all_chunks_for_retrieval(self.db_path, document_ids)
        chunk_by_id = {c["id"]: c for c in chunks}
        corpus = [c["text"] for c in chunks]
        ids_order = [c["id"] for c in chunks]

        bm25_ranked: list[str] = []
        if corpus:
            tokenized = [_tokenize(t) for t in corpus]
            if any(tokenized):
                bm25 = BM25Okapi(tokenized)
                scores = bm25.get_scores(_tokenize(query))
                order = sorted(range(len(scores)), key=lambda i: -scores[i])
                bm25_ranked = [ids_order[i] for i in order[: self.settings.bm25_k]]

        k_text = top_k_text or self.settings.retrieve_k_text
        k_fig = top_k_figures or self.settings.retrieve_k_figures

        vec_res = self.store.query_text(
            query,
            n_results=k_text,
            document_ids=document_ids,
        )
        vec_ids: list[str] = []
        vec_dist: dict[str, float] = {}
        if vec_res["ids"] and vec_res["ids"][0]:
            for i, cid in enumerate(vec_res["ids"][0]):
                vec_ids.append(cid)
                d = vec_res["distances"][0][i] if vec_res.get("distances") else 0.0
                vec_dist[cid] = float(d)

        fused = reciprocal_rank_fusion([bm25_ranked, vec_ids], k=self.settings.rrf_k)
        top_chunk_ids = [fid for fid, _ in fused[: k_text * 4]]

        # Keep fusion order; drop stale Chroma/SQLite mismatches; backfill from DB if fusion was empty
        # or every ranked id was missing from SQLite (common after deleting Chroma but keeping SQLite).
        ordered_ids: list[str] = []
        seen: set[str] = set()
        for cid in top_chunk_ids:
            if cid in seen or cid not in chunk_by_id:
                continue
            seen.add(cid)
            ordered_ids.append(cid)
            if len(ordered_ids) >= k_text:
                break
        if len(ordered_ids) < k_text:
            for cid in ids_order:
                if cid in seen or cid not in chunk_by_id:
                    continue
                seen.add(cid)
                ordered_ids.append(cid)
                if len(ordered_ids) >= k_text:
                    break

        text_hits: list[dict[str, Any]] = []
        sims: list[float] = []
        for cid in ordered_ids[:k_text]:
            c = chunk_by_id[cid]
            dist = vec_dist.get(cid)
            if dist is not None:
                sim = max(0.0, 1.0 - min(float(dist), 1.0))
            else:
                sim = 0.12
            sims.append(sim)
            text_hits.append(
                {
                    "chunk_id": cid,
                    "document_id": c["document_id"],
                    "text": c["text"],
                    "page_start": c["page_start"],
                    "page_end": c["page_end"],
                    "score": sim,
                }
            )

        figure_hits: list[dict[str, Any]] = []
        if include_figures:
            fig_rows = all_figure_index_rows(self.db_path, document_ids)
            fig_by_id = {r["id"]: r for r in fig_rows}
            fq = self.store.query_figures(
                query,
                n_results=k_fig,
                document_ids=document_ids,
            )
            if fq["ids"] and fq["ids"][0]:
                for i, fid in enumerate(fq["ids"][0]):
                    row = fig_by_id.get(fid)
                    if not row:
                        continue
                    dist = fq["distances"][0][i] if fq.get("distances") else 0.0
                    sim = max(0.0, 1.0 - min(float(dist), 1.0))
                    figure_hits.append(
                        {
                            "asset_id": fid,
                            "document_id": row["document_id"],
                            "page": row["page"],
                            "caption_text": row["caption_text"] or "",
                            "file_path": row["file_path"],
                            "score": sim,
                        }
                    )

        conf = sum(sims) / len(sims) if sims else 0.0
        return {
            "text_hits": text_hits,
            "figure_hits": figure_hits,
            "retrieval_confidence": round(min(1.0, conf), 3),
        }


def document_titles_map(db_path) -> dict[str, str]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT id, title FROM documents").fetchall()
    return {r["id"]: r["title"] for r in rows}
