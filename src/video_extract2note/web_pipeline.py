"""网页内容处理流水线：抓取 → LLM 格式化。"""

import time
from pathlib import Path

from video_extract2note.pipeline import PipelineResult, StepTiming
from video_extract2note.transcript_formatter import FormatterError, format_transcript
from video_extract2note.web_fetcher import WebFetchError, fetch_web_content


def run_web_pipeline(url: str, output_dir: Path | None = None) -> PipelineResult:
    """抓取网页内容并格式化整理。

    Args:
        url: 网页链接
        output_dir: 输出目录（网页流水线不产生文件，保留接口一致性）

    Returns:
        PipelineResult 包含格式化文本和各步骤耗时
    """
    timings: list[StepTiming] = []
    t_total_start = time.perf_counter()

    # ── 抓取网页 ──
    t_fetch_start = time.perf_counter()
    try:
        raw_text = fetch_web_content(url)
    except WebFetchError as exc:
        timings.append(
            StepTiming(step="抓取网页", duration_ms=int((time.perf_counter() - t_fetch_start) * 1000), status="error")
        )
        timings.append(StepTiming(step="总计", duration_ms=int((time.perf_counter() - t_total_start) * 1000), status="error"))
        raise WebFetchError(str(exc)) from exc

    char_count = len(raw_text)
    meta = f"{char_count} 字" if char_count < 10000 else f"{char_count / 1000:.1f}K 字"
    timings.append(
        StepTiming(step="抓取网页", duration_ms=int((time.perf_counter() - t_fetch_start) * 1000), status="done", meta=meta)
    )

    # ── LLM 格式化 ──
    t_format_start = time.perf_counter()
    try:
        formatted_text = format_transcript(raw_text)
        timings.append(
            StepTiming(step="格式化", duration_ms=int((time.perf_counter() - t_format_start) * 1000), status="done")
        )
    except FormatterError:
        formatted_text = raw_text
        timings.append(
            StepTiming(step="格式化", duration_ms=int((time.perf_counter() - t_format_start) * 1000), status="error")
        )

    # ── 总耗时 ──
    total_ms = int((time.perf_counter() - t_total_start) * 1000)
    timings.append(StepTiming(step="总计", duration_ms=total_ms, status="done"))

    return PipelineResult(
        text=formatted_text,
        video_path=None,
        timings=timings,
        url=url,
        source_type="web",
        platform="web",
        raw_text=raw_text,
    )
