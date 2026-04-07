from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import Settings


class VectorStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.chroma_path.parent.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(settings.chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._text = self._client.get_or_create_collection(
            name="text_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        self._figures = self._client.get_or_create_collection(
            name="figure_captions",
            metadata={"hnsw:space": "cosine"},
        )
        self._model: Optional[Any] = None

    @property
    def embedder(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.settings.embedding_model)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.embedder.encode(texts, normalize_embeddings=True).tolist()

    def upsert_text_chunks(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not ids:
            return
        embs = self.embed(texts)
        self._text.upsert(ids=ids, embeddings=embs, documents=texts, metadatas=metadatas)

    def upsert_figures(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not ids:
            return
        embs = self.embed(texts)
        self._figures.upsert(ids=ids, embeddings=embs, documents=texts, metadatas=metadatas)

    def query_text(
        self,
        query: str,
        n_results: int,
        document_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        emb = self.embed([query])[0]
        where: Optional[dict[str, Any]] = None
        if document_ids:
            if len(document_ids) == 1:
                where = {"document_id": document_ids[0]}
            else:
                where = {"document_id": {"$in": document_ids}}
        return self._text.query(
            query_embeddings=[emb],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    def query_figures(
        self,
        query: str,
        n_results: int,
        document_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        emb = self.embed([query])[0]
        where: Optional[dict[str, Any]] = None
        if document_ids:
            if len(document_ids) == 1:
                where = {"document_id": document_ids[0]}
            else:
                where = {"document_id": {"$in": document_ids}}
        return self._figures.query(
            query_embeddings=[emb],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    def delete_document_vectors(self, document_id: str) -> None:
        for coll in (self._text, self._figures):
            try:
                coll.delete(where={"document_id": document_id})
            except Exception:
                pass

    def reset_all(self) -> None:
        """Drop and recreate Chroma collections (full library wipe)."""
        for name in ("text_chunks", "figure_captions"):
            try:
                self._client.delete_collection(name)
            except Exception:
                pass
        self._text = self._client.get_or_create_collection(
            name="text_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        self._figures = self._client.get_or_create_collection(
            name="figure_captions",
            metadata={"hnsw:space": "cosine"},
        )
