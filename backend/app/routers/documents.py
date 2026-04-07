from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.database import delete_document, get_document, list_documents
from app.models.schemas import DocumentOut
from app.retrieve.vector_store import VectorStore
from app.services.ingest_service import ingest_uploaded_file, reindex_document
from app.services.library_wipe import clear_entire_library

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_store(settings: Settings) -> VectorStore:
    return VectorStore(settings)


def _row_to_document_out(row: dict) -> DocumentOut:
    profile = None
    raw = row.get("ingest_meta")
    if raw:
        try:
            profile = json.loads(raw)
        except json.JSONDecodeError:
            profile = None
    return DocumentOut(
        id=row["id"],
        title=row["title"],
        original_filename=row["original_filename"],
        mime=row["mime"],
        created_at=row["created_at"],
        chunk_count=int(row.get("chunk_count") or 0),
        asset_count=int(row.get("asset_count") or 0),
        ingest_profile=profile,
    )


@router.get("", response_model=list[DocumentOut])
def api_list_documents(settings: Settings = Depends(get_settings)):
    db_path = settings.data_dir / "app.db"
    return [_row_to_document_out(r) for r in list_documents(db_path)]


@router.post("/library/reset")
def api_reset_library(settings: Settings = Depends(get_settings)):
    """Remove all documents, chunks, assets, vectors, and stored files."""
    db_path = settings.data_dir / "app.db"
    store = _get_store(settings)
    clear_entire_library(settings=settings, store=store, db_path=db_path)
    return {"ok": True}


@router.post("/upload", response_model=DocumentOut)
async def api_upload(
    file: UploadFile = File(...),
    replace_library: bool = Query(
        False,
        description="If true, wipes the entire library before ingesting this file.",
    ),
    settings: Settings = Depends(get_settings),
):
    db_path = settings.data_dir / "app.db"
    if not file.filename:
        raise HTTPException(400, "No filename")
    mime = file.content_type or "application/octet-stream"
    low = file.filename.lower()
    is_pdf_name = low.endswith(".pdf")
    is_pdf_mime = mime == "application/pdf"
    is_image_mime = mime.startswith("image/")
    if not (is_pdf_mime or is_pdf_name or is_image_mime):
        raise HTTPException(400, "Only PDF or image uploads are supported")

    tmp = settings.data_dir / "tmp_upload"
    tmp.mkdir(parents=True, exist_ok=True)
    dest = tmp / file.filename
    try:
        content = await file.read()
        if not content:
            raise HTTPException(400, "Empty file — choose a non-empty PDF or image.")
        if is_pdf_name or is_pdf_mime:
            if len(content) < 4 or content[:4] != b"%PDF":
                raise HTTPException(
                    400,
                    "This file is not a valid PDF (missing %PDF header). "
                    "If it is a PDF, re-save or export it from your reader; otherwise pick a supported format.",
                )
        dest.write_bytes(content)
        store = _get_store(settings)
        try:
            doc_id = ingest_uploaded_file(
                file_path=dest,
                original_filename=file.filename,
                mime=mime,
                settings=settings,
                store=store,
                db_path=db_path,
                replace_library=replace_library,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    finally:
        if dest.exists():
            dest.unlink()

    row = get_document(db_path, doc_id)
    if not row:
        raise HTTPException(500, "Ingest failed")
    return _row_to_document_out(row)


@router.delete("/{doc_id}")
def api_delete(doc_id: str, settings: Settings = Depends(get_settings)):
    db_path = settings.data_dir / "app.db"
    doc = get_document(db_path, doc_id)
    if not doc:
        raise HTTPException(404, "Not found")
    store = _get_store(settings)
    store.delete_document_vectors(doc_id)
    delete_document(db_path, doc_id)
    try:
        Path(doc["file_path"]).unlink(missing_ok=True)
    except Exception:
        pass
    adir = settings.data_dir / "assets" / doc_id
    if adir.exists():
        shutil.rmtree(adir, ignore_errors=True)
    return {"ok": True}


@router.post("/{doc_id}/reindex")
def api_reindex(doc_id: str, settings: Settings = Depends(get_settings)):
    db_path = settings.data_dir / "app.db"
    store = _get_store(settings)
    adir = settings.data_dir / "assets" / doc_id
    if adir.exists():
        shutil.rmtree(adir, ignore_errors=True)
    try:
        reindex_document(doc_id, settings, store, db_path)
    except FileNotFoundError:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.get("/{doc_id}/file")
def api_serve_file(doc_id: str, settings: Settings = Depends(get_settings)):
    db_path = settings.data_dir / "app.db"
    doc = get_document(db_path, doc_id)
    if not doc:
        raise HTTPException(404, "Not found")
    p = Path(doc["file_path"])
    if not p.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(
        path=str(p),
        filename=doc["original_filename"],
        media_type=doc["mime"] or "application/octet-stream",
    )
