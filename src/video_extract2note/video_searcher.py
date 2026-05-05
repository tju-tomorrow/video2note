"""视频搜索模块：Playwright 搜索抖音/B站视频，curl 降级。

搜索策略：
1. DuckDuckGo HTML 版搜索 site:douyin.com OR site:bilibili.com {query}
2. Playwright 渲染 → 解析结果 → 按平台分类
3. Playwright 失败 → curl + 正则解析 HTML
"""

import logging
import re
import subprocess
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


class SearchError(RuntimeError):
    pass


def _platform_from_url(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    if "bilibili" in domain or "b23" in domain:
        return "bilibili"
    if "douyin" in domain or "iesdouyin" in domain:
        return "douyin"
    return "unknown"


def _normalize_search_results(raw_urls: list[dict]) -> list[dict]:
    """去重、过滤非视频链接、补充平台信息。"""
    seen = set()
    results = []
    for r in raw_urls:
        url = r["url"]
        if url in seen:
            continue
        seen.add(url)
        r["platform"] = _platform_from_url(url)
        if not r.get("title"):
            r["title"] = url[:60]
        if not r.get("snippet"):
            r["snippet"] = ""
        results.append(r)
    return results


# ── Playwright 搜索 ──

def _search_with_playwright(query: str, max_results: int) -> list[dict]:
    from playwright.sync_api import sync_playwright

    search_url = f"https://html.duckduckgo.com/html/?q=site%3Adouyin.com+OR+site%3Abilibili.com+{query}"
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(search_url, wait_until="domcontentloaded", timeout=15000)

            links = page.query_selector_all(".result__a")
            snippets = page.query_selector_all(".result__snippet")

            for i, link_el in enumerate(links):
                if len(results) >= max_results:
                    break
                href = link_el.get_attribute("href")
                title = link_el.inner_text().strip()
                if not href:
                    continue
                # DDG HTML 版的链接是 /l/?uddg=... 格式，需要解析
                actual_url = _resolve_ddg_url(href)
                if not actual_url:
                    continue

                snippet = ""
                if i < len(snippets):
                    snippet = snippets[i].inner_text().strip()

                plat = _platform_from_url(actual_url)
                if plat == "unknown":
                    continue

                results.append({
                    "title": title,
                    "url": actual_url,
                    "platform": plat,
                    "snippet": snippet[:200],
                })
        finally:
            browser.close()

    return results


def _resolve_ddg_url(href: str) -> str | None:
    """解析 DuckDuckGo 的 /l/?uddg=... 跳转链接。"""
    if href.startswith("http"):
        return href
    if "uddg=" in href:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg", [""])[0]
        if uddg and uddg.startswith("http"):
            return uddg
    return None


# ── curl 降级 ──

def _search_with_curl(query: str, max_results: int) -> list[dict]:
    from urllib.parse import quote

    search_url = f"https://html.duckduckgo.com/html/?q=site%3Adouyin.com+OR+site%3Abilibili.com+{quote(query)}"
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "15",
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
             search_url],
            capture_output=True, text=True, timeout=20,
        )
    except subprocess.TimeoutExpired:
        raise SearchError("搜索超时")
    except FileNotFoundError:
        raise SearchError("curl 未安装")

    if result.returncode != 0:
        raise SearchError(f"搜索请求失败: {result.stderr[:200]}")

    html = result.stdout
    if not html or len(html) < 200:
        raise SearchError("搜索返回内容为空")

    # 解析 DDG HTML 版结果
    return _parse_ddg_html(html, max_results)


def _parse_ddg_html(html: str, max_results: int) -> list[dict]:
    results = []
    # 匹配 result__a 链接
    link_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<[^>]*class="result__snippet"[^>]*>(.*?)</[^>]*>',
        re.DOTALL,
    )

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (href, title_raw) in enumerate(links):
        if len(results) >= max_results:
            break

        actual_url = _resolve_ddg_url(href)
        if not actual_url:
            continue

        plat = _platform_from_url(actual_url)
        if plat == "unknown":
            continue

        title = re.sub(r"<[^>]+>", "", title_raw).strip()
        if not title:
            title = actual_url[:60]

        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()[:200]

        results.append({
            "title": title,
            "url": actual_url,
            "platform": plat,
            "snippet": snippet,
        })

    return results


# ── 入口 ──

def search_videos(query: str, max_results: int = 15) -> list[dict]:
    """搜索抖音/B站视频。

    Args:
        query: 搜索关键词
        max_results: 返回结果数量上限

    Returns:
        [{title, url, platform, snippet}]

    Raises:
        SearchError: 搜索失败
    """
    if not query or not query.strip():
        raise SearchError("搜索关键词不能为空")

    query = query.strip()
    logger.info("视频搜索: %s", query)

    # Playwright 优先
    try:
        results = _search_with_playwright(query, max_results)
        if results:
            results = _normalize_search_results(results)
            logger.info("Playwright 搜索: %d 条结果", len(results))
            return results[:max_results]
        logger.info("Playwright 搜索无结果，降级 curl")
    except Exception as exc:
        logger.warning("Playwright 搜索失败: %s，降级 curl", exc)

    # curl 降级
    results = _search_with_curl(query, max_results)
    results = _normalize_search_results(results)
    logger.info("curl 搜索: %d 条结果", len(results))
    return results[:max_results]
