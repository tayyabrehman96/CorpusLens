from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

import httpx

from app.config import Settings


MODE_INSTRUCTIONS: dict[str, str] = {
    "default": "Answer clearly and cite sources for every factual claim.",
    "summary": (
        "Write a professional executive brief in Markdown. Use headings: ## Overview, ## Key points, "
        "## Methods / setup (if present), ## Results & data, ## Limitations & caveats, ## Open questions. "
        "Where the evidence contains comparable numbers, metrics, or categories, summarize them in a "
        "**Markdown pipe table** (not ASCII art). Call out if the source PDF appears scanned or low-text. "
        "Every factual claim must cite [DocumentTitle p.X]. Stay grounded in the evidence."
    ),
    "limitations": "Focus on limitations, threats to validity, and weaknesses mentioned or implied in the evidence. Cite sources.",
    "methodology": "Explain the methodology and experimental setup strictly from the evidence. Cite page references.",
    "compare": "Compare and contrast across the provided sources. Use Markdown tables when comparing items side-by-side. Cite each point.",
    "implementation": "Focus on implementation-relevant details: architectures, hyperparameters, datasets, metrics, and reproducibility hints from the text.",
    "future_work": "Suggest future work directions grounded in gaps or explicit future-work statements in the evidence. Label speculation clearly.",
}

DETAIL_INSTRUCTIONS: dict[str, str] = {
    "concise": "Keep the answer short: tight bullets, minimal prose, no redundant tables unless essential.",
    "balanced": "Balance depth and readability; use structure (headings/bullets) when it helps.",
    "deep": "Be thorough: nested structure, explicit reasoning, rich Markdown (headings, bullet lists, tables for comparisons).",
}


def build_system_prompt(mode: str, detail_level: str = "balanced") -> str:
    extra = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["default"])
    depth = DETAIL_INSTRUCTIONS.get(detail_level, DETAIL_INSTRUCTIONS["balanced"])
    return f"""You are CorpusLens, a research assistant. Use ONLY the provided context to answer.
{extra}
Depth: {depth}
Citation format: use square brackets like [DocumentTitle p.X] matching the context labels.
If the context is insufficient, say what is missing rather than inventing."""


def format_context(
    text_hits: list[dict[str, Any]],
    figure_hits: list[dict[str, Any]],
    titles: dict[str, str],
) -> str:
    parts: list[str] = []
    for i, h in enumerate(text_hits, 1):
        title = titles.get(h["document_id"], "Unknown")
        ps, pe = h["page_start"], h["page_end"]
        pg = ps if ps == pe else f"{ps}-{pe}"
        parts.append(
            f"[{title} p.{pg}] (chunk {i})\n{h['text']}\n"
        )
    for j, f in enumerate(figure_hits, 1):
        title = titles.get(f["document_id"], "Unknown")
        cap = f["caption_text"] or "(no caption)"
        parts.append(
            f"[FIGURE {j}: {title} p.{f['page']}]\nCaption / index text: {cap}\n"
        )
    return "\n---\n".join(parts) if parts else "(No retrieved context.)"


def build_messages(
    user_question: str,
    mode: str,
    text_hits: list[dict[str, Any]],
    figure_hits: list[dict[str, Any]],
    titles: dict[str, str],
    detail_level: str = "balanced",
) -> list[dict[str, str]]:
    ctx = format_context(text_hits, figure_hits, titles)
    return [
        {"role": "system", "content": build_system_prompt(mode, detail_level=detail_level)},
        {
            "role": "user",
            "content": f"Context from user library:\n\n{ctx}\n\nQuestion: {user_question}",
        },
    ]


def messages_to_single_prompt(messages: list[dict[str, str]]) -> str:
    """Build one prompt for Ollama /api/generate (older servers or proxies without /api/chat)."""
    parts: list[str] = []
    for m in messages:
        role, content = m.get("role", "user"), m.get("content", "")
        label = role.upper()
        parts.append(f"[{label}]\n{content}")
    return "\n\n".join(parts)


async def stream_ollama(
    settings: Settings,
    messages: list[dict[str, str]],
    model: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Stream from Ollama using POST /api/generate only (not /api/chat).
    Some installs, proxies, or older builds return 404 on /api/chat; /api/generate is the stable API.
    """
    base = settings.ollama_base_url.rstrip("/")
    m = model or settings.ollama_model
    prompt = messages_to_single_prompt(messages)
    gen_url = f"{base}/api/generate"
    gen_body = {"model": m, "prompt": prompt, "stream": True}

    async with httpx.AsyncClient(timeout=600.0) as client:
        async with client.stream("POST", gen_url, json=gen_body) as resp:
            if resp.status_code == 404:
                await resp.aread()
                raise RuntimeError(
                    f"Ollama returned 404 for POST {gen_url}. "
                    f"Confirm Ollama is running and GET {base}/api/tags works. "
                    "Or set LLM_BACKEND=hf_local in backend/.env to use the bundled Hugging Face path."
                )
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = data.get("response", "")
                if piece:
                    yield piece
                if data.get("done"):
                    break
