"""网页内容抓取模块：Playwright 优先，curl 降级。

策略：
1. Playwright stealth 模式（反检测 + JS 渲染）
2. Playwright 失败 → curl + 纯 HTML 解析（无 JS 渲染）
"""

import logging
import re
import subprocess
from urllib.parse import urlparse
from html.parser import HTMLParser

import video_extract2note.config as cfg

logger = logging.getLogger(__name__)

_JS_HEAVY_DOMAINS = cfg.JS_HEAVY_DOMAINS
_STEALTH_DOMAINS = cfg.STEALTH_DOMAINS
_MIN_CONTENT_LENGTH = cfg.MIN_WEB_CONTENT_LENGTH
_STEALTH_ARGS = cfg.STEALTH_ARGS


class WebFetchError(RuntimeError):
    pass


# ── HTML → 纯文本解析器（curl 降级用）──

class _HTMLTextExtractor(HTMLParser):
    """提取 HTML 中的可见文本，保留标题和段落结构。"""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "head"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0
        self._title: str = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote"):
            self._parts.append("\n")
        if tag in ("h1", "h2", "h3"):
            self._parts.append("## ")

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "title":
            self._in_title = False
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "li", "tr", "blockquote"):
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if self._in_title:
            self._title += data
        else:
            self._parts.append(data)

    def get_result(self) -> tuple[str, str]:
        """返回 (title, body_text)。"""
        text = "".join(self._parts)
        # 清理多余空白
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        return self._title.strip(), text


def _html_to_text(html: str) -> tuple[str, str]:
    """从 HTML 提取标题和正文文本。"""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_result()


# ── 判断函数 ──

def _is_js_heavy(url: str) -> bool:
    return urlparse(url).netloc.lower() in _JS_HEAVY_DOMAINS


def _needs_stealth(url: str) -> bool:
    return urlparse(url).netloc.lower() in _STEALTH_DOMAINS


# ── Playwright 抓取 ──

def _fetch_with_playwright(url: str, timeout_ms: int) -> str:
    """Playwright 抓取，返回格式化文本。失败抛异常。"""
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

    js_heavy = _is_js_heavy(url)
    use_stealth = _needs_stealth(url)

    proxy = {"server": cfg.PROXY_URL} if cfg.PROXY_URL else None

    with sync_playwright() as p:
        launch_args = _STEALTH_ARGS if use_stealth else []
        browser = p.chromium.launch(headless=True, args=launch_args)
        try:
            context = browser.new_context(proxy=proxy)
            page = context.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )

            if js_heavy:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            else:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_selector("body", timeout=5000)

            title = page.title() or ""
            body_text = page.evaluate("() => document.body.innerText")

            if len(body_text.strip()) < _MIN_CONTENT_LENGTH and not js_heavy:
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                    body_text = page.evaluate("() => document.body.innerText")
                except PlaywrightTimeout:
                    pass
        finally:
            browser.close()

    if not body_text or not body_text.strip():
        raise WebFetchError(f"页面内容为空: {url}")

    body_text = re.sub(r"\n{3,}", "\n\n", body_text.strip())
    parts = []
    if title.strip():
        parts.append(f"# {title.strip()}")
    parts.append(body_text)
    return "\n\n".join(parts)


# ── curl 降级 ──

def _fetch_with_curl(url: str, timeout_s: int = 15) -> str:
    """curl 降级抓取：获取 HTML → 解析纯文本。"""
    proxy_args = ["--proxy", cfg.PROXY_URL] if cfg.PROXY_URL else []
    try:
        result = subprocess.run(
            [
                "curl", "-sL",
                "--max-time", str(timeout_s),
                "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "-H", "Accept: text/html,application/xhtml+xml",
                "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
                *proxy_args,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s + 5,
        )
    except subprocess.TimeoutExpired:
        raise WebFetchError(f"curl 超时: {url}")
    except FileNotFoundError:
        raise WebFetchError("curl 未安装，无法降级抓取")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise WebFetchError(f"curl 失败 (exit {result.returncode}): {stderr[:200]}")

    html = result.stdout
    if not html or len(html.strip()) < 50:
        raise WebFetchError(f"curl 返回内容过少: {url}")

    title, body_text = _html_to_text(html)

    if not body_text or len(body_text.strip()) < 20:
        raise WebFetchError(f"页面无可提取内容: {url}")

    parts = []
    if title:
        parts.append(f"# {title}")
    parts.append(body_text)
    return "\n\n".join(parts)


# ── 入口：Playwright 优先，curl 降级 ──

def fetch_web_content(url: str, timeout_ms: int = 30_000) -> str:
    """抓取网页内容，返回标题 + 正文纯文本。

    策略：Playwright 优先（支持 JS 渲染 + 反检测），失败自动降级 curl。

    Args:
        url: 完整的 http(s) 链接
        timeout_ms: Playwright 页面加载超时（毫秒）

    Returns:
        格式："# 标题\\n\\n正文文本"

    Raises:
        WebFetchError: 两种方式均失败
    """
    logger.info("抓取网页: %s", url)

    # ── 尝试 Playwright ──
    try:
        result = _fetch_with_playwright(url, timeout_ms)
        logger.info("Playwright 抓取成功 (%d 字符)", len(result))
        return result
    except Exception as playwright_err:
        pw_msg = str(playwright_err)[:100]
        logger.warning("Playwright 失败: %s，降级 curl", pw_msg)

    # ── 降级 curl ──
    try:
        result = _fetch_with_curl(url, timeout_s=15)
        logger.info("curl 抓取成功 (%d 字符)", len(result))
        return result
    except Exception as curl_err:
        raise WebFetchError(
            f"抓取失败，已尝试 Playwright 和 curl：\n"
            f"  Playwright: {pw_msg}\n"
            f"  curl: {curl_err}"
        )
