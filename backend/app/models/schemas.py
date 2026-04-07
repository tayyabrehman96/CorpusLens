from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    title: str
    original_filename: str
    mime: str
    created_at: str
    chunk_count: int = Field(0, description="Number of text chunks indexed for retrieval.")
    asset_count: int = Field(0, description="Number of stored assets (e.g. figure crops).")
    ingest_profile: Optional[dict[str, Any]] = Field(
        default=None,
        description="PDF/image heuristic profile (kind, pages, hints) when available.",
    )


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str
    document_ids: Optional[list[str]] = None
    mode: Literal[
        "default",
        "summary",
        "limitations",
        "methodology",
        "compare",
        "implementation",
        "future_work",
    ] = "default"
    retrieve_k: Optional[int] = Field(
        default=None,
        ge=4,
        le=40,
        description="Override number of text chunks to retrieve (default from server settings).",
    )
    detail_level: Literal["concise", "balanced", "deep"] = "balanced"
    fast_mode: bool = Field(
        default=False,
        description="Skips figure retrieval and caps context for quicker answers.",
    )


class EvidenceChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    text: str
    page_start: int
    page_end: int
    score: Optional[float] = None


class EvidenceFigure(BaseModel):
    asset_id: str
    document_id: str
    document_title: str
    page: int
    caption_text: str
    image_url: str
    score: Optional[float] = None


class ChatResponseMeta(BaseModel):
    retrieval_confidence: float = Field(description="Heuristic 0-1 from mean similarity")
    mode: str


class ExportMarkdownBody(BaseModel):
    title: str = "Research notes"
    answer: str
    evidence_chunks: list[EvidenceChunk] = []
    evidence_figures: list[EvidenceFigure] = []
