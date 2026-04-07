from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from app.config import Settings
from app.database import (
    clear_chunks_and_assets_for_document,
    count_assets_for_document,
    count_chunks_for_document,
    delete_document,
    insert_asset,
    insert_chunks,
    insert_document,
    update_document_ingest_meta,
)
from app.ingest.pdf import ingest_pdf_with_figures
from app.ingest.pdf_profile import analyze_pdf_profile, dumps_profile, profile_image_upload
from app.retrieve.vector_store import VectorStore
from app.services.library_wipe import clear_entire_library


def _safe_name(name: str) -> str:
    base = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE)[:180]
    return base or "upload"


def _cleanup_failed_ingest(
    doc_id: str,
    stored: Path,
    settings: Settings,
    store: VectorStore,
    db_path: Path,
) -> None:
    store.delete_document_vectors(doc_id)
    delete_document(db_path, doc_id)
    adir = settings.data_dir / "assets" / doc_id
    if adir.exists():
        shutil.rmtree(adir, ignore_errors=True)
    try:
        stored.unlink(missing_ok=True)
    except OSError:
        pass


def _ingest_profile_json(stored: Path, mime: str, original_filename: str) -> str | None:
    low = original_filename.lower()
    if mime == "application/pdf" or low.endswith(".pdf"):
        return dumps_profile(analyze_pdf_profile(stored))
    if mime.startswith("image/"):
        return dumps_profile(profile_image_upload(original_filename))
    return None


def _try_ocr(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image

        return (pytesseract.image_to_string(Image.open(path)) or "").strip()[:4000]
    except Exception:
        return ""


def _ingest_physical_file(
    doc_id: str,
    stored: Path,
    title: str,
    mime: str,
    original_filename: str,
    settings: Settings,
    store: VectorStore,
    db_path: Path,
) -> None:
    if mime == "application/pdf" or original_filename.lower().endswith(".pdf"):
        chunks_tuples, figures = ingest_pdf_with_figures(
            stored, doc_id, settings.data_dir, settings, ocr_fn=_try_ocr
        )
        chunk_rows = [(t, ps, pe, ix) for t, ps, pe, ix in chunks_tuples]
        chunk_ids = insert_chunks(db_path, doc_id, chunk_rows)
        metas = [
            {
                "document_id": doc_id,
                "page_start": ps,
                "page_end": pe,
                "chunk_index": ix,
            }
            for (_, ps, pe, ix) in chunks_tuples
        ]
        store.upsert_text_chunks(
            ids=chunk_ids,
            texts=[c[0] for c in chunks_tuples],
            metadatas=metas,
        )
        for fig in figures:
            aid = insert_asset(
                db_path,
                doc_id,
                "figure",
                fig["file_path"],
                fig["page"],
                fig.get("caption_text"),
                fig.get("ocr_text"),
                None,
            )
            idx_text = fig.get("index_text") or fig.get("caption_text") or ""
            store.upsert_figures(
                ids=[aid],
                texts=[idx_text],
                metadatas=[{"document_id": doc_id, "page": int(fig["page"])}],
            )
    elif mime.startswith("image/"):
        assets_dir = settings.data_dir / "assets" / doc_id
        assets_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(original_filename).suffix or ".png"
        dest = assets_dir / f"upload{ext}"
        shutil.copy2(stored, dest)
        ocr = _try_ocr(dest)
        body = f"User-uploaded image: {title}.\n{ocr}".strip()
        chunk_ids = insert_chunks(db_path, doc_id, [(body, 1, 1, 0)])
        store.upsert_text_chunks(
            ids=chunk_ids,
            texts=[body],
            metadatas=[{"document_id": doc_id, "page_start": 1, "page_end": 1, "chunk_index": 0}],
        )
        aid = insert_asset(
            db_path,
            doc_id,
            "figure",
            str(dest),
            1,
            title,
            ocr,
            None,
        )
        store.upsert_figures(
            ids=[aid],
            texts=[(title + "\n" + ocr).strip() or title],
            metadatas=[{"document_id": doc_id, "page": 1}],
        )
    else:
        raise ValueError(f"Unsupported type: {mime}")


def ingest_uploaded_file(
    *,
    file_path: Path,
    original_filename: str,
    mime: str,
    settings: Settings,
    store: VectorStore,
    db_path: Path,
    replace_library: bool = False,
) -> str:
    """Persists document, chunks, vectors. Returns document id."""
    if replace_library:
        clear_entire_library(settings=settings, store=store, db_path=db_path)

    title = Path(original_filename).stem
    stored = settings.data_dir / "files" / f"{uuid.uuid4()}_{_safe_name(original_filename)}"
    stored.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, stored)

    meta_json = _ingest_profile_json(stored, mime, original_filename)
    doc_id = insert_document(
        db_path,
        title=title,
        original_filename=original_filename,
        file_path=str(stored),
        mime=mime,
        ingest_meta=meta_json,
    )
    try:
        _ingest_physical_file(
            doc_id, stored, title, mime, original_filename, settings, store, db_path
        )
    except Exception:
        _cleanup_failed_ingest(doc_id, stored, settings, store, db_path)
        raise

    low = original_filename.lower()
    is_pdf = mime == "application/pdf" or low.endswith(".pdf")
    if is_pdf:
        n_chunks = count_chunks_for_document(db_path, doc_id)
        n_assets = count_assets_for_document(db_path, doc_id)
        if n_chunks == 0 and n_assets == 0:
            _cleanup_failed_ingest(doc_id, stored, settings, store, db_path)
            raise ValueError(
                "This PDF produced no searchable text or figure crops. "
                "It may be empty, encrypted, or image-only with no extractable regions. "
                "Try a different export, or convert scans to a text PDF / upload images."
            )
    return doc_id


def reindex_document(
    doc_id: str,
    settings: Settings,
    store: VectorStore,
    db_path: Path,
) -> None:
    from app.database import get_document

    doc = get_document(db_path, doc_id)
    if not doc:
        raise FileNotFoundError(doc_id)
    store.delete_document_vectors(doc_id)
    clear_chunks_and_assets_for_document(db_path, doc_id)
    p = Path(doc["file_path"])
    title = Path(doc["original_filename"]).stem
    _ingest_physical_file(
        doc_id,
        p,
        title,
        doc["mime"],
        doc["original_filename"],
        settings,
        store,
        db_path,
    )
    refreshed = _ingest_profile_json(p, doc["mime"], doc["original_filename"])
    if refreshed:
        update_document_ingest_meta(db_path, doc_id, refreshed)
