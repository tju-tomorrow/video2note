import concurrent.futures
import json as _json
import logging
import os
import re
import shutil
import subprocess
import time
from html import unescape
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

import video_extract2note.config as cfg

logger = logging.getLogger(__name__)

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None


class DownloadError(RuntimeError):
    pass


def _curl_proxy_args() -> list[str]:
    """返回 curl 的代理参数列表，未配置代理则为空。"""
    if cfg.PROXY_URL:
        return ["--proxy", cfg.PROXY_URL]
    return []


def _playwright_proxy() -> dict[str, str] | None:
    """返回 Playwright proxy 参数，未配置则为 None。"""
    if cfg.PROXY_URL:
        return {"server": cfg.PROXY_URL}
    return None


class _QuietYtdlpLogger:
    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def _is_douyin_url(url: str) -> bool:
    domain = urlsplit(url).netloc.lower()
    return any(d in domain for d in ("douyin.com", "iesdouyin.com"))


def _is_cookie_error(error: Exception) -> bool:
    return "cookie" in str(error).lower()


def _map_download_error(error: Exception) -> DownloadError:
    message = str(error)
    if "ffmpeg" in message.lower():
        return DownloadError("ffmpeg 未安装或不可用，请安装 ffmpeg 后重试。")
    if "cookie" in message.lower():
        return DownloadError(
            "yt-dlp 需要浏览器生成的抖音访客 cookies，不一定需要登录。"
            "程序会尝试自动打开浏览器获取；如果浏览器没有安装，请运行："
            "python -m playwright install chromium"
        )
    # 抖音图文（/note/）没有视频/音频，yt-dlp 无法处理
    if "unsupported url" in message.lower():
        if "/note/" in message:
            return DownloadError(
                "该链接是抖音图文内容（非视频），没有音频无法转写。"
                "请粘贴视频链接（douyin.com/video/...）。"
            )
        return DownloadError(
            f"不支持的链接类型: {message}。请确认是抖音视频链接。"
        )
    return DownloadError(
        f"下载失败: {message}。请检查链接是否有效、网络是否可用、视频是否公开可访问，"
        "或尝试升级 yt-dlp 后重试：python -m pip install -U yt-dlp"
        )


def _is_media_url(url: str) -> bool:
    lowered = url.lower()
    path = urlsplit(url).path.lower()
    return any(
        token in lowered
        for token in (
            "douyinvod.com",
            "/video/tos/",
            "mime_type=video_mp4",
            "mime_type=audio",
            "video_id=",
        )
    ) or path.endswith((".mp4", ".m4a", ".mp3", ".aac", ".m3u8"))


def _media_url_score(url: str) -> int:
    lowered = url.lower()
    score = 0
    if "douyinvod.com" in lowered:
        score += 80
    if "/video/tos/" in lowered:
        score += 80
    if "mime_type=video_mp4" in lowered or "mime_type=audio" in lowered:
        score += 60
    if "__vid=" in lowered or "video_id=" in lowered:
        score += 30
    if urlsplit(url).path.lower().endswith((".m4a", ".mp3", ".aac")):
        score += 20
    if any(
        token in lowered
        for token in (
            "douyinstatic.com",
            "byteeffecttos.com",
            "effectcdn",
            "douyin-pc-web",
        )
    ):
        score -= 120
    return score


def _select_best_media_url(urls: list[str]) -> str | None:
    if not urls:
        return None
    best = max(urls, key=_media_url_score)
    return best if _media_url_score(best) > 0 else None


def _is_media_response(response: Any) -> bool:
    if _is_media_url(response.url):
        return True
    try:
        content_type = response.headers.get("content-type", "").lower()
    except Exception:
        return False
    return content_type.startswith(("video/", "audio/"))


_URL_CANDIDATE_RE = re.compile(
    r"https?(?::|%3A)(?://|\\/\\/|%2F%2F)[^\"'<>\s]+",
    re.IGNORECASE,
)


