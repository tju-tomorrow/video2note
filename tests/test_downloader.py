from pathlib import Path

import pytest

from video_extract2note.downloader import (
    DownloadError,
    _playwright_headless_enabled,
    download_audio,
)


class FakeYoutubeDL:
    received_options = None

    def __init__(self, options):
        self.options = options
        FakeYoutubeDL.received_options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def extract_info(self, url, download):
        assert url == "https://v.douyin.com/abc123/"
        assert download is True
        output_template = self.options["outtmpl"]
        output_dir = Path(output_template).parent
        audio_path = output_dir / "abc123.mp3"
        audio_path.write_bytes(b"fake audio")
        return {"id": "abc123"}


class RaisingYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def extract_info(self, url, download):
        raise RuntimeError("ffmpeg not found")


class CookiesYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def extract_info(self, url, download):
        raise RuntimeError("Fresh cookies (not necessarily logged in) are needed")


class CapturingYoutubeDL(FakeYoutubeDL):
    pass


class PlaywrightRetryYoutubeDL:
    attempts = []

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def extract_info(self, url, download):
        PlaywrightRetryYoutubeDL.attempts.append({"url": url, "options": self.options})
        output_template = self.options["outtmpl"]
        output_dir = Path(output_template).parent
        if self.options.get("cookiefile") is None:
            raise RuntimeError("Fresh cookies (not necessarily logged in) are needed")
        audio_path = output_dir / "abc123.mp3"
        audio_path.write_bytes(b"fake audio")
        return {"id": "abc123"}


class FakePage:
    visited_urls = []
    response_handler = None
    url = "https://www.douyin.com/video/fake"

    def on(self, event, handler):
        assert event == "response"
        FakePage.response_handler = handler

    def goto(self, url, wait_until, timeout):
        FakePage.visited_urls.append(url)
        self.url = url
        assert wait_until == "domcontentloaded"
        assert timeout in {30000, 45000}

    def wait_for_timeout(self, timeout):
        assert timeout in {5000, 12000}
        if (
            FakePage.response_handler is not None
            and FakePage.visited_urls[-1] == "https://v.douyin.com/abc123/"
            and timeout == 12000
        ):
            FakePage.response_handler(FakeResponse())

    def evaluate(self, js):
        assert js == "() => navigator.userAgent"
        return "FakeBrowser/1.0"


class FakeResponse:
    url = "https://media.example/video.mp4?mime_type=video_mp4"


class FakeContext:
    def new_page(self):
        return FakePage()

    def cookies(self, urls):
        assert "https://www.douyin.com" in urls
        return [
            {
                "domain": ".douyin.com",
                "path": "/",
                "name": "s_v_web_id",
                "value": "verify_fakevisitor",
                "expires": -1,
                "secure": False,
            }
        ]


class FakeBrowser:
    closed = False

    def new_context(self, **kwargs):
        assert kwargs["locale"] == "zh-CN"
        assert kwargs["viewport"] == {"width": 1280, "height": 900}
        return FakeContext()

    def close(self):
        FakeBrowser.closed = True


class FakeChromium:
    def launch(self, headless):
        FakeChromium.received_headless = headless
        assert isinstance(headless, bool)
        return FakeBrowser()


class FakePlaywright:
    chromium = FakeChromium()


class FakePlaywrightFactory:
    def __enter__(self):
        return FakePlaywright()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_download_audio_returns_created_audio_file(tmp_path):
    audio_path = download_audio(
        "https://v.douyin.com/abc123/",
        tmp_path,
        ydl_factory=FakeYoutubeDL,
    )

    assert audio_path == tmp_path / "abc123.mp3"
    assert audio_path.read_bytes() == b"fake audio"
    assert FakeYoutubeDL.received_options["format"] == "bestaudio/best"
    assert FakeYoutubeDL.received_options["noplaylist"] is True
    assert callable(FakeYoutubeDL.received_options["logger"].error)


def test_download_audio_reports_missing_ffmpeg(tmp_path):
    with pytest.raises(DownloadError, match="ffmpeg"):
        download_audio(
            "https://v.douyin.com/abc123/",
            tmp_path,
            ydl_factory=RaisingYoutubeDL,
        )


