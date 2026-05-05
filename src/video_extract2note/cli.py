import sys
import tempfile
from pathlib import Path
from typing import Callable, TextIO

from video_extract2note.downloader import DownloadError
from video_extract2note.input_parser import extract_first_url
from video_extract2note.pipeline import run_pipeline
from video_extract2note.transcriber import TranscriptionError


def run_once(
    raw_input: str,
    download_func: Callable[[str, Path], Path] | None = None,
    transcribe_func: Callable[[Path], str] | None = None,
    temp_dir_factory: Callable[[], object] = tempfile.TemporaryDirectory,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    url = extract_first_url(raw_input)
    if url is None:
        print("未找到有效链接，请粘贴抖音分享链接或包含链接的分享文本。", file=stderr)
        return 1

    try:
        with temp_dir_factory() as temp_dir:
            output_dir = Path(temp_dir)
            print("正在并行下载音频并加载模型...", file=stdout)
            result = run_pipeline(url, output_dir)
            text = result.text
    except (DownloadError, TranscriptionError) as exc:
        print(str(exc), file=stderr)
        return 1

    print("", file=stdout)
    print(text, file=stdout)
    return 0


def main() -> int:
    raw_input = input("请输入抖音链接或分享文本: ")
    return run_once(
        raw_input,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
