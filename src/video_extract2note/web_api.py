"""VidWise Web API — FastAPI HTTP 服务，端口 8765。

启动: python -m video_extract2note.web_api
"""

import json
import os
from datetime import datetime
from pathlib import Path

import video_extract2note.config as cfg
from video_extract2note.db import get_record_by_id, init_db, list_records, save_record
from video_extract2note.knowledge_base import get_kb
from video_extract2note.input_parser import classify_url, extract_first_url
from video_extract2note.pipeline import run_pipeline, run_local_file
from video_extract2note.transcriber import TranscriptionError
from video_extract2note.video_searcher import SearchError, search_videos
from video_extract2note.web_pipeline import run_web_pipeline

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except ImportError:
    raise ImportError("请安装 fastapi: pip install fastapi uvicorn pydantic")

app = FastAPI(title="VidWise API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

OUTPUT_BASE = Path.home() / "Documents" / "VideoExtract2Note"


# ── Models ──

class ExtractRequest(BaseModel):
    url: str


class ExtractFileRequest(BaseModel):
    file_path: str


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str = "deepseek"


class SaveRequest(BaseModel):
    url: str = ""
    platform: str = ""
    engine: str = ""
    rawText: str = ""
    formattedText: str = ""
    durationSeconds: float | None = None
    sourceType: str = "video"
    title: str = ""


class SearchRequest(BaseModel):
    query: str


# ── Routes ──

@app.post("/api/extract")
def api_extract(req: ExtractRequest):
    url = extract_first_url(req.url)
    if not url:
        raise HTTPException(400, "未找到有效链接")

    url_type = classify_url(url)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = OUTPUT_BASE / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        if url_type == "video":
            result = run_pipeline(url, output_dir)
        else:
            result = run_web_pipeline(url, output_dir)
    except Exception as exc:
        raise HTTPException(500, str(exc))

    return {
        "ok": True,
        "text": result.text,
        "videoUrl": str(result.video_path) if result.video_path else None,
        "logs": [],
        "timings": [{"step": t.step, "durationMs": t.duration_ms, "status": t.status, "meta": t.meta} for t in result.timings],
        "saveContext": {
            "url": url,
            "platform": result.platform,
            "engine": result.engine,
            "rawText": result.raw_text,
            "durationSeconds": result.duration_seconds,
            "sourceType": "video" if url_type == "video" else "web",
        },
    }


@app.post("/api/extract-file")
def api_extract_file(req: ExtractFileRequest):
    path = Path(req.file_path)
    if not path.exists():
        raise HTTPException(400, f"文件不存在: {req.file_path}")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = OUTPUT_BASE / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = run_local_file(path, output_dir)
    except Exception as exc:
        raise HTTPException(500, str(exc))

    return {
        "ok": True,
        "text": result.text,
        "videoUrl": str(result.video_path) if result.video_path else None,
        "logs": [],
        "timings": [{"step": t.step, "durationMs": t.duration_ms, "status": t.status, "meta": t.meta} for t in result.timings],
        "saveContext": {
            "url": f"local://{path.name}",
            "platform": "local",
            "engine": result.engine,
            "rawText": result.raw_text,
            "durationSeconds": result.duration_seconds,
            "sourceType": "video",
        },
    }


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    if req.model == "mimo":
        api_key = os.environ.get("MIMO_API_KEY", "").strip()
        base_url = cfg.MIMO_BASE_URL
        model_name = cfg.MIMO_MODEL
    else:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        base_url = cfg.DEEPSEEK_BASE_URL
        model_name = cfg.DEEPSEEK_MODEL

    if not api_key:
        raise HTTPException(400, f"未设置 {req.model.upper()}_API_KEY")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model_name,
            messages=req.messages,
            temperature=0.7,
            max_tokens=2048,
        )
        return {"ok": True, "reply": resp.choices[0].message.content.strip()}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/save")
def api_save(req: SaveRequest):
    try:
        init_db()
        save_record(
            url=req.url,
            source_type=req.sourceType,
            formatted_text=req.formattedText,
            title=req.title,
            platform=req.platform,
            engine=req.engine,
            raw_text=req.rawText,
            duration_seconds=req.durationSeconds,
        )
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/history")
def api_history(limit: int = 20):
    try:
        init_db()
        records = list_records(limit=limit, offset=0)
        return {
            "ok": True,
            "records": [
                {
                    "id": r["id"], "url": r["url"], "sourceType": r["source_type"],
                    "platform": r["platform"] or "", "title": r["title"] or "",
                    "engine": r["engine"] or "", "duration": r["duration_seconds"],
                    "createdAt": r["created_at"], "preview": (r["formatted_text"] or "")[:200],
                }
                for r in records
            ],
        }
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/history/{record_id}")
def api_get_record(record_id: int):
    try:
        init_db()
        r = get_record_by_id(record_id)
        if r is None:
            raise HTTPException(404, f"记录 {record_id} 不存在")
        return {
            "ok": True,
            "record": {
                "id": r["id"], "url": r["url"], "sourceType": r["source_type"],
                "platform": r["platform"] or "", "title": r["title"] or "",
                "engine": r["engine"] or "", "rawText": r["raw_text"] or "",
                "formattedText": r["formatted_text"] or "", "duration": r["duration_seconds"],
                "createdAt": r["created_at"],
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/search")
def api_search(req: SearchRequest):
    try:
        results = search_videos(req.query, max_results=15)
        return {"ok": True, "results": results}
    except SearchError as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/knowledge/rebuild")
def api_kb_rebuild():
    try:
        kb = get_kb()
        count = kb.rebuild()
        return {"ok": True, "count": count}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/knowledge/search")
def api_kb_search(req: SearchRequest):
    try:
        kb = get_kb()
        docs = kb.search(req.query)
        return {"ok": True, "docs": docs}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/knowledge/status")
def api_kb_status():
    try:
        kb = get_kb()
        return {"ok": True, "built": kb.is_built()}
    except Exception as exc:
        raise HTTPException(500, str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
