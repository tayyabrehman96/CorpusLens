"""Heuristic PDF profile: text-rich vs scanned / image-heavy (for UI hints)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz


def analyze_pdf_profile(path: Path) -> dict[str, Any]:
    doc = fitz.open(path)
    try:
        pages = len(doc)
        text_chars = 0
        image_refs = 0
        for i in range(pages):
            page = doc[i]
            text_chars += len((page.get_text("text") or "").strip())
            image_refs += len(page.get_images(full=True) or [])
    finally:
        doc.close()

    avg = text_chars / max(pages, 1)
    if pages == 0:
        kind = "empty"
        hint = "Empty PDF."
    elif avg < 35 and image_refs >= max(1, pages // 2):
        kind = "scanned_or_image_heavy"
        hint = "Likely scanned or image-heavy: little extractable text. OCR/Tesseract helps; answers may be weaker."
    elif avg < 100:
        kind = "low_text_mixed"
        hint = "Moderate text; may mix figures and body text. Summaries use available text + captions."
    else:
        kind = "text_native"
        hint = "Text-based PDF: good for search, summaries, and tables."

    return {
        "pdf_kind": kind,
        "page_count": pages,
        "text_char_estimate": text_chars,
        "embedded_image_blocks": image_refs,
        "chars_per_page_avg": round(avg, 1),
        "hint": hint,
    }


def profile_image_upload(filename: str) -> dict[str, Any]:
    return {
        "pdf_kind": "image_upload",
        "page_count": 1,
        "text_char_estimate": 0,
        "embedded_image_blocks": 0,
        "chars_per_page_avg": 0.0,
        "hint": "Image file: answers rely on OCR if Tesseract is installed.",
    }


def dumps_profile(d: dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False)
