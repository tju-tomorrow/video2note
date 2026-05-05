import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import video_extract2note.config as cfg
from video_extract2note.downloader import (
    DownloadError, download_audio,
)
from video_extract2note.transcript_formatter import FormatterError, format_transcript
from video_extract2note.transcriber import (
    TranscriptionError,
    TranscriptionOptions,
    is_whisper_cpp_available,
    is_mimo_available,
    load_model,
    transcribe_audio_detailed,
    transcribe_audio_parallel,
    _transcribe_whisper_cpp,
    _transcribe_mimo,
)

logger = logging.getLogger(__name__)

_UNSET = object()
_LONG_AUDIO_THRESHOLD = cfg.LONG_AUDIO_THRESHOLD_SECONDS


def _detect_platform(url: str) -> str:
    domain = urlsplit(url).netloc.lower()
    if "douyin" in domain or "iesdouyin" in domain:
        return "douyin"
    if "bilibili" in domain or "b23" in domain:
        return "bilibili"
    return ""


@dataclass(frozen=True)
class StepTiming:
    step: str
    duration_ms: int
    status: str  # "done" | "error"
    meta: str = ""  # 附加信息，如文件大小


@dataclass(frozen=True)
class PipelineResult:
    text: str
    video_path: Path | None = None
    timings: list[StepTiming] = field(default_factory=list)
    url: str = ""
    source_type: str = "video"
    platform: str = ""
    title: str = ""
    engine: str = ""
    raw_text: str = ""
    duration_seconds: float | None = None


def _get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(audio_path),
        ],
        capture_output=True, text=True,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def _ensure_faster_whisper_model(
    model: Any,
    model_name: str,
    model_factory: Any,
) -> Any:
    """确保 faster-whisper 模型已加载，未加载则加载。"""
    if model is not None:
        return model
    load_kwargs: dict[str, Any] = {}
    if model_factory is not _UNSET:
        load_kwargs["model_factory"] = model_factory
    return load_model(model_name, **load_kwargs)


def _transcribe_with_faster_whisper(
    audio_path: Path,
    model: Any,
    model_name: str,
    model_factory: Any,
    output_dir: Path,
) -> Any:
    """使用 faster-whisper 转写，长音频自动并行。"""
    model = _ensure_faster_whisper_model(model, model_name, model_factory)
    try:
        duration = _get_audio_duration(audio_path)
    except Exception:
        duration = 0
    if duration > _LONG_AUDIO_THRESHOLD:
        num_workers = min(os.cpu_count() or 4, cfg.MAX_PARALLEL_WORKERS)
        options = TranscriptionOptions(model_name=model_name, num_workers=num_workers)
        return transcribe_audio_parallel(audio_path, model, options, output_dir)
    return transcribe_audio_detailed(audio_path, model=model)


def _transcribe_with_fallback(
    audio_path: Path,
    engine: str,
    model_name: str,
    model: Any,
    model_factory: Any,
    output_dir: Path,
    fallback_errors: list[tuple[str, str]],
) -> Any:
    """统一转写入口，按引擎选择 + 自动降级。

    降级链: mimo → whisper.cpp → faster-whisper
    """
    if not audio_path.exists():
        raise TranscriptionError(f"音频文件不存在: {audio_path}")

    # ── MiMo 引擎 ──
    if engine == "mimo":
        try:
            logger.info("尝试 MiMo 转写...")
            return _transcribe_mimo(audio_path, "zh")
        except Exception as exc:
            logger.warning("MiMo 转写失败: %s，降级", exc)
            fallback_errors.append(("mimo", str(exc)))

        if is_whisper_cpp_available():
            try:
                logger.info("降级到 whisper.cpp...")
                return _transcribe_whisper_cpp(audio_path, model_name, "zh")
            except Exception as exc:
                logger.warning("whisper.cpp 转写失败: %s，降级", exc)
                fallback_errors.append(("whisper.cpp", str(exc)))
        logger.info("降级到 faster-whisper")
        return _transcribe_with_faster_whisper(audio_path, model, model_name, model_factory, output_dir)

    # ── whisper.cpp 引擎 ──
    if engine == "whisper.cpp":
        return _transcribe_whisper_cpp(audio_path, model_name, "zh")

    # ── faster-whisper 引擎（默认） ──
    return _transcribe_with_faster_whisper(audio_path, model, model_name, model_factory, output_dir)


