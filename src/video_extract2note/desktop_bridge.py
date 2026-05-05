import json
import os
import sys
from datetime import datetime
from pathlib import Path

import video_extract2note.config as cfg
import video_extract2note.db as db
from video_extract2note.downloader import DownloadError
from video_extract2note.input_parser import extract_first_url, classify_url
from video_extract2note.pipeline import run_pipeline, run_local_file
from video_extract2note.transcriber import TranscriptionError
from video_extract2note.web_pipeline import run_web_pipeline
from video_extract2note.knowledge_base import get_kb
from video_extract2note.video_searcher import search_videos, SearchError
from video_extract2note.web_fetcher import WebFetchError

OUTPUT_BASE = Path.home() / "Documents" / "VideoExtract2Note"


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


# ── 提取链接 ──

def run_link(raw_input: str) -> int:
    logs: list[str] = []
    url = extract_first_url(raw_input)
    if url is None:
        _emit(
            {
                "ok": False,
                "text": None,
                "videoPath": None,
                "error": "未找到有效链接，请粘贴视频分享链接或网页链接。",
                "logs": logs,
            }
        )
        return 1

    url_type = classify_url(url)

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = OUTPUT_BASE / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)

        if url_type == "video":
            logs.append("正在下载视频并加载模型...")
            result = run_pipeline(url, output_dir)
        else:
            logs.append("正在抓取网页内容...")
            result = run_web_pipeline(url, output_dir)
    except (DownloadError, TranscriptionError, WebFetchError) as exc:
        _emit(
            {
                "ok": False,
                "text": None,
                "videoPath": None,
                "error": str(exc),
                "logs": logs,
            }
        )
        return 1

    video_path = str(result.video_path) if result.video_path else None

    timings = [
        {"step": t.step, "durationMs": t.duration_ms, "status": t.status, "meta": t.meta}
        for t in result.timings
    ]

    _emit(
        {
            "ok": True,
            "text": result.text,
            "videoPath": video_path,
            "error": None,
            "logs": logs,
            "timings": timings,
            "saveContext": {
                "url": url,
                "platform": result.platform,
                "engine": result.engine,
                "rawText": result.raw_text,
                "durationSeconds": result.duration_seconds,
                "sourceType": "video" if url_type == "video" else "web",
            },
        }
    )
    return 0


# ── 历史记录列表 ──

def list_history(limit: int = 20, offset: int = 0) -> int:
    try:
        db.init_db()
        records = db.list_records(limit=limit, offset=offset)
        _emit(
            {
                "ok": True,
                "records": [
                    {
                        "id": r["id"],
                        "url": r["url"],
                        "sourceType": r["source_type"],
                        "platform": r["platform"] or "",
                        "title": r["title"] or "",
                        "engine": r["engine"] or "",
                        "duration": r["duration_seconds"],
                        "createdAt": r["created_at"],
                        "preview": (r["formatted_text"] or "")[:200],
                    }
                    for r in records
                ],
                "error": None,
            }
        )
        return 0
    except Exception as exc:
        _emit({"ok": False, "records": [], "error": str(exc)})
        return 1


# ── 全文搜索 ──

def search_records(query: str, limit: int = 10) -> int:
    try:
        db.init_db()
        records = db.search_records(query, limit=limit)
        _emit(
            {
                "ok": True,
                "records": [
                    {
                        "id": r["id"],
                        "url": r["url"],
                        "sourceType": r["source_type"],
                        "platform": r["platform"] or "",
                        "title": r["title"] or "",
                        "engine": r["engine"] or "",
                        "duration": r["duration_seconds"],
                        "createdAt": r["created_at"],
                        "preview": (r["formatted_text"] or "")[:200],
                    }
                    for r in records
                ],
                "error": None,
            }
        )
        return 0
    except Exception as exc:
        _emit({"ok": False, "records": [], "error": str(exc)})
        return 1


# ── 获取单条记录详情 ──

def get_record(record_id: int) -> int:
    try:
        db.init_db()
        r = db.get_record_by_id(record_id)
        if r is None:
            _emit({"ok": False, "record": None, "error": f"记录 {record_id} 不存在"})
            return 1
        _emit(
            {
                "ok": True,
                "record": {
                    "id": r["id"],
                    "url": r["url"],
                    "sourceType": r["source_type"],
                    "platform": r["platform"] or "",
                    "title": r["title"] or "",
                    "engine": r["engine"] or "",
                    "rawText": r["raw_text"] or "",
                    "formattedText": r["formatted_text"] or "",
                    "duration": r["duration_seconds"],
                    "createdAt": r["created_at"],
                },
                "error": None,
            }
        )
        return 0
    except Exception as exc:
        _emit({"ok": False, "record": None, "error": str(exc)})
        return 1


