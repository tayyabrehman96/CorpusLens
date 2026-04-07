"""Optional Ollama vision captions for figure crops (ingest-time)."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx

from app.config import Settings


def ollama_vision_caption(image_path: Path, settings: Settings) -> str:
    """
    Call Ollama /api/generate with a vision-capable model and one base64 image.
    Returns empty string if OLLAMA_VISION_MODEL is unset or the request fails.
    """
    model = (settings.ollama_vision_model or "").strip()
    if not model:
        return ""
    if not image_path.is_file():
        return ""

    try:
        raw = image_path.read_bytes()
        b64 = base64.standard_b64encode(raw).decode("ascii")
    except OSError:
        return ""

    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    body = {
        "model": model,
        "prompt": (
            "Describe this figure, chart, diagram, or image in 2–4 short sentences for search indexing. "
            "Mention title, axes, units, or main trends if visible. If unreadable, say so."
        ),
        "images": [b64],
        "stream": False,
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return ""

    text = (data.get("response") or "").strip()
    return text[:4000]
