from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.models.schemas import ExportMarkdownBody

router = APIRouter(prefix="/api/export", tags=["export"])


@router.post("/markdown", response_class=PlainTextResponse)
def export_markdown(
    body: ExportMarkdownBody,
    settings: Settings = Depends(get_settings),
):
    lines = [
        f"# {body.title}",
        "",
        "## Answer",
        "",
        body.answer.strip(),
        "",
        "## Evidence — text",
        "",
    ]
    for c in body.evidence_chunks:
        lines.append(
            f"- **{c.document_title}** (p.{c.page_start}" + (f"–{c.page_end}" if c.page_end != c.page_start else "") + ")"
        )
        lines.append(f"  > {c.text[:800].replace(chr(10), ' ')}")
        lines.append("")
    if body.evidence_figures:
        lines.append("## Evidence — figures")
        lines.append("")
        base = (settings.api_public_url or "").rstrip("/")
        for f in body.evidence_figures:
            raw = f.image_url.strip()
            if raw.startswith("http://") or raw.startswith("https://"):
                url = raw
            else:
                path = raw if raw.startswith("/") else f"/{raw}"
                url = f"{base}{path}" if base else path
            lines.append(f"- **{f.document_title}** p.{f.page}: {f.caption_text or '(no caption)'}")
            lines.append(f"  - Image: `{url}`")
            if not (raw.startswith("http://") or raw.startswith("https://")) and not base:
                lines.append("  - _(Set API_PUBLIC_URL in backend `.env` for absolute image links.)_")
            lines.append("")
    return "\n".join(lines)