def test_download_audio_reports_missing_yt_dlp(tmp_path):
    with pytest.raises(DownloadError, match="yt-dlp 未安装"):
        download_audio(
            "https://v.douyin.com/abc123/",
            tmp_path,
            ydl_factory=None,
        )


def test_download_audio_reports_missing_playwright_media_url(tmp_path):
    with pytest.raises(DownloadError, match="访客 cookies"):
        download_audio(
            "https://www.douyin.com/video/7632608679321722266",
            tmp_path,
            ydl_factory=CookiesYoutubeDL,
            playwright_factory=FakePlaywrightFactory,
        )


def test_download_audio_can_load_cookies_from_browser(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_EXTRACT2NOTE_COOKIES_BROWSER", "chrome")

    download_audio(
        "https://v.douyin.com/abc123/",
        tmp_path,
        ydl_factory=CapturingYoutubeDL,
    )

    assert CapturingYoutubeDL.received_options["cookiesfrombrowser"] == ("chrome",)


def test_download_audio_retries_with_playwright_cookies_on_cookie_error(tmp_path):
    PlaywrightRetryYoutubeDL.attempts = []
    FakeBrowser.closed = False
    FakePage.visited_urls = []
    FakePage.response_handler = None

    audio_path = download_audio(
        "https://v.douyin.com/abc123/",
        tmp_path,
        ydl_factory=PlaywrightRetryYoutubeDL,
        playwright_factory=FakePlaywrightFactory,
    )

    assert audio_path == tmp_path / "abc123.mp3"
    assert PlaywrightRetryYoutubeDL.attempts[0]["url"] == "https://v.douyin.com/abc123/"
    assert "cookiefile" not in PlaywrightRetryYoutubeDL.attempts[0]["options"]
    assert PlaywrightRetryYoutubeDL.attempts[1]["url"] == "https://media.example/video.mp4?mime_type=video_mp4"
    assert PlaywrightRetryYoutubeDL.attempts[1]["options"]["outtmpl"].endswith("media.%(ext)s")
    cookiefile = PlaywrightRetryYoutubeDL.attempts[1]["options"]["cookiefile"]
    assert Path(cookiefile).read_text().startswith("# Netscape HTTP Cookie File")
    assert "s_v_web_id" in Path(cookiefile).read_text()
    assert PlaywrightRetryYoutubeDL.attempts[1]["options"]["http_headers"]["Referer"] == "https://v.douyin.com/abc123/"
    assert PlaywrightRetryYoutubeDL.attempts[1]["options"]["http_headers"]["User-Agent"] == "FakeBrowser/1.0"
    assert FakeBrowser.closed is True
    assert FakePage.visited_urls == [
        "https://www.douyin.com/",
        "https://v.douyin.com/abc123/",
    ]


def test_playwright_runs_headless_by_default(monkeypatch):
    monkeypatch.delenv("VIDEO_EXTRACT2NOTE_PLAYWRIGHT_HEADLESS", raising=False)
    monkeypatch.delenv("VIDEO_EXTRACT2NOTE_PLAYWRIGHT_HEADED", raising=False)

    assert _playwright_headless_enabled() is True


def test_playwright_can_be_forced_headed_for_debug(monkeypatch):
    monkeypatch.setenv("VIDEO_EXTRACT2NOTE_PLAYWRIGHT_HEADED", "1")
    monkeypatch.delenv("VIDEO_EXTRACT2NOTE_PLAYWRIGHT_HEADLESS", raising=False)

    assert _playwright_headless_enabled() is False


class CheckOptionsYoutubeDL:
    received_options = None

    def __init__(self, options):
        self.options = options
        CheckOptionsYoutubeDL.received_options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def extract_info(self, url, download):
        output_template = self.options["outtmpl"]
        output_dir = Path(output_template).parent
        audio_path = output_dir / "abc123.m4a"
        audio_path.write_bytes(b"fake raw audio")
        return {"id": "abc123"}


def test_download_audio_without_extract_audio_skips_ffmpeg_postprocessor(tmp_path):
    audio_path = download_audio(
        "https://v.douyin.com/abc123/",
        tmp_path,
        ydl_factory=CheckOptionsYoutubeDL,
        extract_audio=False,
    )

    assert "postprocessors" not in CheckOptionsYoutubeDL.received_options
    assert audio_path.suffix == ".m4a"
