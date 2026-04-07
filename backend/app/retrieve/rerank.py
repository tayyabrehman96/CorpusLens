"""Optional cross-encoder reranking of text retrieval hits (sentence-transformers)."""

from __future__ import annotations

from typing import Any

import numpy as np

from app.config import Settings

_rerankers: dict[str, Any] = {}


def get_cross_encoder(model_name: str) -> Any:
    if model_name not in _rerankers:
        from sentence_transformers import CrossEncoder

        _rerankers[model_name] = CrossEncoder(model_name)
    return _rerankers[model_name]


def rerank_text_hits(
    query: str,
    hits: list[dict[str, Any]],
    top_k: int,
    settings: Settings,
) -> list[dict[str, Any]]:
    """
    Re-order and trim hits using a cross-encoder. Expects hits with 'text' keys.
    Scores are replaced with 0-1 normalized relevance within this candidate set.
    """
    if not settings.rerank_enabled or len(hits) <= 1:
        return hits[:top_k]

    try:
        model = get_cross_encoder(settings.rerank_model)
    except Exception:
        return hits[:top_k]

    texts = [(h.get("text") or "")[:8000] for h in hits]
    pairs = [[query, t] for t in texts]
    try:
        raw = model.predict(pairs)
    except Exception:
        return hits[:top_k]

    r = np.asarray(raw, dtype=np.float64).reshape(-1)
    rmin = float(r.min())
    rmax = float(r.max())
    if rmax - rmin < 1e-9:
        norm = np.ones_like(r) * 0.5
    else:
        norm = (r - rmin) / (rmax - rmin)

    order = np.argsort(-r)
    out: list[dict[str, Any]] = []
    for i in order[:top_k]:
        idx = int(i)
        h = dict(hits[idx])
        h["score"] = float(norm[idx])
        out.append(h)
    return out
