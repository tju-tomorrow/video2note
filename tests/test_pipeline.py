import time
from pathlib import Path

import pytest

from video_extract2note.downloader import DownloadError
from video_extract2note.pipeline import run_pipeline
from video_extract2note.transcriber import TranscriptionError


@pytest.fixture(autouse=True)
def _mock_pipeline_deps(monkeypatch):
    """Skip LLM formatting and force faster-whisper path in tests."""
    monkeypatch.setattr(
        "video_extract2note.pipeline.format_transcript", lambda text, client=None: text
    )
    monkeypatch.setattr(
        "video_extract2note.pipeline.is_whisper_cpp_available", lambda: False
    )
    monkeypatch.setattr(
        "video_extract2note.pipeline.is_mimo_available", lambda: False
    )


class FakeYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def extract_info(self, url, download):
        time.sleep(0.05)
        output_template = self.options["outtmpl"]
        output_dir = Path(output_template).parent
        ext = "mp3" if "postprocessors" in self.options else "m4a"
        audio_path = output_dir / f"abc123.{ext}"
        audio_path.write_bytes(b"fake audio")
        return {"id": "abc123"}


class SlowYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def extract_info(self, url, download):
        time.sleep(0.3)
        output_template = self.options["outtmpl"]
        output_dir = Path(output_template).parent
        audio_path = output_dir / "abc123.m4a"
        audio_path.write_bytes(b"fake audio")
        return {"id": "abc123"}


class FailingYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def extract_info(self, url, download):
        raise RuntimeError("ffmpeg not found")


class FakeModel:
    def transcribe(self, audio_path, **kwargs):
        class FakeInfo:
            language = "zh"
            duration = 5.0

        class FakeSegment:
            text = "流水线转写结果"

        return iter([FakeSegment]), FakeInfo()


class FakeModelFactory:
    def __call__(self, model_name, **kwargs):
        time.sleep(0.05)
        return FakeModel()


class SlowModelFactory:
    def __call__(self, model_name, **kwargs):
        time.sleep(0.3)
        return FakeModel()


class FailingModelFactory:
    def __call__(self, model_name, **kwargs):
        raise RuntimeError("model load failure")


def test_run_pipeline_returns_cleaned_text(tmp_path):
    result = run_pipeline(
        "https://v.douyin.com/abc123/",
        tmp_path,
        ydl_factory=FakeYoutubeDL,
        model_factory=FakeModelFactory(),
    )

    assert result == "流水线转写结果"
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".m4a"


def test_run_pipeline_parallel_execution(tmp_path):
    start = time.perf_counter()
    run_pipeline(
        "https://v.douyin.com/abc123/",
        tmp_path,
        ydl_factory=SlowYoutubeDL,
        model_factory=SlowModelFactory(),
    )
    elapsed = time.perf_counter() - start

    # Both take ~0.3s each. If serial: ~0.6s. If parallel: ~0.3s.
    assert elapsed < 0.5, f"Expected parallel execution, took {elapsed:.2f}s"


def test_run_pipeline_download_error(tmp_path):
    with pytest.raises(DownloadError, match="ffmpeg"):
        run_pipeline(
            "https://v.douyin.com/abc123/",
            tmp_path,
            ydl_factory=FailingYoutubeDL,
            model_factory=FakeModelFactory(),
        )


def test_run_pipeline_model_error(tmp_path):
    with pytest.raises(TranscriptionError, match="faster-whisper"):
        run_pipeline(
            "https://v.douyin.com/abc123/",
            tmp_path,
            ydl_factory=FakeYoutubeDL,
            model_factory=None,
        )
