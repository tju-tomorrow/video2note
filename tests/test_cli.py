import io
import shutil
import tempfile
from pathlib import Path

from video_extract2note.cli import main, run_once
from video_extract2note.downloader import DownloadError
from video_extract2note.transcriber import TranscriptionError


class TrackingTempDir:
    last_path = None

    def __enter__(self):
        self.path = tempfile.mkdtemp()
        TrackingTempDir.last_path = Path(self.path)
        return self.path

    def __exit__(self, exc_type, exc, traceback):
        shutil.rmtree(self.path)
        return False


def fake_run_pipeline_ok(url, output_dir):
    assert url == "https://v.douyin.com/abc123/"
    return "这是转写结果"


def fake_run_pipeline_download_error(url, output_dir):
    raise DownloadError("下载音频失败：请检查链接")


def fake_run_pipeline_transcription_error(url, output_dir):
    raise TranscriptionError("未识别到可用语音内容。")


def test_run_once_extracts_url_prints_text_and_cleans_tempdir(monkeypatch):
    monkeypatch.setattr("video_extract2note.cli.run_pipeline", fake_run_pipeline_ok)

    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_once(
        "分享文本 https://v.douyin.com/abc123/ 复制打开",
        temp_dir_factory=TrackingTempDir,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert "正在并行下载" in stdout.getvalue()
    assert "这是转写结果" in stdout.getvalue()
    assert stderr.getvalue() == ""
    assert TrackingTempDir.last_path is not None
    assert not TrackingTempDir.last_path.exists()


def test_run_once_reports_missing_url_before_download(monkeypatch):
    monkeypatch.setattr("video_extract2note.cli.run_pipeline", fake_run_pipeline_ok)

    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_once(
        "没有链接",
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "未找到有效链接" in stderr.getvalue()


def test_run_once_reports_download_error(monkeypatch):
    monkeypatch.setattr(
        "video_extract2note.cli.run_pipeline", fake_run_pipeline_download_error
    )

    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_once(
        "https://v.douyin.com/abc123/",
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert "下载音频失败" in stderr.getvalue()


def test_run_once_reports_transcription_error(monkeypatch):
    monkeypatch.setattr(
        "video_extract2note.cli.run_pipeline", fake_run_pipeline_transcription_error
    )

    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_once(
        "https://v.douyin.com/abc123/",
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert "未识别到可用语音内容" in stderr.getvalue()


def test_main_prompts_for_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "https://v.douyin.com/abc123/")
    monkeypatch.setattr("video_extract2note.cli.run_pipeline", fake_run_pipeline_ok)

    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", stderr)

    assert main() == 0
    assert "这是转写结果" in stdout.getvalue()
    assert stderr.getvalue() == ""