def run_pipeline(
    url: str,
    output_dir: Path,
    ydl_factory: Any = _UNSET,
    model_factory: Any = _UNSET,
    model_name: str = "small",
    engine: str = "auto",
) -> PipelineResult:
    """
    核心流程（音频优先）：
    1. 并行：下载音频（yt-dlp）+ 加载 whisper 模型
    2. 转写 + 格式化
    视频异步下载，不阻塞转写。

    Args:
        url: 视频链接
        output_dir: 输出目录
        ydl_factory: yt-dlp 工厂函数
        model_factory: 模型工厂函数
        model_name: 模型名称 (small/medium 等)
        engine: 转写引擎选择
            - "auto": 自动选择 (whisper.cpp > faster-whisper > mimo)
            - "faster-whisper": 使用 faster-whisper (本地 CPU)
            - "whisper.cpp": 使用 whisper.cpp (Apple Silicon 优化)
            - "mimo": 使用小米 MiMo API (云端)
    """
    timings: list[StepTiming] = []
    t_total_start = time.perf_counter()

    # ── 检测转写引擎 ──
    if engine == "auto":
        # 优先级: mimo > whisper.cpp > faster-whisper
        if is_mimo_available():
            use_engine = "mimo"
        elif is_whisper_cpp_available():
            use_engine = "whisper.cpp"
        else:
            use_engine = "faster-whisper"
    else:
        use_engine = engine

    logger.info("引擎选择: %s (请求: %s)", use_engine, engine)
    use_whisper_cpp = use_engine == "whisper.cpp"
    use_mimo = use_engine == "mimo"

    # ── 下载音频 + 加载模型（并行）──
    # 注意: MiMo 不需要预加载模型
    audio_path: Path | None = None
    audio_error: Exception | None = None

    def _download_audio() -> None:
        nonlocal audio_path, audio_error
        try:
            audio_kwargs: dict[str, Any] = {"extract_audio": False}
            if ydl_factory is not _UNSET:
                audio_kwargs["ydl_factory"] = ydl_factory
            audio_path = download_audio(url, output_dir, **audio_kwargs)
        except Exception as exc:
            audio_error = exc

    t_dl_start = time.perf_counter()
    audio_thread = threading.Thread(target=_download_audio, daemon=True)
    audio_thread.start()

    # 并行加载模型（仅 faster-whisper）
    model = None
    model_error: Exception | None = None
    t_model_start = time.perf_counter()
    if not use_whisper_cpp and not use_mimo:
        try:
            load_kwargs: dict[str, Any] = {}
            if model_factory is not _UNSET:
                load_kwargs["model_factory"] = model_factory
            model = load_model(model_name, **load_kwargs)
        except Exception as exc:
            model_error = exc
    t_model_ms = int((time.perf_counter() - t_model_start) * 1000)

    audio_thread.join()
    t_dl_ms = int((time.perf_counter() - t_dl_start) * 1000)

    if not use_whisper_cpp and not use_mimo:
        timings.append(
            StepTiming(
                step="加载模型",
                duration_ms=t_model_ms,
                status="done" if model_error is None else "error",
            )
        )
    if model_error is not None:
        if isinstance(model_error, TranscriptionError):
            raise model_error
        raise TranscriptionError(str(model_error)) from model_error

    # 下载文件大小
    dl_meta = ""
    if audio_path is not None and audio_path.exists():
        try:
            size_bytes = audio_path.stat().st_size
            if size_bytes >= 1024 * 1024:
                dl_meta = f"{size_bytes / (1024 * 1024):.1f}MB"
            else:
                dl_meta = f"{size_bytes / 1024:.0f}KB"
        except OSError:
            pass
    timings.append(StepTiming(step="下载音频", duration_ms=t_dl_ms, status="done", meta=dl_meta))

    if audio_error is not None:
        if isinstance(audio_error, DownloadError):
            raise audio_error
        raise DownloadError(str(audio_error)) from audio_error

    if audio_path is None or not audio_path.exists():
        raise DownloadError("下载完成后未找到音频文件。")

    # ── 转写 ──
    t_transcribe_start = time.perf_counter()
    fallback_errors: list[tuple[str, str]] = []

    try:
        result = _transcribe_with_fallback(
            audio_path=audio_path,
            engine=use_engine,
            model_name=model_name,
            model=model,
            model_factory=model_factory,
            output_dir=output_dir,
            fallback_errors=fallback_errors,
        )
    except Exception as exc:
        t_transcribe_ms = int((time.perf_counter() - t_transcribe_start) * 1000)
        timings.append(StepTiming(step="转写", duration_ms=t_transcribe_ms, status="error"))
        error_msg = str(exc)
        if fallback_errors:
            error_parts = [f"[{eng}] {msg}" for eng, msg in fallback_errors]
            error_msg = "转写失败，已尝试以下引擎：\n" + "\n".join(error_parts)
        raise TranscriptionError(error_msg) from exc

    t_transcribe_ms = int((time.perf_counter() - t_transcribe_start) * 1000)
    timings.append(StepTiming(step="转写", duration_ms=t_transcribe_ms, status="done"))

    raw_text = result.cleaned_text

    # ── 格式化 ──
    t_format_start = time.perf_counter()
    try:
        formatted_text = format_transcript(raw_text)
        timings.append(
            StepTiming(
                step="格式化",
                duration_ms=int((time.perf_counter() - t_format_start) * 1000),
                status="done",
            )
        )
    except FormatterError:
        formatted_text = raw_text
        timings.append(
            StepTiming(
                step="格式化",
                duration_ms=int((time.perf_counter() - t_format_start) * 1000),
                status="error",
            )
        )

    # ── 总耗时 ──
    total_ms = int((time.perf_counter() - t_total_start) * 1000)
    timings.append(StepTiming(step="总计", duration_ms=total_ms, status="done"))

    return PipelineResult(
        text=formatted_text,
        video_path=None,
        timings=timings,
        url=url,
        source_type="video",
        platform=_detect_platform(url),
        engine=use_engine,
        raw_text=raw_text,
        duration_seconds=getattr(result, "duration", None),
    )