def _normalize_url_candidate(candidate: str) -> str:
    normalized = unescape(candidate)
    for _ in range(3):
        decoded = unquote(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    return (
        normalized.replace("\\/", "/")
        .replace("\\u002F", "/")
        .replace("\\u002f", "/")
        .replace("\\u0026", "&")
        .replace("\\u003d", "=")
        .strip()
        .rstrip("\\\"'`;)")
    )


def _extract_media_urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in _URL_CANDIDATE_RE.finditer(text):
        url = _normalize_url_candidate(match.group(0))
        if _is_media_url(url) and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _append_unique(target: list[str], candidates: list[str]) -> None:
    seen = set(target)
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            target.append(candidate)


def _is_timeout_error(error: Exception) -> bool:
    return "timeout" in type(error).__name__.lower() or "timeout" in str(error).lower()


def _download_attempt(
    url: str,
    output_dir: Path,
    ydl_factory: Callable[[dict[str, Any]], Any],
    cookies_browser: str | None,
    format_str: str = "bestaudio/best",
    cookiefile: Path | None = None,
    extra_headers: dict[str, str] | None = None,
    extract_audio: bool = True,
    file_stem: str = "media",
) -> None:
    output_template = (
        str(output_dir / f"{file_stem}.%(ext)s")
        if _is_media_url(url)
        else str(output_dir / f"{file_stem}_%(id)s.%(ext)s")
    )

    options: dict[str, Any] = {
        "format": format_str,
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "logger": _QuietYtdlpLogger(),
    }
    if extract_audio:
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ]
    if cookies_browser:
        options["cookiesfrombrowser"] = (cookies_browser,)
    if cookiefile is not None:
        options["cookiefile"] = str(cookiefile)
    if extra_headers:
        options["http_headers"] = extra_headers

    with redirect_stderr(StringIO()):
        with ydl_factory(options) as ydl:
            ydl.extract_info(url, download=True)


def _remove_downloaded_files(output_dir: Path, cookiefile: Path | None) -> None:
    for stale_file in output_dir.iterdir():
        if stale_file.is_file() and stale_file != cookiefile:
            stale_file.unlink()


def _load_default_playwright_factory() -> Callable[[], Any] | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


def _write_netscape_cookie_file(cookies: list[dict[str, Any]], cookiefile: Path) -> None:
    lines = ["# Netscape HTTP Cookie File\n"]
    for cookie in cookies:
        domain = cookie["domain"]
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = cookie.get("path") or "/"
        secure = "TRUE" if cookie.get("secure") else "FALSE"
        expires = int(cookie.get("expires") or 0)
        if expires <= 0:
            expires = 2147483647
        name = cookie["name"]
        value = cookie["value"]
        lines.append(
            f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"
        )
    cookiefile.write_text("".join(lines))


def _cookie_cache_path() -> Path:
    return cfg.COOKIE_CACHE_DIR / "douyin_cookies.txt"


def _load_cached_cookies() -> tuple[Path, dict[str, str], bool] | None:
    """加载缓存的 cookie 文件。

    Returns:
        (cookiefile, headers, stale) 或 None（不存在/彻底过期）
        stale=True 表示超过刷新阈值但仍可尝试使用
    """
    cache = _cookie_cache_path()
    if not cache.exists():
        return None
    try:
        age = time.time() - cache.stat().st_mtime
        if age > cfg.COOKIE_MAX_USABLE_SECONDS:
            logger.info("Cookie 缓存已超过 %.1f 小时，彻底丢弃", age / 3600)
            return None
        stale = age > cfg.COOKIE_REFRESH_AFTER_SECONDS
        if stale:
            logger.info("Cookie 缓存已过期 (%.1f 小时)，但仍尝试使用", age / 3600)
    except OSError:
        return None
    headers = {
        "Referer": "https://www.douyin.com/",
        "User-Agent": _DOUYIN_UA,
    }
    return cache, headers, stale


def _save_cached_cookies(cookiefile: Path) -> None:
    """将 cookie 文件保存到缓存目录。"""
    cache = _cookie_cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(cookiefile), str(cache))


_COOKIE_CACHE_TIME = "cookie_cache_time"


