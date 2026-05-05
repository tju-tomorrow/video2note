"""SQLite 持久化存储：转写记录 + FTS5 全文搜索。"""

import logging
import sqlite3
from pathlib import Path

import video_extract2note.config as cfg

logger = logging.getLogger(__name__)

DB_PATH = cfg.DB_PATH


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path | None = None) -> None:
    """建表（幂等）。"""
    conn = _connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                platform TEXT,
                title TEXT,
                engine TEXT,
                raw_text TEXT,
                formatted_text TEXT NOT NULL,
                duration_seconds REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_records_url ON records(url);
            CREATE INDEX IF NOT EXISTS idx_records_created ON records(created_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
                title, raw_text, formatted_text,
                content='records', content_rowid='id',
                tokenize='trigram'
            );
        """)
        conn.commit()
        logger.debug("数据库初始化完成: %s", db_path or DB_PATH)
    finally:
        conn.close()


def _sync_fts(conn: sqlite3.Connection, row_id: int,
              title: str | None, raw_text: str | None, formatted_text: str) -> None:
    """同步 FTS5 索引。"""
    conn.execute(
        "INSERT INTO records_fts(rowid, title, raw_text, formatted_text) VALUES (?, ?, ?, ?)",
        (row_id, title or "", raw_text or "", formatted_text),
    )


def save_record(
    url: str,
    source_type: str,
    formatted_text: str,
    platform: str = "",
    title: str = "",
    engine: str = "",
    raw_text: str = "",
    duration_seconds: float | None = None,
    db_path: Path | None = None,
) -> int:
    """插入一条记录，返回 id。"""
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO records (url, source_type, platform, title, engine, raw_text, formatted_text, duration_seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, source_type, platform or None, title or None, engine or None,
             raw_text or None, formatted_text, duration_seconds),
        )
        row_id = cur.lastrowid
        _sync_fts(conn, row_id, title, raw_text, formatted_text)
        conn.commit()
        logger.info("记录已保存 id=%d url=%s", row_id, url)
        return row_id
    finally:
        conn.close()


def get_record_by_id(record_id: int, db_path: Path | None = None) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_record_by_url(url: str, db_path: Path | None = None) -> dict | None:
    """按 URL 查最新记录。"""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM records WHERE url = ? ORDER BY created_at DESC LIMIT 1",
            (url,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def search_records(query: str, limit: int = 10, db_path: Path | None = None) -> list[dict]:
    """FTS5 全文搜索。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """SELECT r.* FROM records r
               JOIN records_fts fts ON r.id = fts.rowid
               WHERE records_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_records(limit: int = 20, offset: int = 0, db_path: Path | None = None) -> list[dict]:
    """历史记录列表（按时间倒序）。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM records ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_record(record_id: int, db_path: Path | None = None) -> bool:
    """删除记录及其 FTS 索引。"""
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM records_fts WHERE rowid = ?", (record_id,))
        cur = conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
