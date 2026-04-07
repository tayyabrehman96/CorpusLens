from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.database import get_asset

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/{asset_id}/image")
def serve_asset_image(asset_id: str, settings: Settings = Depends(get_settings)):
    db_path = settings.data_dir / "app.db"
    row = get_asset(db_path, asset_id)
    if not row:
        raise HTTPException(404, "Not found")
    p = Path(row["file_path"])
    if not p.exists():
        raise HTTPException(404, "File missing")
    media = "image/png"
    if p.suffix.lower() in (".jpg", ".jpeg"):
        media = "image/jpeg"
    elif p.suffix.lower() == ".webp":
        media = "image/webp"
    return FileResponse(path=str(p), media_type=media)
