from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

import fitz  # PyMuPDF

from app.config import Settings


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(
    full_text: str,
    page_for_char_offset: list[tuple[int, int, int]],
    chunk_size: int,
    overlap: int,
) -> list[tuple[str, int, int, int]]:
    """
    page_for_char_offset: list of (char_start, char_end, page_number) covering full_text.
    Returns list of (chunk_text, page_start, page_end, chunk_index).
    """
    if not full_text.strip():
        return []

    def char_to_page(pos: int) -> int:
        for cs, ce, p in page_for_char_offset:
            if cs <= pos < ce:
                return p
        return page_for_char_offset[-1][2] if page_for_char_offset else 1

    chunks: list[tuple[str, int, int, int]] = []
    paras = _split_paragraphs(full_text)
    buf = ""
    buf_start_char = 0
    idx = 0

    def flush_buf(end_char: int) -> None:
        nonlocal buf, buf_start_char, idx
        t = buf.strip()
        if len(t) < 30 and chunks:
            return
        if t:
            ps = char_to_page(buf_start_char)
            pe = char_to_page(max(buf_start_char, end_char - 1))
            chunks.append((t, ps, pe, idx))
            idx += 1
        buf = ""

    char_pos = 0
    for para in paras:
        if not buf:
            buf_start_char = char_pos
        if len(buf) + len(para) + 2 <= chunk_size:
            buf = (buf + "\n\n" + para).strip() if buf else para
        else:
            if buf:
                flush_buf(char_pos)
            if len(para) <= chunk_size:
                buf = para
                buf_start_char = char_pos
            else:
                start = 0
                while start < len(para):
                    end = min(start + chunk_size, len(para))
                    piece = para[start:end].strip()
                    if piece:
                        buf_start_char = char_pos + start
                        buf = piece
                        flush_buf(char_pos + end)
                        start = max(start + chunk_size - overlap, end)
                    else:
                        start = end
                buf = ""
                char_pos += len(para) + 2
                continue
        char_pos += len(para) + 2

    if buf.strip():
        flush_buf(char_pos)

    if not chunks and full_text.strip():
        ps = char_to_page(0)
        pe = char_to_page(len(full_text) - 1)
        chunks.append((full_text.strip()[:chunk_size], ps, pe, 0))

    return chunks


_CAPTION_HINTS = re.compile(
    r"(?i)\b(figure|fig\.|table|diagram|chart|plot|image)\s*[.\d\-]*\s*",
)


def _guess_caption_below(page: fitz.Page, img_rect: fitz.Rect, blocks: list) -> str:
    """blocks from page.get_text('blocks') — (x0,y0,x1,y1,text,...)"""
    ix0, iy0, ix1, iy1 = img_rect
    candidates: list[tuple[float, str]] = []
    for b in blocks:
        if len(b) < 5:
            continue
        x0, y0, x1, y1, txt = b[0], b[1], b[2], b[3], (b[4] or "").strip()
        if not txt or len(txt) < 3:
            continue
        if y0 >= iy1 - 2:
            dist = y0 - iy1
            if dist < 120:
                candidates.append((dist, txt))
        if iy0 <= y1 <= iy1 + 5 and ix0 - 20 <= x0 <= ix1 + 20:
            candidates.append((abs(y0 - iy1), txt))
    candidates.sort(key=lambda x: x[0])
    for _, txt in candidates[:3]:
        if _CAPTION_HINTS.search(txt) or len(txt) < 400:
            return txt[:800]
    return candidates[0][1][:800] if candidates else ""


def extract_figures(
    doc_path: Path,
    document_id: str,
    assets_dir: Path,
    ocr_fn: Optional[Callable[[Path], str]] = None,
) -> list[dict]:
    """
    Returns list of dicts: file_path (relative to data dir or absolute), page, caption_text, ocr_text
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    doc = fitz.open(doc_path)
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            page_num = page_index + 1
            blocks = page.get_text("blocks")
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    rects = page.get_image_rects(xref)
                except Exception:
                    rects = []
                if not rects:
                    continue
                for rect in rects:
                    try:
                        pix = page.get_pixmap(clip=rect, alpha=False)
                    except Exception:
                        continue
                    fname = f"{document_id}_p{page_num}_xref{xref}_{len(out)}.png"
                    fpath = assets_dir / fname
                    pix.save(str(fpath))
                    caption = _guess_caption_below(page, rect, blocks)
                    ocr_text = ""
                    if ocr_fn:
                        try:
                            ocr_text = ocr_fn(fpath) or ""
                        except Exception:
                            ocr_text = ""
                    index_text = " ".join(
                        filter(None, [caption, ocr_text])
                    ).strip() or f"Figure on page {page_num}"
                    out.append(
                        {
                            "file_path": str(fpath),
                            "page": page_num,
                            "caption_text": caption,
                            "ocr_text": ocr_text,
                            "index_text": index_text,
                        }
                    )
    finally:
        doc.close()
    return out


def ingest_pdf(
    pdf_path: Path,
    settings: Settings,
) -> list[tuple[str, int, int, int]]:
    """Returns text chunks as (text, page_start, page_end, chunk_index)."""
    doc = fitz.open(pdf_path)
    try:
        parts: list[str] = []
        page_offsets: list[tuple[int, int, int]] = []
        pos = 0
        for i in range(len(doc)):
            page = doc[i]
            text = page.get_text("text") or ""
            start = pos
            parts.append(text)
            if not text.endswith("\n"):
                parts.append("\n\n")
                pos += len(text) + 2
            else:
                pos += len(text)
            end = pos
            page_offsets.append((start, end, i + 1))
        full = "".join(parts)
    finally:
        doc.close()

    return chunk_text(full, page_offsets, settings.chunk_size, settings.chunk_overlap)


def ingest_pdf_with_figures(
    pdf_path: Path,
    document_id: str,
    data_dir: Path,
    settings: Settings,
    ocr_fn: Optional[Callable[[Path], str]] = None,
) -> tuple[list[tuple[str, int, int, int]], list[dict]]:
    assets_dir = data_dir / "assets" / document_id
    chunks = ingest_pdf(pdf_path, settings)
    figures = extract_figures(pdf_path, document_id, assets_dir, ocr_fn=ocr_fn)
    return chunks, figures
