import base64
import concurrent.futures
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable

import video_extract2note.config as cfg
from video_extract2note.transcript_cleaner import TranscriptCleaningError, clean_transcript

logger = logging.getLogger(__name__)

DEFAULT_MODEL = cfg.DEFAULT_TRANSCRIPTION_MODEL
DEFAULT_INITIAL_PROMPT = cfg.DEFAULT_INITIAL_PROMPT
_DEFAULT_FACTORY = object()

_MODEL_NAME_TO_GGML = cfg.WHISPER_CPP_MODELS


class TranscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscriptionOptions:
    model_name: str = DEFAULT_MODEL
    language: str = "zh"
    device: str = "auto"
    compute_type: str = "auto"
    vad_filter: bool = True
    initial_prompt: str = DEFAULT_INITIAL_PROMPT
    beam_size: int = 1
    num_workers: int = 1


@dataclass(frozen=True)
class TranscriptResult:
    raw_text: str
    cleaned_text: str
    language: str | None
    model_name: str
    duration: float | None = None
    engine: str = "faster-whisper"


_QUALITY_PROFILES = {
    "fast": TranscriptionOptions(model_name="base"),
    "standard": TranscriptionOptions(model_name="small"),
    "quality": TranscriptionOptions(model_name="medium"),
}


def join_segments(segments: Iterable[Any]) -> str:
    parts = [segment.text.strip() for segment in segments if segment.text.strip()]
    return " ".join(parts)


def _load_default_model_factory() -> Callable[..., Any] | None:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    return WhisperModel


def get_transcription_options(profile: str = "standard") -> TranscriptionOptions:
    try:
        return _QUALITY_PROFILES[profile]
    except KeyError as exc:
        allowed = "、".join(sorted(_QUALITY_PROFILES))
        raise TranscriptionError(f"未知转写质量配置：{profile}。可选：{allowed}") from exc


# ── faster-whisper (Python, CPU, 回退方案) ──────────────────────────────

def load_model(
    model_name: str = DEFAULT_MODEL,
    model_factory: Callable[..., Any] | None | object = _DEFAULT_FACTORY,
    options: TranscriptionOptions | None = None,
) -> Any:
    if model_factory is _DEFAULT_FACTORY:
        model_factory = _load_default_model_factory()
    if model_factory is None:
        raise TranscriptionError(
            "faster-whisper 未安装，请先运行：python -m pip install faster-whisper"
        )
    resolved_options = options or get_transcription_options("standard")
    return model_factory(
        model_name,
        device=resolved_options.device,
        compute_type=resolved_options.compute_type,
    )


def _transcribe_with_model(
    model: Any,
    audio_path: Path,
    resolved_options: TranscriptionOptions,
    effective_model_name: str,
) -> TranscriptResult:
    segments, info = model.transcribe(
        str(audio_path),
        language=resolved_options.language,
        vad_filter=resolved_options.vad_filter,
        initial_prompt=resolved_options.initial_prompt,
        beam_size=resolved_options.beam_size,
    )
    raw_text = join_segments(segments)
    if not raw_text:
        raise TranscriptionError("未识别到可用语音内容。")
    try:
        cleaned_text = clean_transcript(raw_text)
    except TranscriptCleaningError as exc:
        raise TranscriptionError(str(exc)) from exc
    if not cleaned_text:
        raise TranscriptionError("未识别到可用语音内容。")
    return TranscriptResult(
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        language=getattr(info, "language", None),
        model_name=effective_model_name,
        duration=getattr(info, "duration", None),
        engine="faster-whisper",
    )


def transcribe_audio_detailed(
    audio_path: Path,
    model_name: str | None = None,
    model_factory: Callable[..., Any] | None | object = _DEFAULT_FACTORY,
    options: TranscriptionOptions | None = None,
    model: Any | None = None,
) -> TranscriptResult:
    resolved_options = options or get_transcription_options("standard")
    if model_name is not None:
        resolved_options = replace(resolved_options, model_name=model_name)
    effective_model_name = resolved_options.model_name

    if model is None:
        if model_factory is _DEFAULT_FACTORY:
            model_factory = _load_default_model_factory()
        if model_factory is None:
            raise TranscriptionError(
                "faster-whisper 未安装，请先运行：python -m pip install faster-whisper"
            )
        try:
            model = model_factory(
                effective_model_name,
                device=resolved_options.device,
                compute_type=resolved_options.compute_type,
            )
        except Exception as exc:
            raise TranscriptionError(f"转写失败：{exc}") from exc

    try:
        return _transcribe_with_model(model, audio_path, resolved_options, effective_model_name)
    except Exception as exc:
        raise TranscriptionError(f"转写失败：{exc}") from exc