# ── 本地文件 ──

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".webm", ".m4v"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def run_file(file_path: str) -> int:
    path = Path(file_path)
    if not path.exists():
        _emit({"ok": False, "text": None, "videoPath": None, "error": f"文件不存在: {file_path}", "logs": []})
        return 1
    if not path.is_file():
        _emit({"ok": False, "text": None, "videoPath": None, "error": f"路径不是文件: {file_path}", "logs": []})
        return 1

    ext = path.suffix.lower()
    if ext not in _VIDEO_EXTENSIONS and ext not in _AUDIO_EXTENSIONS:
        _emit({
            "ok": False, "text": None, "videoPath": None, "logs": [],
            "error": f"不支持的文件格式 ({ext})。仅支持视频和音频文件。",
        })
        return 1

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = OUTPUT_BASE / timestamp
        result = run_local_file(path, output_dir)
    except Exception as exc:
        _emit({"ok": False, "text": None, "videoPath": None, "error": str(exc), "logs": []})
        return 1

    video_path = str(result.video_path) if result.video_path else None
    timings = [
        {"step": t.step, "durationMs": t.duration_ms, "status": t.status, "meta": t.meta}
        for t in result.timings
    ]

    _emit({
        "ok": True,
        "text": result.text,
        "videoPath": video_path,
        "error": None,
        "logs": [],
        "timings": timings,
        "saveContext": {
            "url": f"local://{path.name}",
            "platform": result.platform,
            "engine": result.engine,
            "rawText": result.raw_text,
            "durationSeconds": result.duration_seconds,
            "sourceType": "video",
        },
    })
    return 0


# ── 视频搜索 ──

def run_search(query: str, limit: int = 15) -> int:
    try:
        results = search_videos(query, max_results=limit)
        _emit({"ok": True, "results": results, "error": None})
        return 0
    except SearchError as exc:
        _emit({"ok": False, "results": [], "error": str(exc)})
        return 1


# ── 手动保存到素材库 ──

def run_save(json_str: str) -> int:
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        _emit({"ok": False, "error": f"JSON 解析失败: {exc}"})
        return 1
    try:
        db.init_db()
        db.save_record(
            url=data.get("url", ""),
            source_type=data.get("sourceType", "video"),
            formatted_text=data.get("formattedText", ""),
            title=data.get("title", ""),
            platform=data.get("platform", ""),
            engine=data.get("engine", ""),
            raw_text=data.get("rawText", ""),
            duration_seconds=data.get("durationSeconds"),
        )
        _emit({"ok": True})
        return 0
    except Exception as exc:
        _emit({"ok": False, "error": str(exc)})
        return 1


# ── Agent 聊天 ──

def run_chat(json_str: str) -> int:
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        _emit({"ok": False, "reply": "", "error": f"JSON 解析失败: {exc}"})
        return 1

    messages = data.get("messages", [])
    model_key = data.get("model", "deepseek")

    if model_key == "mimo":
        api_key = os.environ.get("MIMO_API_KEY", "").strip()
        base_url = cfg.MIMO_BASE_URL
        model_name = cfg.MIMO_MODEL
    else:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        base_url = cfg.DEEPSEEK_BASE_URL
        model_name = cfg.DEEPSEEK_MODEL

    if not api_key:
        _emit({"ok": False, "reply": "", "error": f"未设置 {model_key.upper()}_API_KEY"})
        return 1

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )
        reply = response.choices[0].message.content.strip()
        _emit({"ok": True, "reply": reply, "error": None})
        return 0
    except Exception as exc:
        _emit({"ok": False, "reply": "", "error": str(exc)})
        return 1


# ── CLI 入口 ──

def main() -> int:
    if len(sys.argv) < 2:
        _emit({"ok": False, "error": "缺少参数。用法: run <url> | file <path> | list | search <query> | get <id>"})
        return 1

    cmd = sys.argv[1]

    if cmd == "list":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        offset = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        return list_history(limit, offset)

    if cmd == "search":
        if len(sys.argv) < 3:
            _emit({"ok": False, "error": "缺少搜索关键词"})
            return 1
        query = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        return search_records(query, limit)

    if cmd == "get":
        if len(sys.argv) < 3:
            _emit({"ok": False, "error": "缺少记录 ID"})
            return 1
        return get_record(int(sys.argv[2]))

    if cmd == "search":
        if len(sys.argv) < 3:
            _emit({"ok": False, "error": "缺少搜索关键词"})
            return 1
        query = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 15
        return run_search(query, limit)

    if cmd == "file":
        if len(sys.argv) < 3:
            _emit({"ok": False, "error": "缺少文件路径。用法: file <path>"})
            return 1
        return run_file(sys.argv[2])

    if cmd == "save":
        if len(sys.argv) < 3:
            _emit({"ok": False, "error": "缺少数据。用法: save <json>"})
            return 1
        return run_save(sys.argv[2])

    if cmd == "chat":
        if len(sys.argv) < 3:
            _emit({"ok": False, "error": "缺少数据。用法: chat <json>"})
            return 1
        return run_chat(sys.argv[2])

    if cmd == "kb-rebuild":
        try:
            kb = get_kb()
            count = kb.rebuild()
            _emit({"ok": True, "count": count})
        except Exception as exc:
            _emit({"ok": False, "error": str(exc)})
        return 0

    if cmd == "kb-search":
        if len(sys.argv) < 3:
            _emit({"ok": False, "error": "缺少查询关键词"})
            return 1
        try:
            kb = get_kb()
            docs = kb.search(sys.argv[2])
            _emit({"ok": True, "docs": docs})
        except Exception as exc:
            _emit({"ok": False, "error": str(exc)})
        return 0

    # 向后兼容：argv[1] 不是子命令时当作 URL
    return run_link(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
