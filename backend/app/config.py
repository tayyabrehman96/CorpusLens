from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = Path(__file__).resolve().parent.parent / "data"
    database_url: str = "sqlite:///./data/app.db"  # relative to cwd when using sqlite
    chroma_path: Path = Path(__file__).resolve().parent.parent / "data" / "chroma"
    # LLM_BACKEND=ollama (HTTP to Ollama) or hf_local (Hugging Face model under data/hf_hub).
    llm_backend: str = "hf_local"
    # Local Ollama default for this app only (override with OLLAMA_BASE_URL).
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    # Hugging Face model id or absolute path to a folder with config.json (first run downloads into data/hf_hub).
    hf_local_model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    # Input truncation (tokens) for CPU speed; must leave room for hf_max_new_tokens.
    hf_context_tokens: int = 2048
    hf_max_new_tokens: int = 384
    hf_do_sample: bool = True
    hf_temperature: float = 0.7
    hf_top_p: float = 0.9
    hf_trust_remote_code: bool = False
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Origins allowed to call this API (this app’s Next.js dev server by default).
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Optional: public base URL of *this* FastAPI instance for Markdown export links (API_PUBLIC_URL).
    api_public_url: str = ""
    chunk_size: int = 1200
    chunk_overlap: int = 200
    retrieve_k_text: int = 12
    retrieve_k_figures: int = 4
    bm25_k: int = 20
    rrf_k: int = 60
    # Cross-encoder reranking after hybrid fusion (downloads ~90MB model on first use).
    rerank_enabled: bool = False
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_pool_multiplier: int = 4
    # Full-page Tesseract OCR for PDFs classified scan-heavy / low-text (requires tesseract on PATH).
    pdf_ocr_pages_enabled: bool = True
    pdf_ocr_max_pages: int = 80
    pdf_ocr_dpi_scale: float = 2.0
    # Optional: Ollama vision model tag for figure captions at ingest (empty = disabled).
    ollama_vision_model: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