def transcribe_audio(
    audio_path: Path,
    model_name: str = DEFAULT_MODEL,
    model_factory: Callable[..., Any] | None | object = _DEFAULT_FACTORY,
) -> str:
    return transcribe_audio_detailed(
        audio_path,
        model_name=model_name,
        model_factory=model_factory,
    ).cleaned_text


# ── whisper.cpp (CLI, Apple Silicon 原生加速) ───────────────────────────

def _find_whisper_cli() -> str | None:
    path = shutil.which("whisper-cli")
    if path:
        return path
    brew_path = Path("/opt/homebrew/bin/whisper-cli")
    if brew_path.exists():
        return str(brew_path)
    return None


def _find_whisper_cpp_model(model_name: str) -> str | None:
    ggml_name = _MODEL_NAME_TO_GGML.get(model_name, "ggml-small.bin")
    cached = cfg.WHISPER_CPP_MODEL_DIR / ggml_name
    if cached.exists():
        return str(cached)
    return None


def _download_whisper_cpp_model(model_name: str) -> str | None:
    ggml_name = _MODEL_NAME_TO_GGML.get(model_name, "ggml-small.bin")
    url = f"https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/{ggml_name}"
    dest = cfg.WHISPER_CPP_MODEL_DIR / ggml_name
    cfg.WHISPER_CPP_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["curl", "-L", url, "-o", str(dest), "--max-time", "600", "--silent", "--show-error"],
            check=True,
        )
        return str(dest)
    except subprocess.CalledProcessError:
        return None


def _transcribe_whisper_cpp(
    audio_path: Path,
    model_name: str,
    language: str,
) -> TranscriptResult:
    model_path = _find_whisper_cpp_model(model_name)
    if model_path is None:
        model_path = _download_whisper_cpp_model(model_name)
    if model_path is None:
        raise TranscriptionError(f"whisper.cpp 模型 {model_name} 下载失败")

    if not audio_path.exists():
        raise TranscriptionError(f"音频文件不存在: {audio_path}")

    # whisper-cli 只支持 wav/flac/mp3/ogg，其他格式需要先转 wav
    suffix = audio_path.suffix.lower()
    input_path = audio_path
    temp_wav: Path | None = None
    if suffix not in (".wav", ".flac", ".mp3", ".ogg"):
        temp_wav = audio_path.parent / f"{audio_path.stem}_cpp.wav"
        ffmpeg_result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path),
             "-ar", "16000", "-ac", "1", str(temp_wav)],
            capture_output=True, text=True,
        )
        if ffmpeg_result.returncode != 0:
            raise TranscriptionError(
                f"音频格式转换失败: {ffmpeg_result.stderr.strip()}"
            )
        if not temp_wav.exists():
            raise TranscriptionError(
                f"音频格式转换后文件不存在: {temp_wav}"
            )
        input_path = temp_wav

    if not input_path.exists():
        raise TranscriptionError(f"转写输入文件不存在: {input_path}")

    try:
        result = subprocess.run(
            [
                _find_whisper_cli(),
                "-m", model_path,
                "-l", language,
                "-nt",
                "-np",
                "-f", str(input_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise TranscriptionError(f"whisper.cpp 转写失败：{result.stderr.strip()}")

        raw_text = result.stdout.strip()
        if not raw_text:
            raise TranscriptionError("未识别到可用语音内容。")

        try:
            cleaned_text = clean_transcript(raw_text)
        except TranscriptCleaningError as exc:
            raise TranscriptionError(str(exc)) from exc
        if not cleaned_text:
            raise TranscriptionError("未识别到可用语音内容。")

        return TranscriptResult(
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            language=language,
            model_name=model_name,
            engine="whisper.cpp",
        )
    finally:
        if temp_wav is not None:
            try:
                temp_wav.unlink()
            except OSError:
                pass


def is_whisper_cpp_available() -> bool:
    return _find_whisper_cli() is not None


# ── MiMo API (小米多模态模型) ──────────────────────────────────────────────

def _audio_to_base64(audio_path: Path) -> str:
    """将音频文件转换为 base64 编码"""
    with open(audio_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_audio_mime_type(audio_path: Path) -> str:
    """根据文件扩展名返回 MIME 类型"""
    suffix = audio_path.suffix.lower()
    mime_map = {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".aac": "audio/aac",
    }
    return mime_map.get(suffix, "audio/mpeg")


def _transcribe_mimo_single(
    audio_path: Path,
    language: str = "zh",
) -> str:
    """单段音频的 MiMo 转写（内部使用，返回纯文本）"""
    api_key = os.environ.get("MIMO_API_KEY")
    if not api_key:
        raise TranscriptionError(
            "MIMO_API_KEY 未设置，请在 .env 文件中配置或设置环境变量"
        )

    try:
        from openai import OpenAI
    except ImportError:
        raise TranscriptionError(
            "openai 未安装，请先运行：python -m pip install openai"
        )

    # 转换为 base64
    audio_base64 = _audio_to_base64(audio_path)

    client = OpenAI(
        api_key=api_key,
        base_url=cfg.MIMO_BASE_URL,
    )

    completion = client.chat.completions.create(
        model=cfg.MIMO_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": "请逐字逐句转写这段音频的所有语音内容，不要总结、不要省略、不要添加任何解释，只输出转写文字。"
                    }
                ]
            }
        ],
        max_completion_tokens=8192
    )

    # MiMo 是推理模型，内容可能在 content 或 reasoning_content 中
    message = completion.choices[0].message
    raw_text = message.content.strip() if message.content else ""

    # 如果 content 为空，尝试用 reasoning_content
    if not raw_text:
        reasoning = getattr(message, 'reasoning_content', None)
        if reasoning:
            raw_text = reasoning.strip()

    return raw_text