_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".webm", ".m4v", ".wmv"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}


def run_local_file(
    file_path: Path,
    output_dir: Path,
    model_factory: Any = _UNSET,
    model_name: str = "small",
    engine: str = "auto",
) -> PipelineResult:
    """处理本地视频/音频文件，提取音频后转写。

    Args:
        file_path: 本地文件路径
        output_dir: 输出目录
        model_factory: 模型工厂函数
        model_name: 模型名称
        engine: 转写引擎选择
    """
    timings: list[StepTiming] = []
    t_total_start = time.perf_counter()

    output_dir.mkdir(parents=True, exist_ok=True)

    ext = file_path.suffix.lower()

    # ── 检测转写引擎 ──
    if engine == "auto":
        if is_mimo_available():
            use_engine = "mimo"
        elif is_whisper_cpp_available():
            use_engine = "whisper.cpp"
        else:
            use_engine = "faster-whisper"
    else:
        use_engine = engine

    logger.info("本地文件引擎选择: %s (请求: %s)", use_engine, engine)
    use_whisper_cpp = use_engine == "whisper.cpp"
    use_mimo = use_engine == "mimo"

    # ── 提取音频（如果是视频）──
    t_extract_start = time.perf_counter()

    if ext in _AUDIO_EXTENSIONS:
        audio_path = file_path
        timings.append(StepTiming(step="使用音频", duration_ms=0, status="done", meta=ext))
    elif ext in _VIDEO_EXTENSIONS:
        audio_path = output_dir / "extracted_audio.mp3"
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(file_path), "-vn",
             "-acodec", "libmp3lame", "-q:a", "2", str(audio_path)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise DownloadError(f"音频提取失败: {result.stderr[:200]}")
        t_extract_ms = int((time.perf_counter() - t_extract_start) * 1000)
        size_mb = audio_path.stat().st_size / (1024 * 1024)
        ext_meta = f"{size_mb:.1f}MB"
        timings.append(StepTiming(step="提取音频", duration_ms=t_extract_ms, status="done", meta=ext_meta))
    else:
        raise DownloadError(f"不支持的文件格式: {ext}。支持视频({', '.join(sorted(_VIDEO_EXTENSIONS))})和音频({', '.join(sorted(_AUDIO_EXTENSIONS))})。")

    if not audio_path.exists():
        raise DownloadError("提取音频后未找到文件。")

    # ── 转写 ──
    model = None
    if not use_whisper_cpp and not use_mimo:
        try:
            load_kwargs: dict[str, Any] = {}
            if model_factory is not _UNSET:
                load_kwargs["model_factory"] = model_factory
            model = load_model(model_name, **load_kwargs)
        except Exception as exc:
            raise TranscriptionError(str(exc)) from exc

    t_transcribe_start = time.perf_counter()
    fallback_errors: list[tuple[str, str]] = []

    try:
        result = _transcribe_with_fallback(
            audio_path=audio_path,
            engine=use_engine,
            model_name=model_name,
            model=model,
            model_factory=model_factory,
            output_dir=output_dir,
            fallback_errors=fallback_errors,
        )
    except Exception as exc:
        t_transcribe_ms = int((time.perf_counter() - t_transcribe_start) * 1000)
        timings.append(StepTiming(step="转写", duration_ms=t_transcribe_ms, status="error"))
        error_msg = str(exc)
        if fallback_errors:
            error_parts = [f"[{eng}] {msg}" for eng, msg in fallback_errors]
            error_msg = "转写失败，已尝试以下引擎：\n" + "\n".join(error_parts)
        raise TranscriptionError(error_msg) from exc

    t_transcribe_ms = int((time.perf_counter() - t_transcribe_start) * 1000)
    timings.append(StepTiming(step="转写", duration_ms=t_transcribe_ms, status="done"))

    raw_text = result.cleaned_text

    # ── 格式化 ──
    t_format_start = time.perf_counter()
    try:
        formatted_text = format_transcript(raw_text)
        timings.append(StepTiming(step="格式化", duration_ms=int((time.perf_counter() - t_format_start) * 1000), status="done"))
    except FormatterError:
        formatted_text = raw_text
        timings.append(StepTiming(step="格式化", duration_ms=int((time.perf_counter() - t_format_start) * 1000), status="error"))

    # ── 总耗时 ──
    total_ms = int((time.perf_counter() - t_total_start) * 1000)
    timings.append(StepTiming(step="总计", duration_ms=total_ms, status="done"))

    return PipelineResult(
        text=formatted_text,
        video_path=file_path if ext in _VIDEO_EXTENSIONS else None,
        timings=timings,
        url=file_path.name,
        source_type="video",
        platform="local",
        engine=use_engine,
        raw_text=raw_text,
        duration_seconds=getattr(result, "duration", None),
    )
