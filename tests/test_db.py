"""db.py 模块测试。"""

import sqlite3
import time
from pathlib import Path

import pytest

from video_extract2note.db import (
    delete_record,
    get_record_by_id,
    get_record_by_url,
    init_db,
    list_records,
    save_record,
    search_records,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def initialized_db(db_path: Path) -> Path:
    init_db(db_path)
    return db_path


def _insert_sample(db_path: Path, **overrides) -> int:
    defaults = dict(
        url="https://www.douyin.com/video/123",
        source_type="video",
        formatted_text="这是一段格式化后的转写文本",
        platform="douyin",
        title="测试视频",
        engine="mimo",
        raw_text="这是一段转写文本",
        duration_seconds=120.5,
    )
    defaults.update(overrides)
    return save_record(**defaults, db_path=db_path)


# ── 建表 ──

def test_init_db_creates_tables(db_path: Path):
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert "records" in tables
    assert "records_fts" in tables


def test_init_db_idempotent(db_path: Path):
    init_db(db_path)
    init_db(db_path)  # 不应报错


# ── 写入 ──

def test_save_record_returns_id(initialized_db: Path):
    rid = _insert_sample(initialized_db)
    assert isinstance(rid, int)
    assert rid > 0


def test_save_record_minimal(initialized_db: Path):
    rid = save_record(
        url="https://example.com",
        source_type="web",
        formatted_text="hello",
        db_path=initialized_db,
    )
    assert rid > 0


# ── 读取 ──

def test_get_record_by_id(initialized_db: Path):
    rid = _insert_sample(initialized_db)
    r = get_record_by_id(rid, db_path=initialized_db)
    assert r is not None
    assert r["id"] == rid
    assert r["url"] == "https://www.douyin.com/video/123"
    assert r["platform"] == "douyin"
    assert r["engine"] == "mimo"
    assert r["duration_seconds"] == 120.5


def test_get_record_by_id_not_found(initialized_db: Path):
    assert get_record_by_id(9999, db_path=initialized_db) is None


def test_get_record_by_url(initialized_db: Path):
    _insert_sample(initialized_db)
    r = get_record_by_url("https://www.douyin.com/video/123", db_path=initialized_db)
    assert r is not None
    assert r["platform"] == "douyin"


def test_get_record_by_url_not_found(initialized_db: Path):
    assert get_record_by_url("https://not.exist", db_path=initialized_db) is None


# ── 列表 ──

def test_list_records_order(initialized_db: Path):
    _insert_sample(initialized_db, url="https://a.com", formatted_text="first")
    time.sleep(1.1)  # datetime('now') 秒级精度，需要跨秒
    _insert_sample(initialized_db, url="https://b.com", formatted_text="second")
    results = list_records(db_path=initialized_db)
    assert len(results) == 2
    # 按时间倒序，最新在前
    assert results[0]["formatted_text"] == "second"


def test_list_records_pagination(initialized_db: Path):
    for i in range(5):
        _insert_sample(initialized_db, url=f"https://{i}.com", formatted_text=f"text{i}")
    page = list_records(limit=2, offset=2, db_path=initialized_db)
    assert len(page) == 2


# ── 全文搜索 ──

def test_search_records_basic(initialized_db: Path):
    _insert_sample(initialized_db, raw_text="React Fiber 是前端框架的核心", formatted_text="Fiber 架构详解")
    _insert_sample(initialized_db, url="https://b.com", raw_text="Python 后端开发", formatted_text="Django 教程")
    results = search_records("Fiber", db_path=initialized_db)
    assert len(results) >= 1
    assert any("Fiber" in r["formatted_text"] or "Fiber" in (r["raw_text"] or "") for r in results)


def test_search_records_no_match(initialized_db: Path):
    _insert_sample(initialized_db)
    results = search_records("不存在的关键词xyz", db_path=initialized_db)
    assert len(results) == 0


def test_search_records_chinese(initialized_db: Path):
    _insert_sample(initialized_db, raw_text="机器学习是人工智能的子领域", formatted_text="机器学习入门")
    results = search_records("机器学习", db_path=initialized_db)
    assert len(results) >= 1


# ── 删除 ──

def test_delete_record(initialized_db: Path):
    rid = _insert_sample(initialized_db)
    assert delete_record(rid, db_path=initialized_db) is True
    assert get_record_by_id(rid, db_path=initialized_db) is None


def test_delete_record_not_found(initialized_db: Path):
    assert delete_record(9999, db_path=initialized_db) is False