def _transcribe_mimo(
    audio_path: Path,
    language: str = "zh",
) -> TranscriptResult:
    """使用 MiMo API 进行语音转文字（支持并行分段）"""
    if not audio_path.exists():
        raise TranscriptionError(f"音频文件不存在: {audio_path}")

    # MiMo 只支持 mp3/flac/m4a/wav/ogg，其他格式需要转换
    supported_formats = {".mp3", ".flac", ".m4a", ".wav", ".ogg"}
    suffix = audio_path.suffix.lower()
    input_path = audio_path
    temp_audio: Path | None = None

    if suffix not in supported_formats:
        # 转换为 mp3
        temp_audio = audio_path.parent / f"{audio_path.stem}_mimo.mp3"
        ffmpeg_result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path),
             "-ar", "16000", "-ac", "1", "-b:a", "128k", str(temp_audio)],
            capture_output=True, text=True,
        )
        if ffmpeg_result.returncode != 0:
            raise TranscriptionError(
                f"音频格式转换失败: {ffmpeg_result.stderr.strip()}"
            )
        if not temp_audio.exists():
            raise TranscriptionError(f"音频格式转换后文件不存在: {temp_audio}")
        input_path = temp_audio

    try:
        # 检查音频时长，决定是否并行
        duration = _get_audio_duration(input_path)
        audio_size_mb = input_path.stat().st_size / (1024 * 1024)
        long_audio_threshold = getattr(cfg, 'LONG_AUDIO_THRESHOLD_SECONDS', 300)

        # MiMo API 有 50MB 限制，大文件必须分段
        if duration > long_audio_threshold or audio_size_mb > 45:
            # 长音频或大文件：并行分段转写
            raw_text = _transcribe_mimo_parallel(input_path, duration, audio_size_mb)
        else:
            # 短音频：直接转写
            raw_text = _transcribe_mimo_single(input_path, language)

        if not raw_text:
            raise TranscriptionError("MiMo 未识别到可用语音内容。")

        return TranscriptResult(
            raw_text=raw_text,
            cleaned_text=raw_text,  # 直接使用原文
            language=language,
            model_name=cfg.MIMO_MODEL,
            engine="mimo",
        )
    finally:
        # 清理临时文件
        if temp_audio is not None:
            try:
                temp_audio.unlink()
            except OSError:
                pass