def _create_playwright_session(
    url: str,
    output_dir: Path,
    playwright_factory: Callable[[], Any] | None,
) -> tuple[Path, str | None, dict[str, str]]:
    if playwright_factory is None:
        playwright_factory = _load_default_playwright_factory()
    if playwright_factory is None:
        raise DownloadError(
            "Playwright 未安装，无法自动获取抖音访客 cookies。请运行："
            "python -m pip install playwright && python -m playwright install chromium"
        )

    headless = _playwright_headless_enabled()
    proxy = _playwright_proxy()
    try:
        with playwright_factory() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            try:
                context = browser.new_context(
                    locale="zh-CN",
                    viewport={"width": 1280, "height": 900},
                    proxy=proxy,
                )
                page = context.new_page()
                media_urls: list[str] = []

                def collect_media_url(response: Any) -> None:
                    if _is_media_response(response):
                        _append_unique(media_urls, [response.url])

                page.on("response", collect_media_url)
                page.goto(
                    "https://www.douyin.com/",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                page.wait_for_timeout(5000)
                try:
                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=45000,
                    )
                except Exception as exc:
                    if not _is_timeout_error(exc):
                        raise
                page.wait_for_timeout(12000)
                for _ in range(3):
                    try:
                        page.mouse.click(640, 450)
                    except Exception:
                        pass
                    try:
                        page.keyboard.press("Space")
                    except Exception:
                        pass
                    page.wait_for_timeout(5000)
                    try:
                        candidate_urls = page.evaluate(
                            """() => {
                                const urls = new Set();
                                for (const item of performance.getEntriesByType('resource')) {
                                    if (item && item.name) urls.add(item.name);
                                }
                                for (const node of document.querySelectorAll('video, source')) {
                                    if (node.currentSrc) urls.add(node.currentSrc);
                                    if (node.src) urls.add(node.src);
                                }
                                return Array.from(urls);
                            }"""
                        )
                        _append_unique(
                            media_urls,
                            [candidate for candidate in candidate_urls if _is_media_url(candidate)],
                        )
                    except Exception:
                        pass
                    try:
                        _append_unique(media_urls, _extract_media_urls_from_text(page.content()))
                    except Exception:
                        pass
                    if _select_best_media_url(media_urls) is not None:
                        break
                cookies = context.cookies(["https://www.douyin.com", "https://v.douyin.com"])
                headers = {
                    "Referer": page.url,
                    "User-Agent": page.evaluate("() => navigator.userAgent"),
                }
            finally:
                browser.close()
    except Exception as exc:
        raise DownloadError(
            "自动启动浏览器获取抖音访客 cookies 失败。请确认已运行："
            "python -m playwright install chromium"
        ) from exc

    if not cookies:
        raise DownloadError("浏览器没有生成可用的抖音 cookies，请手动打开 douyin.com 后重试。")

    cookiefile = output_dir / "douyin-playwright-cookies.txt"
    _write_netscape_cookie_file(cookies, cookiefile)
    _save_cached_cookies(cookiefile)
    return cookiefile, _select_best_media_url(media_urls), headers


def _playwright_headless_enabled() -> bool:
    headless_override = os.environ.get("VIDEO_EXTRACT2NOTE_PLAYWRIGHT_HEADLESS", "")
    headed_override = os.environ.get("VIDEO_EXTRACT2NOTE_PLAYWRIGHT_HEADED", "")
    if headless_override.strip():
        return headless_override.strip().lower() in ("1", "true", "yes")
    if headed_override.strip():
        return headed_override.strip().lower() not in ("1", "true", "yes")
    return True


def _download_with_format(
    url: str,
    output_dir: Path,
    format_str: str,
    ydl_factory: Callable[[dict[str, Any]], Any] | None = YoutubeDL,
    playwright_factory: Callable[[], Any] | None = None,
    extract_audio: bool = True,
    file_stem: str = "media",
) -> Path:
    if ydl_factory is None:
        raise DownloadError("yt-dlp 未安装，请先运行：python -m pip install yt-dlp")

    output_dir.mkdir(parents=True, exist_ok=True)

    # 提前检测图文链接，避免走到 yt-dlp 再报错
    note_error = _check_douyin_note(url)
    if note_error:
        raise DownloadError(note_error)

    explicit_browser = os.environ.get("VIDEO_EXTRACT2NOTE_COOKIES_BROWSER", "").strip()
    cookies_browser = explicit_browser or None

    # 只有抖音需要 cookies，B站等平台直接走 yt-dlp
    cached = None
    stale = False
    if _is_douyin_url(url) and not explicit_browser:
        result = _load_cached_cookies()
        if result is not None:
            cached = (result[0], result[1])
            stale = result[2]

    try:
        logger.debug("yt-dlp 下载尝试: %s (stale=%s)", url, stale)
        _download_attempt(
            url, output_dir, ydl_factory, cookies_browser,
            format_str=format_str, extract_audio=extract_audio, file_stem=file_stem,
            cookiefile=cached[0] if cached else None,
            extra_headers=cached[1] if cached else None,
        )
    except Exception as exc:
        if not _is_cookie_error(exc) or explicit_browser:
            raise _map_download_error(exc) from exc

        logger.warning("yt-dlp cookie 错误，启动 Playwright 获取 cookies")
        cookiefile, media_url, media_headers = _create_playwright_session(
            url,
            output_dir,
            playwright_factory,
        )
        media_retry_error: Exception | None = None
        if media_url is not None:
            _remove_downloaded_files(output_dir, cookiefile)
            try:
                _download_attempt(
                    media_url,
                    output_dir,
                    ydl_factory,
                    None,
                    format_str=format_str,
                    cookiefile=cookiefile,
                    extra_headers=media_headers,
                    extract_audio=extract_audio,
                    file_stem=file_stem,
                )
            except Exception as retry_exc:
                media_retry_error = retry_exc

        if media_url is None or media_retry_error is not None:
            _remove_downloaded_files(output_dir, cookiefile)
            try:
                _download_attempt(
                    url,
                    output_dir,
                    ydl_factory,
                    None,
                    format_str=format_str,
                    cookiefile=cookiefile,
                    extra_headers=media_headers,
                    extract_audio=extract_audio,
                    file_stem=file_stem,
                )
            except Exception as retry_exc:
                raise _map_download_error(media_retry_error or retry_exc) from retry_exc

    files = [
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name != "douyin-playwright-cookies.txt"
    ]
    if not files:
        raise DownloadError("下载完成后未找到文件，请升级 yt-dlp 后重试。")

    return max(files, key=lambda path: path.stat().st_mtime)


