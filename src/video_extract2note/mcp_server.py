"""MCP server: exposes video transcription and web fetching as tools for Claude Code."""

import asyncio
import shutil
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import video_extract2note.config as cfg
import video_extract2note.db as db
from video_extract2note.input_parser import extract_first_url
from video_extract2note.pipeline import run_pipeline
from video_extract2note.web_pipeline import run_web_pipeline

mcp = FastMCP("video-extract2note")

OUTPUT_BASE = cfg.MCP_OUTPUT_BASE

# 启动时初始化数据库
db.init_db()


@mcp.tool()
async def fetch_video_transcript(url: str, engine: str = "auto") -> str:
    """提取视频的转写文本。给定视频链接（抖音/B站），下载音频、语音转文字、格式化后返回纯文本内容。

    支持平台: 抖音 (douyin.com, v.douyin.com, iesdouyin.com), B站 (bilibili.com, b23.tv)

    Args:
        url: 视频链接（支持抖音、B站）
        engine: 转写引擎选择
            - "auto": 自动选择 (默认) - MiMo > whisper.cpp > faster-whisper
            - "mimo": 小米 MiMo API 云端转写 (需要 MIMO_API_KEY)
            - "whisper.cpp": Apple Silicon 原生加速
            - "faster-whisper": 本地 CPU 转写

    返回: 格式化后的转写文本，可直接阅读理解视频内容。
    """
    extracted = extract_first_url(url)
    if extracted is None:
        return "错误: 未找到有效视频链接。请提供抖音或B站视频链接。"

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = OUTPUT_BASE / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = run_pipeline(extracted, output_dir, engine=engine)
        # 自动存储到数据库
        try:
            db.save_record(
                url=extracted,
                source_type="video",
                formatted_text=result.text,
                platform=result.platform,
                engine=result.engine,
                raw_text=result.raw_text,
                duration_seconds=result.duration_seconds,
            )
        except Exception:
            pass  # 存储失败不影响返回
        return result.text
    except Exception as exc:
        return f"错误: {exc}"
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


@mcp.tool()
async def fetch_web_content(url: str) -> str:
    """抓取任意网页内容并格式化整理。给定网页链接，抓取页面正文、通过 LLM 整理后返回 Markdown 文本。

    适用场景: 新闻文章、博客、技术文档、百科页面等任意可公开访问的网页。

    Args:
        url: 网页链接（任意 http/https URL）

    返回: 格式化后的 Markdown 文本，包含标题和正文内容。
    """
    extracted = extract_first_url(url)
    if extracted is None:
        return "错误: 未找到有效链接。请提供 http 或 https 开头的网页链接。"

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_web_pipeline, extracted)
        # 自动存储到数据库
        try:
            db.save_record(
                url=extracted,
                source_type="web",
                formatted_text=result.text,
                platform="web",
                raw_text=result.raw_text,
            )
        except Exception:
            pass  # 存储失败不影响返回
        return result.text
    except Exception as exc:
        return f"错误: {exc}"


def main():
    mcp.run()


@mcp.tool()
async def search_transcripts(query: str, limit: int = 10) -> str:
    """全文搜索历史转写记录。支持关键词搜索标题、转写文本和格式化文本。

    Args:
        query: 搜索关键词
        limit: 返回结果数量上限，默认 10

    返回: 匹配的记录列表，包含 URL、平台、标题和文本摘要。
    """
    try:
        results = db.search_records(query, limit=limit)
    except Exception as exc:
        return f"搜索失败: {exc}"

    if not results:
        return f"未找到匹配「{query}」的记录。"

    lines = [f"找到 {len(results)} 条匹配记录：\n"]
    for r in results:
        title = r.get("title") or "(无标题)"
        platform = r.get("platform") or "未知"
        created = r.get("created_at", "")
        text_preview = (r.get("formatted_text") or "")[:200]
        lines.append(f"### [{r['id']}] {title}")
        lines.append(f"- 平台: {platform} | 时间: {created}")
        lines.append(f"- 链接: {r['url']}")
        lines.append(f"- 摘要: {text_preview}...")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
async def list_history(limit: int = 20, offset: int = 0) -> str:
    """查看历史转写记录列表，按时间倒序排列。

    Args:
        limit: 返回数量上限，默认 20
        offset: 跳过前 N 条记录，用于分页

    返回: 历史记录列表，包含 ID、平台、标题和时间。
    """
    try:
        results = db.list_records(limit=limit, offset=offset)
    except Exception as exc:
        return f"查询失败: {exc}"

    if not results:
        return "暂无历史记录。"

    lines = [f"历史记录（{offset + 1}–{offset + len(results)}）：\n"]
    for r in results:
        title = r.get("title") or "(无标题)"
        platform = r.get("platform") or "未知"
        created = r.get("created_at", "")
        engine = r.get("engine") or "-"
        lines.append(f"[{r['id']}] {title} | {platform} | {engine} | {created}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