def _split_audio_by_vad(
    audio_path: Path,
    output_dir: Path,
    min_segment_duration: float = 30.0,
    max_segment_duration: float = 120.0,
    silence_threshold_db: float = -35.0,
    min_silence_duration: float = 0.8,
) -> list[Path]:
    """
    使用 ffmpeg 的 silencedetect 滤镜按静音段切分音频。
    如果静音段切分不合适，回退到按时长等分。

    Args:
        audio_path: 输入音频路径
        output_dir: 输出目录
        min_segment_duration: 每段最小时长（秒）
        max_segment_duration: 每段最大时长（秒）
        silence_threshold_db: 静音阈值（dB）
        min_silence_duration: 最小静音持续时间（秒）

    Returns:
        分段音频路径列表
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 先检测静音位置
    detect_result = subprocess.run(
        [
            "ffmpeg", "-i", str(audio_path),
            "-af", f"silencedetect=noise={silence_threshold_db}dB:d={min_silence_duration}",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )

    # 解析静音检测输出
    silence_points = []
    for line in detect_result.stderr.split('\n'):
        if 'silence_end:' in line:
            # 格式: [silencedetect @ ...] silence_end: 123.45 | silence_duration: 2.34
            try:
                end_time = float(line.split('silence_end:')[1].split('|')[0].strip())
                silence_points.append(end_time)
            except (IndexError, ValueError):
                continue

    # 根据静音点计算分段
    duration = _get_audio_duration(audio_path)
    segments = []
    start_time = 0.0

    for silence_end in silence_points:
        segment_duration = silence_end - start_time
        if segment_duration >= min_segment_duration:
            segments.append((start_time, silence_end))
            start_time = silence_end

    # 最后一段
    if duration - start_time >= min_segment_duration * 0.5:
        segments.append((start_time, duration))

    # 如果分段太少或每段太长，回退到等分
    if len(segments) < 2:
        logger.info("VAD 分段效果不佳，回退到等时切分")
        return _split_audio_equal(audio_path, output_dir, duration, max_segment_duration)

    # 检查是否有特别长的段，需要进一步切分
    final_segments = []
    for seg_start, seg_end in segments:
        seg_duration = seg_end - seg_start
        if seg_duration > max_segment_duration * 1.5:
            # 过长的段，等分
            num_sub = int(seg_duration / max_segment_duration) + 1
            sub_duration = seg_duration / num_sub
            for i in range(num_sub):
                final_segments.append((
                    seg_start + i * sub_duration,
                    min(seg_start + (i + 1) * sub_duration, seg_end)
                ))
        else:
            final_segments.append((seg_start, seg_end))

    # 切分音频
    segment_paths = []
    for i, (seg_start, seg_end) in enumerate(final_segments):
        seg_path = output_dir / f"mimo_seg_{i:03d}.mp3"
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-v", "quiet",
                "-i", str(audio_path),
                "-ss", str(seg_start),
                "-to", str(seg_end),
                "-c", "copy",
                str(seg_path),
            ],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and seg_path.exists():
            segment_paths.append(seg_path)

    return segment_paths


def _split_audio_equal(
    audio_path: Path,
    output_dir: Path,
    duration: float,
    segment_duration: float = 120.0,
) -> list[Path]:
    """
    按固定时长等分音频

    Args:
        audio_path: 输入音频路径
        output_dir: 输出目录
        duration: 音频总时长（秒）
        segment_duration: 每段时长（秒）

    Returns:
        分段音频路径列表
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    num_segments = max(1, int(duration / segment_duration) + (1 if duration % segment_duration > 0 else 0))
    segment_paths = []

    for i in range(num_segments):
        start_time = i * segment_duration
        seg_path = output_dir / f"mimo_seg_{i:03d}.mp3"
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-v", "quiet",
                "-i", str(audio_path),
                "-ss", str(start_time),
                "-t", str(segment_duration),
                "-c", "copy",
                str(seg_path),
            ],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and seg_path.exists():
            segment_paths.append(seg_path)

    return segment_paths


