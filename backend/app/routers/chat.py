from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.generate.ollama import build_messages, stream_ollama
from app.models.schemas import ChatRequest
from app.database import library_stats
from app.retrieve.hybrid import HybridRetriever, document_titles_map
from app.retrieve.vector_store import VectorStore

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _llm_backend(settings: Settings) -> str:
    b = (settings.llm_backend or "ollama").strip().lower()
    return b if b in ("ollama", "hf_local") else "ollama"


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    settings: Settings = Depends(get_settings),
):
    db_path = settings.data_dir / "app.db"
    store = VectorStore(settings)
    retriever = HybridRetriever(settings, store, db_path)
    titles = document_titles_map(db_path)

    doc_ids = body.document_ids
    if doc_ids is not None and len(doc_ids) == 0:
        doc_ids = None
    # Drop unknown IDs (e.g. stale UI selection after replace-library upload)
    if doc_ids:
        doc_ids = [d for d in doc_ids if d in titles]
        if not doc_ids:
            doc_ids = None

    k_text = body.retrieve_k if body.retrieve_k is not None else settings.retrieve_k_text
    k_fig = settings.retrieve_k_figures
    if body.mode == "compare" and doc_ids and len(doc_ids) >= 2:
        k_text = min(24, k_text * 2)
        k_fig = min(8, k_fig * 2)
    include_figures: bool | None = None
    if body.fast_mode:
        k_text = min(k_text, 8)
        k_fig = 0
        include_figures = False

    res = retriever.retrieve(
        body.message,
        doc_ids,
        include_figures,
        top_k_text=k_text,
        top_k_figures=k_fig,
    )

    if not res["text_hits"] and not res["figure_hits"]:
        doc_count, chunk_count = library_stats(db_path)

        if doc_count == 0:
            hint = (
                "Your library is empty. Use **Upload** (left panel) to add PDFs or images, "
                "wait until they appear under Library, then ask again."
            )
        elif chunk_count == 0:
            hint = (
                f"You have {doc_count} file(s) in the library but **no text chunks** were stored "
                "(extraction may have failed). Remove those entries and re-upload, or use a different PDF."
            )
        elif doc_ids is not None:
            hint = (
                "No chunks match the **selected documents** (or those files have no extractable text). "
                "Untick all checkboxes to search the **whole library**, or upload richer PDFs."
            )
        else:
            hint = (
                f"The index looks inconsistent ({doc_count} docs, {chunk_count} chunks but nothing retrieved). "
                "Try deleting the document and uploading again, or restart the API after clearing "
                "`backend/data/chroma` if you moved machines."
            )

        async def empty_gen():
            yield _sse(
                {
                    "type": "meta",
                    "retrieval_confidence": 0.0,
                    "mode": body.mode,
                    "library_documents": doc_count,
                    "library_chunks": chunk_count,
                }
            )
            yield _sse(
                {
                    "type": "token",
                    "content": hint,
                }
            )
            yield _sse({"type": "done", "evidence": {"chunks": [], "figures": []}})

        return StreamingResponse(
            empty_gen(),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    messages = build_messages(
        body.message,
        body.mode,
        res["text_hits"],
        res["figure_hits"],
        titles,
        detail_level=body.detail_level,
    )

    async def event_gen():
        yield _sse(
            {
                "type": "meta",
                "retrieval_confidence": res["retrieval_confidence"],
                "mode": body.mode,
            }
        )
        try:
            backend = _llm_backend(settings)
            if backend == "hf_local":
                from app.generate.hf_local import stream_hf_local

                yield _sse(
                    {
                        "type": "token",
                        "content": (
                            "⏳ Local model on CPU: loading weights and generating can take "
                            "1–3 minutes the first time. Text will appear below as tokens arrive.\n\n"
                        ),
                    }
                )
                async for piece in stream_hf_local(settings, messages):
                    yield _sse({"type": "token", "content": piece})
            else:
                async for piece in stream_ollama(settings, messages):
                    yield _sse({"type": "token", "content": piece})
        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})
            return

        chunks_out = [
            {
                "chunk_id": h["chunk_id"],
                "document_id": h["document_id"],
                "document_title": titles.get(h["document_id"], "Unknown"),
                "text": h["text"][:4000],
                "page_start": h["page_start"],
                "page_end": h["page_end"],
                "score": h.get("score"),
            }
            for h in res["text_hits"]
        ]
        figs_out = [
            {
                "asset_id": f["asset_id"],
                "document_id": f["document_id"],
                "document_title": titles.get(f["document_id"], "Unknown"),
                "page": f["page"],
                "caption_text": f.get("caption_text") or "",
                "image_url": f"/api/assets/{f['asset_id']}/image",
                "score": f.get("score"),
            }
            for f in res["figure_hits"]
        ]
        yield _sse({"type": "done", "evidence": {"chunks": chunks_out, "figures": figs_out}})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/health/llm")
async def llm_health(settings: Settings = Depends(get_settings)):
    """Reports which LLM backend is configured (Ollama HTTP vs Hugging Face under data/hf_hub)."""
    b = _llm_backend(settings)
    if b == "hf_local":
        return {
            "ok": True,
            "backend": "hf_local",
            "model": settings.hf_local_model,
            "cache": str((settings.data_dir / "hf_hub").resolve()),
        }
    import httpx

    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            r.raise_for_status()
        return {"ok": True, "backend": "ollama", "model": settings.ollama_model, "ollama_url": url}
    except Exception as e:
        raise HTTPException(503, f"Ollama unreachable: {e}")


@router.get("/health/ollama")
async def ollama_health(settings: Settings = Depends(get_settings)):
    """Deprecated alias; prefer GET /api/chat/health/llm"""
    return await llm_health(settings)
