"""Clear SQLite library rows, on-disk files, and Chroma collections."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.config import Settings
from app.database import get_conn
from app.retrieve.vector_store import VectorStore


def clear_entire_library(
    *,
    settings: Settings,
    store: VectorStore,
    db_path: Path,
) -> None:
    store.reset_all()
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT file_path FROM documents").fetchall()
        for r in rows:
            try:
                Path(r["file_path"]).unlink(missing_ok=True)
            except OSError:
                pass
        conn.execute("DELETE FROM documents")
        conn.commit()

    files_dir = settings.data_dir / "files"
    if files_dir.exists():
        for p in files_dir.iterdir():
            try:
                if p.is_file():
                    p.unlink(missing_ok=True)
            except OSError:
                pass

    assets_root = settings.data_dir / "assets"
    if assets_root.exists():
        for sub in assets_root.iterdir():
            if sub.is_dir():
                shutil.rmtree(sub, ignore_errors=True)