def _transcribe_mimo_parallel(audio_path: Path, duration: float, total_size_mb: float = 0) -> str:
    """
    并行分段调用 MiMo API 转写

    Args:
        audio_path: 音频路径
        duration: 音频时长（秒）
        total_size_mb: 音频总大小（MB），用于计算分段大小

    Returns:
        拼接后的完整转写文本
    """
    max_workers = getattr(cfg, 'MAX_PARALLEL_WORKERS', 4)

    # 根据音频时长和大小决定分段数量
    # 确保每段不超过 45MB（留余量给 base64 编码膨胀）
    max_segment_mb = 45
    min_segments_by_size = max(1, int(total_size_mb / max_segment_mb) + 1)
    min_segments_by_duration = max(2, int(duration / 120))
    num_segments = max(min_segments_by_size, min_segments_by_duration)
    num_segments = min(max_workers, num_segments)

    # 创建临时目录存放分段
    temp_dir = audio_path.parent / f"mimo_segments_{audio_path.stem}"

    try:
        # 尝试 VAD 分段
        segment_paths = _split_audio_by_vad(audio_path, temp_dir)

        if len(segment_paths) < 2:
            # VAD 分段失败，回退等分
            segment_paths = _split_audio_equal(audio_path, temp_dir, duration, duration / num_segments)

        logger.info(f"MiMo 并行转写: {len(segment_paths)} 个分段")

        # 并行转写
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_transcribe_mimo_single, p): p for p in segment_paths}
            for future in concurrent.futures.as_completed(futures):
                seg_path = futures[future]
                try:
                    text = future.result()
                    results.append((segment_paths.index(seg_path), text))
                    logger.debug(f"分段 {seg_path.name} 转写完成: {len(text)} 字符")
                except Exception as e:
                    logger.warning(f"分段 {seg_path.name} 转写失败: {e}")
                    # 单段失败不影响整体，继续其他段

        # 按分段顺序排序并拼接
        results.sort(key=lambda x: x[0])
        full_text = " ".join(text for _, text in results if text)

        return full_text

    finally:
        # 清理临时分段文件
        if temp_dir.exists():
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except OSError:
                pass


def is_mimo_available() -> bool:
    """检查 MiMo 是否可用（需要 API Key）"""
    return os.environ.get("MIMO_API_KEY") is not None


# ── 并行分段（仅用于 faster-whisper 回退） ──────────────────────────────

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


def _split_audio(audio_path: Path, output_dir: Path, num_segments: int) -> list[Path]:
    duration = _get_audio_duration(audio_path)
    segment_time = max(15, int(duration / num_segments))
    segment_pattern = str(output_dir / "segment_%03d.m4a")
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "quiet",
            "-i", str(audio_path),
            "-f", "segment",
            "-segment_time", str(segment_time),
            "-reset_timestamps", "1",
            "-c", "copy",
            segment_pattern,
        ],
        check=True,
    )
    return sorted(
        p for p in output_dir.iterdir() if p.name.startswith("segment_") and p.suffix == ".m4a"
    )


def transcribe_audio_parallel(
    audio_path: Path,
    model: Any,
    options: TranscriptionOptions | None = None,
    output_dir: Path | None = None,
) -> TranscriptResult:
    resolved_options = options or get_transcription_options("standard")
    num_workers = resolved_options.num_workers
    if num_workers <= 1:
        return _transcribe_with_model(
            model, audio_path, resolved_options, resolved_options.model_name,
        )
    if output_dir is None:
        output_dir = audio_path.parent

    segment_paths = _split_audio(audio_path, output_dir, num_workers)
    segment_options = replace(resolved_options, vad_filter=False)

    def transcribe_segment(path: Path) -> str:
        result = _transcribe_with_model(
            model, path, segment_options, resolved_options.model_name,
        )
        return result.cleaned_text

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(transcribe_segment, p) for p in segment_paths]
        results = [f.result() for f in futures]

    for p in segment_paths:
        try:
            p.unlink()
        except OSError:
            pass

    full_text = " ".join(results)
    if not full_text:
        raise TranscriptionError("未识别到可用语音内容。")
    return TranscriptResult(
        raw_text=full_text,
        cleaned_text=full_text,
        language=None,
        model_name=resolved_options.model_name,
        engine="faster-whisper",
    )