# ── 抖音直链解析（秒级提取，绕过 yt-dlp） ──────────────────────────────

_DOUYIN_UA = cfg.DOUYIN_USER_AGENT

_DOUYIN_VIDEO_ID_RE = re.compile(r"/video/(\d{15,20})")
_DOUYIN_MODAL_ID_RE = re.compile(r"[?&]modal_id=(\d{15,20})")
_DOUYIN_SHARE_VIDEO_RE = re.compile(r"/share/video/(\d{15,20})")
_DOUYIN_NOTE_RE = re.compile(r"/note/(\d+)")
_DOUYIN_VIDEO_URL_RE = re.compile(r"douyin\.com/video/")


def _curl_final_url(url: str, timeout: int = 10) -> str | None:
    """用 curl 跟随重定向，返回最终 URL。"""
    try:
        result = subprocess.run(
            ["curl", "-sSL", "-o", "/dev/null", "-w", "%{url_effective}",
             "-A", _DOUYIN_UA, "--max-time", str(timeout), *_curl_proxy_args(), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        final = result.stdout.strip()
        return final if final else None
    except Exception:
        return None


def _curl_get_json(url: str, referer: str | None = None, timeout: int = 10,
                   extra_headers: dict[str, str] | None = None) -> tuple[dict | None, str]:
    """用 curl GET 请求并解析 JSON 响应。返回 (data, error_reason)。"""
    cmd = ["curl", "-sS", "-A", _DOUYIN_UA, "--max-time", str(timeout), *_curl_proxy_args()]
    if referer:
        cmd.extend(["-H", f"Referer: {referer}"])
    if extra_headers:
        for k, v in extra_headers.items():
            cmd.extend(["-H", f"{k}: {v}"])
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        if result.returncode != 0:
            err = result.stderr.strip()
            return None, err if err else f"curl exit={result.returncode}"
        stdout = result.stdout.strip()
        if not stdout:
            return None, "API返回空"
        try:
            return _json.loads(stdout), ""
        except _json.JSONDecodeError:
            return None, f"JSON解析失败: {stdout[:120]}"
    except subprocess.TimeoutExpired:
        return None, "超时"
    except Exception as exc:
        return None, str(exc)


def _curl_head_headers(url: str, timeout: int = 10) -> dict[str, str] | None:
    """用 curl 发送 HEAD 请求，返回响应头字典。"""
    try:
        result = subprocess.run(
            ["curl", "-sSL", "-I", "-A", _DOUYIN_UA, "--max-time", str(timeout), *_curl_proxy_args(), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode != 0:
            return None
        headers: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()
        return headers if headers else None
    except Exception:
        return None


def _curl_download(url: str, dest: Path, headers: dict[str, str] | None = None,
                   timeout: int = 120) -> bool:
    """用 curl 下载文件到指定路径。"""
    cmd = ["curl", "-sSL", "-A", _DOUYIN_UA, "-o", str(dest),
           "--max-time", str(timeout), "--retry", "2", *_curl_proxy_args()]
    if headers:
        for k, v in headers.items():
            cmd.extend(["-H", f"{k}: {v}"])
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        return result.returncode == 0 and dest.stat().st_size > 1024
    except Exception:
        return False


def _check_douyin_note(url: str) -> str | None:
    """如果是图文链接，返回友好提示；否则返回 None。"""
    if _DOUYIN_NOTE_RE.search(url):
        return "该链接是抖音图文内容（非视频），没有音频无法转写。请粘贴视频链接。"
    return None


def _resolve_douyin_video_id(short_url: str) -> str | None:
    """跟随短链跳转，提取抖音视频 ID。图文返回 None。"""
    # 先尝试直接从 URL 提取（支持 share/video 和普通 /video/ 格式）
    m = _DOUYIN_SHARE_VIDEO_RE.search(short_url)
    if m:
        return m.group(1)
    m = _DOUYIN_VIDEO_ID_RE.search(short_url)
    if m:
        return m.group(1)
    m = _DOUYIN_MODAL_ID_RE.search(short_url)
    if m:
        return m.group(1)

    # 短链接（v.douyin.com），跟随重定向
    final_url = _curl_final_url(short_url)
    if final_url is None:
        return None

    if _DOUYIN_NOTE_RE.search(final_url) and not _DOUYIN_VIDEO_URL_RE.search(final_url):
        return None

    m = _DOUYIN_VIDEO_ID_RE.search(final_url)
    if m:
        return m.group(1)
    m = _DOUYIN_MODAL_ID_RE.search(final_url)
    if m:
        return m.group(1)
    return None


def _scrape_video_page(video_id: str) -> tuple[str | None, str]:
    """从抖音视频页面 HTML 提取无水印视频直链。返回 (url, error_reason)。"""
    page_url = f"https://www.douyin.com/video/{video_id}"
    desktop_ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # 尝试用缓存的 cookie 获取页面（反爬需要）
    cmd = ["curl", "-sS", "-A", desktop_ua,
           "-H", "Accept: text/html,application/json",
           "--max-time", "15", *_curl_proxy_args()]
    cached = _load_cached_cookies()
    if cached:
        cmd.extend(["-b", str(cached[0])])
    cmd.append(page_url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode != 0:
            return None, f"页面请求失败: {result.stderr.strip()[:80]}"
        html = result.stdout
    except subprocess.TimeoutExpired:
        return None, "页面请求超时"
    except Exception as exc:
        return None, str(exc)[:80]

    if not html or len(html) < 500:
        return None, "页面返回空或太短"

    # 方式1: <script id="RENDER_DATA"> ... </script>
    m = re.search(r'<script[^>]*id="RENDER_DATA"[^>]*>([^<]+)</script>', html)
    if m:
        try:
            from urllib.parse import unquote as _unquote
            raw = _unquote(m.group(1))
            data = _json.loads(raw)
            # RENDER_DATA 结构: { "app": { "video": {...} } } 或直接包含 video 信息
            video_info = _extract_video_from_json(data)
            if video_info:
                return video_info, ""
        except Exception:
            pass

    # 方式2: window.__INITIAL_STATE__ = {...}
    m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?})\s*;</script>', html, re.DOTALL)
    if not m:
        m = re.search(r'Self\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
    if m:
        try:
            raw_js = m.group(1)
            # 处理 JS 对象中的 undefined
            raw_js = re.sub(r'\bundefined\b', 'null', raw_js)
            data = _json.loads(raw_js)
            video_info = _extract_video_from_json(data)
            if video_info:
                return video_info, ""
        except Exception:
            pass

    # 方式3: 直接在 HTML 中搜索视频 URL
    vod_match = re.search(r'//[^"\'<>]+douyinvod\.com[^"\'<>\s]+', html)
    if vod_match:
        url = "https:" + vod_match.group(0)
        return url, ""

    # 方式4: 搜索任何看起来像视频 CDN 的 URL
    for pattern in [
        r'"url_list"\s*:\s*\["([^"]+)"',
        r'https?://[^"\'<>\s]+/video/tos/[^"\'<>\s]+',
    ]:
        m = re.search(pattern, html)
        if m:
            url = m.group(1) if '"url_list"' in pattern else m.group(0)
            if _is_media_url(url):
                return url, ""

    return None, "页面中未找到视频数据"


def _extract_video_url_via_ytdlp(url: str, output_dir: Path,
                                  ydl_factory: Callable | None = None) -> tuple[str | None, str]:
    """用 yt-dlp 仅提取视频 URL（不下载），然后用 curl 下载。"""
    if ydl_factory is None:
        try:
            from yt_dlp import YoutubeDL
            ydl_factory = YoutubeDL
        except ImportError:
            return None, "yt-dlp未安装"

    cookiefile = None
    cached = _load_cached_cookies()
    if cached:
        cookiefile = cached[0]

    options: dict[str, Any] = {
        "format": "best",
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,  # 只提取信息，不下载
    }
    if cookiefile is not None:
        options["cookiefile"] = str(cookiefile)

    try:
        with redirect_stderr(StringIO()):
            with ydl_factory(options) as ydl:
                info = ydl.extract_info(url, download=False)
        # 从 info 中提取直接 URL
        for fmt in (info.get("formats") or []):
            direct_url = fmt.get("url")
            if direct_url and _is_media_url(direct_url):
                return direct_url, ""
        # 尝试直接的 URL 字段
        direct_url = info.get("url") or info.get("webpage_url")
        if direct_url and _is_media_url(direct_url):
            return direct_url, ""
        return None, "yt-dlp未提取到视频URL"
    except Exception as exc:
        return None, str(exc)[:80]


def _extract_video_from_json(data: dict) -> str | None:
    """从抖音 JSON 数据中递归搜索视频 URL。"""
    if isinstance(data, dict):
        # 直接搜索 play_addr.url_list
        for key in ("play_addr", "playAddr", "download_addr", "video", "bit_rate"):
            if key in data:
                inner = data[key]
                if isinstance(inner, dict):
                    urls = inner.get("url_list") or inner.get("urlList") or []
                    if urls:
                        url = urls[0]
                        return url.replace("playwm", "play") if isinstance(url, str) else None
        # 递归搜索
        for key in ("aweme_detail", "video", "item_list", "app", "data", "detail"):
            if key in data:
                result = _extract_video_from_json(data[key])
                if result:
                    return result
        # 搜索列表中的第一个元素
        for key, val in data.items():
            if isinstance(val, (dict, list)):
                result = _extract_video_from_json(val)
                if result:
                    return result
    elif isinstance(data, list) and data:
        for item in data:
            if isinstance(item, (dict, list)):
                result = _extract_video_from_json(item)
                if result:
                    return result
    return None


_PARALLEL_CHUNKS = cfg.PARALLEL_DOWNLOAD_CHUNKS
_PARALLEL_MIN_SIZE = cfg.PARALLEL_DOWNLOAD_MIN_SIZE


def _fetch_headers(url: str) -> dict[str, str] | None:
    """发送 HEAD 请求，获取 Content-Length 和 Accept-Ranges。"""
    return _curl_head_headers(url)


def _download_range(url: str, start: int, end: int, dest: Path) -> bool:
    """下载指定字节范围到临时文件。"""
    return _curl_download(url, dest, headers={"Range": f"bytes={start}-{end}"})


def _download_http_file(url: str, dest: Path) -> tuple[bool, str]:
    """并行分块下载：4 线程同时拉取，合并写入目标文件。

    返回 (成功, 方式)，方式为 "parallel" / "curl" / "urllib"。
    """
    headers = _fetch_headers(url)
    content_length: int | None = None
    if headers:
        cl = headers.get("content-length")
        if cl and cl.isdigit():
            content_length = int(cl)

    # 小文件或无法获取大小时回退单线程 curl
    if content_length is None or content_length < _PARALLEL_MIN_SIZE:
        ok = _download_single(url, dest)
        return ok, "curl"

    # 检查是否支持 Range
    accept_ranges = (headers or {}).get("accept-ranges", "").lower()
    if "bytes" not in accept_ranges:
        ok = _download_single(url, dest)
        return ok, "curl"

    # 并行分块下载
    chunk_size = content_length // _PARALLEL_CHUNKS
    temp_files: list[Path] = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=_PARALLEL_CHUNKS) as pool:
            futures: list[tuple[int, concurrent.futures.Future[bool]]] = []
            for i in range(_PARALLEL_CHUNKS):
                start = i * chunk_size
                end = content_length - 1 if i == _PARALLEL_CHUNKS - 1 else start + chunk_size - 1
                tf = dest.parent / f".chunk_{i}_{dest.name}"
                temp_files.append(tf)
                futures.append((i, pool.submit(_download_range, url, start, end, tf)))

            for _idx, fut in futures:
                if not fut.result():
                    return False, "parallel"

        with open(dest, "wb") as out:
            for tf in temp_files:
                with open(tf, "rb") as chunk:
                    shutil.copyfileobj(chunk, out)
        return (dest.stat().st_size > 1024), "parallel"
    except Exception:
        return False, "parallel"
    finally:
        for tf in temp_files:
            try:
                tf.unlink()
            except OSError:
                pass


def _download_single(url: str, dest: Path) -> bool:
    """单线程 curl 下载。"""
    return _curl_download(url, dest)


def _probe_video_streams(src: Path) -> dict | None:
    """用 ffprobe 探测视频流信息。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "v:0", str(src)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        streams = _json.loads(result.stdout).get("streams", [])
        if not streams:
            return None
        return streams[0]
    except Exception:
        return None


def _is_chromium_compatible(video_info: dict) -> bool:
    """判断视频是否已被转码为 Chromium 兼容格式。"""
    codec = video_info.get("codec_name", "")
    profile = video_info.get("profile", "")
    pix_fmt = video_info.get("pix_fmt", "")

    return (
        codec == "h264"
        and profile.lower() in ("baseline", "constrained baseline")
        and pix_fmt == "yuv420p"
    )


def _normalize_video(src: Path, dest: Path) -> Path | None:
    """将视频转为 Chromium 兼容格式（H.264 baseline + yuv420p + AAC LC）。"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src),
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-profile:v", "baseline", "-level", "4.0",
             "-x264-params", "bframes=0:cabac=0:ref=1",
             "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", str(dest)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return None
        if dest.stat().st_size < 1024:
            return None
        # 验证输出是有效的 H.264 baseline + yuv420p
        info = _probe_video_streams(dest)
        if info is None:
            return None
        codec = info.get("codec_name", "")
        pix_fmt = info.get("pix_fmt", "")
        if codec != "h264" or pix_fmt != "yuv420p":
            return None
        return dest
    except Exception:
        return None


def _douyin_direct(url: str, output_dir: Path, file_stem: str) -> tuple[Path | None, str]:
    """抖音直链下载入口，返回 (path, 诊断信息)。path 为 None 表示失败。"""
    video_id = _resolve_douyin_video_id(url)
    if not video_id:
        return None, "直链:短链解析失败"

    # 方式1: 页面抓取（最快，无需 yt-dlp）
    video_url, scrape_err = _scrape_video_page(video_id)
    if video_url:
        pass  # 继续往下走到下载逻辑
    else:
        # 方式2: yt-dlp 提取 URL（用规范化后的 douyin.com/video/{id}，避免 iesdouyin.com 重定向）
        norm_url = f"https://www.douyin.com/video/{video_id}"
        video_url, scrape_err = _extract_video_url_via_ytdlp(norm_url, output_dir)
        if video_url:
            scrape_err = ""  # 成功，清除错误

    if not video_url:
        return None, f"直链:视频地址获取失败({scrape_err or '未知'})"

    ext = ".mp4"
    dest = output_dir / f"{file_stem}{ext}"

    ok, dl_method = _download_http_file(video_url, dest)
    if not ok:
        return None, f"直链:下载失败({dl_method})"

    return dest, f"直链+{dl_method}"


_BILIBILI_DOMAINS = cfg.BILIBILI_DOMAINS


def _is_bilibili_url(url: str) -> bool:
    return urlsplit(url).netloc.lower().rstrip("/") in _BILIBILI_DOMAINS


def _bilibili_extract_video_info(page) -> dict | None:
    """从 B站页面提取视频元信息。"""
    state = page.evaluate("() => window.__INITIAL_STATE__")
    if not state:
        return None
    video_data = state.get("videoData", {})
    if not video_data:
        return None
    return {
        "title": video_data.get("title", ""),
        "bvid": video_data.get("bvid", ""),
        "aid": video_data.get("aid", 0),
        "cid": video_data.get("cid", 0),
        "duration": video_data.get("duration", 0),
    }


def _bilibili_fetch_audio_urls(page, info: dict) -> list[dict]:
    """通过 B站 playurl API 获取音频流列表。"""
    result = page.evaluate(
        """async (params) => {
            const url = 'https://api.bilibili.com/x/player/wbi/playurl?avid='
                + params.aid + '&bvid=' + params.bvid + '&cid=' + params.cid
                + '&qn=0&fnver=0&fnval=4048&fourk=1';
            const resp = await fetch(url, {credentials: 'include'});
            return await resp.json();
        }""",
        {"aid": info["aid"], "bvid": info["bvid"], "cid": info["cid"]},
    )
    if result.get("code") != 0:
        return []
    dash = result["data"].get("dash", {})
    return dash.get("audio", [])


def _bilibili_direct_audio(
    url: str,
    output_dir: Path,
    playwright_factory: Callable[[], Any] | None = None,
) -> tuple[Path | None, str]:
    """通过 Playwright 直接获取 B站音频流。返回 (path, 方式)。"""
    if playwright_factory is None:
        playwright_factory = _load_default_playwright_factory()
    if playwright_factory is None:
        return None, "B站直链:Playwright未安装"

    headless = _playwright_headless_enabled()
    proxy = _playwright_proxy()
    try:
        with playwright_factory() as playwright:
            browser = playwright.chromium.launch(
                headless=headless,
                args=cfg.STEALTH_ARGS,
            )
            try:
                context = browser.new_context(proxy=proxy)
                page = context.new_page(
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                )
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # 等待视频播放器加载
                page.wait_for_timeout(3000)
                try:
                    page.wait_for_selector("video", timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(2000)

                info = _bilibili_extract_video_info(page)
                if not info:
                    return None, "B站直链:无法提取视频信息"

                audio_urls = _bilibili_fetch_audio_urls(page, info)
                if not audio_urls:
                    return None, "B站直链:无法获取音频流"

                # 选最高码率
                best = max(audio_urls, key=lambda a: a.get("bandwidth", 0))
                audio_url = best.get("baseUrl", best.get("base_url", ""))
                if not audio_url:
                    return None, "B站直链:音频URL为空"

                # 从 Playwright 获取 cookies/headers 用于下载
                cookies = page.context.cookies()
                user_agent = page.evaluate("() => navigator.userAgent")

            finally:
                browser.close()
    except Exception as exc:
        return None, f"B站直链:Playwright异常({exc})"

    # 下载音频文件
    ext = ".m4s"
    dest = output_dir / f"audio{ext}"
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    cmd = [
        "curl", "-sSL", "-A", user_agent, "-H", f"Referer: https://www.bilibili.com/",
        "-H", f"Cookie: {cookie_str}", "-H", f"Origin: https://www.bilibili.com",
        "-o", str(dest), "--max-time", "120", "--retry", "2", *_curl_proxy_args(), audio_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=130)
    if result.returncode != 0 or dest.stat().st_size < 1024:
        return None, "B站直链:音频下载失败"

    return dest, "B站直链+playwright"


def download_audio(
    url: str,
    output_dir: Path,
    ydl_factory: Callable[[dict[str, Any]], Any] | None = YoutubeDL,
    playwright_factory: Callable[[], Any] | None = None,
    extract_audio: bool = True,
) -> Path:
    logger.info("下载音频: %s", url)

    # 只有抖音需要 URL 规范化，B站等平台直接用原始 URL
    ytdlp_url = url
    if _is_douyin_url(url):
        video_id = _resolve_douyin_video_id(url)
        if video_id:
            ytdlp_url = f"https://www.douyin.com/video/{video_id}"

    # B站优先走 Playwright 直链（绕过 yt-dlp 的 412 反爬）
    if _is_bilibili_url(url):
        logger.info("B站: 尝试 Playwright 直链获取音频")
        direct_path, direct_info = _bilibili_direct_audio(
            url, output_dir, playwright_factory
        )
        if direct_path is not None:
            logger.info("B站直链成功: %s", direct_info)
            return direct_path
        logger.warning("B站直链失败，回退 yt-dlp")

    return _download_with_format(
        ytdlp_url, output_dir,
        format_str="bestaudio/best",
        ydl_factory=ydl_factory,
        playwright_factory=playwright_factory,
        extract_audio=extract_audio,
        file_stem="audio",
    )


def download_video(
    url: str,
    output_dir: Path,
    ydl_factory: Callable[[dict[str, Any]], Any] | None = YoutubeDL,
    playwright_factory: Callable[[], Any] | None = None,
) -> tuple[Path, str]:
    """下载视频，返回 (路径, 下载方式)。

    下载方式如 "直链+parallel"、"直链:短链解析失败→yt-dlp" 等。
    """
    # 优先走抖音直链解析（秒级，无水印，无需 cookie）
    direct_path, direct_info = _douyin_direct(url, output_dir, "video")
    if direct_path is not None:
        return direct_path, direct_info

    # 回退 yt-dlp（附带直链失败原因）
    # 把 iesdouyin.com/share/video/ 规范化为 douyin.com/video/，yt-dlp 才认识
    ytdlp_url = url
    video_id = _resolve_douyin_video_id(url)
    if video_id:
        ytdlp_url = f"https://www.douyin.com/video/{video_id}"
    path = _download_with_format(
        ytdlp_url, output_dir,
        format_str="best",
        ydl_factory=ydl_factory,
        playwright_factory=playwright_factory,
        extract_audio=False,
        file_stem="video",
    )
    return path, f"{direct_info}→yt-dlp"
