import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional


def _migrate_documents_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(documents)")
    cols = {r[1] for r in cur.fetchall()}
    if "ingest_meta" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN ingest_meta TEXT")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                mime TEXT NOT NULL,
                created_at TEXT NOT NULL,
                ingest_meta TEXT
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                text TEXT NOT NULL,
                page_start INTEGER NOT NULL,
                page_end INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                page INTEGER NOT NULL,
                caption_text TEXT,
                ocr_text TEXT,
                description TEXT,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
            CREATE INDEX IF NOT EXISTS idx_assets_document ON assets(document_id);
            """
        )
        _migrate_documents_columns(conn)
        conn.commit()


@contextmanager
def get_conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def insert_document(
    db_path: Path,
    title: str,
    original_filename: str,
    file_path: str,
    mime: str,
    ingest_meta: Optional[str] = None,
) -> str:
    doc_id = str(uuid.uuid4())
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO documents (id, title, original_filename, file_path, mime, created_at, ingest_meta)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, title, original_filename, file_path, mime, _utc_now(), ingest_meta),
        )
        conn.commit()
    return doc_id


def update_document_ingest_meta(db_path: Path, doc_id: str, ingest_meta: Optional[str]) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE documents SET ingest_meta = ? WHERE id = ?",
            (ingest_meta, doc_id),
        )
        conn.commit()


def list_documents(db_path: Path) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.title, d.original_filename, d.mime, d.created_at, d.ingest_meta,
                   (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunk_count,
                   (SELECT COUNT(*) FROM assets a WHERE a.document_id = d.id) AS asset_count
            FROM documents d
            ORDER BY d.created_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def count_chunks_for_document(db_path: Path, document_id: str) -> int:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (document_id,)
        ).fetchone()
    return int(row[0]) if row else 0


def count_assets_for_document(db_path: Path, document_id: str) -> int:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM assets WHERE document_id = ?", (document_id,)
        ).fetchone()
    return int(row[0]) if row else 0


def get_document(db_path: Path, doc_id: str) -> Optional[dict[str, Any]]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def delete_document(db_path: Path, doc_id: str) -> None:
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM assets WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()


def insert_chunks(
    db_path: Path,
    document_id: str,
    chunks: list[tuple[str, int, int, int]],
) -> list[str]:
    """chunks: (text, page_start, page_end, chunk_index)"""
    ids: list[str] = []
    with get_conn(db_path) as conn:
        for text, ps, pe, idx in chunks:
            cid = str(uuid.uuid4())
            ids.append(cid)
            conn.execute(
                """
                INSERT INTO chunks (id, document_id, text, page_start, page_end, chunk_index)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (cid, document_id, text, ps, pe, idx),
            )
        conn.commit()
    return ids


def insert_asset(
    db_path: Path,
    document_id: str,
    asset_type: str,
    file_path: str,
    page: int,
    caption_text: Optional[str],
    ocr_text: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    aid = str(uuid.uuid4())
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO assets (id, document_id, asset_type, file_path, page, caption_text, ocr_text, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (aid, document_id, asset_type, file_path, page, caption_text or "", ocr_text or "", description or ""),
        )
        conn.commit()
    return aid


def list_assets_for_document(db_path: Path, document_id: str) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM assets WHERE document_id = ? ORDER BY page, id", (document_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_chunk(db_path: Path, chunk_id: str) -> Optional[dict[str, Any]]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
    return dict(row) if row else None


def get_asset(db_path: Path, asset_id: str) -> Optional[dict[str, Any]]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return dict(row) if row else None


def all_chunks_for_retrieval(db_path: Path, document_ids: Optional[list[str]] = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        if document_ids:
            q = "SELECT id, document_id, text, page_start, page_end FROM chunks WHERE document_id IN ({})".format(
                ",".join("?" * len(document_ids))
            )
            rows = conn.execute(q, document_ids).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, document_id, text, page_start, page_end FROM chunks"
            ).fetchall()
    return [dict(r) for r in rows]


def all_figure_index_rows(db_path: Path, document_ids: Optional[list[str]] = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        if document_ids:
            q = """
            SELECT id, document_id, page, caption_text, ocr_text, description, file_path
            FROM assets WHERE asset_type = 'figure' AND document_id IN ({})
            """.format(",".join("?" * len(document_ids)))
            rows = conn.execute(q, document_ids).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, document_id, page, caption_text, ocr_text, description, file_path
                FROM assets WHERE asset_type = 'figure'
                """
            ).fetchall()
    return [dict(r) for r in rows]


def clear_chunks_and_assets_for_document(db_path: Path, document_id: str) -> None:
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM assets WHERE document_id = ?", (document_id,))
        conn.commit()


def library_stats(db_path: Path) -> tuple[int, int]:
    """Returns (document_count, chunk_count)."""
    with get_conn(db_path) as conn:
        doc_n = int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
        chunk_n = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    return doc_n, chunk_n
