import re
from urllib.parse import parse_qs, urlparse

_URL_RE = re.compile(r"https?://[^\s]+")
_TRAILING_PUNCTUATION = "，。,.!！?？；;：:、)]}）】》\"'"

_BILIBILI_DOMAINS = {"www.bilibili.com", "bilibili.com", "m.bilibili.com", "b23.tv"}


def _is_bilibili_url(url: str) -> bool:
    return urlparse(url).netloc.lower().rstrip("/") in _BILIBILI_DOMAINS


def _normalize_bilibili_url(url: str) -> str:
    """规范化 B站链接：去参数、标准化 BV/av 号。b23.tv 短链由 yt-dlp 处理。"""
    parsed = urlparse(url)
    # b23.tv 短链保持原样，yt-dlp 会自动解析
    if parsed.netloc.lower() == "b23.tv":
        return url
    # 去掉 ?p=xxx 分P参数、spm_id_from=... 等追踪参数
    cleaned = parsed._replace(query="", fragment="")
    return cleaned.geturl()


def _normalize_douyin_url(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    douyin_domains = {"www.douyin.com", "douyin.com",
                      "www.iesdouyin.com", "iesdouyin.com",
                      "v.douyin.com"}

    if domain not in douyin_domains:
        return url

    # /share/video/{id}/... → /video/{id}
    m = re.search(r"/share/video/(\d+)", parsed.path)
    if m:
        return f"https://www.douyin.com/video/{m.group(1)}"

    # /user/self?modal_id=... → /video/{id}
    modal_ids = parse_qs(parsed.query).get("modal_id", [])
    if parsed.path == "/user/self" and modal_ids:
        return f"https://www.douyin.com/video/{modal_ids[0]}"

    return url


def extract_first_url(text: str) -> str | None:
    match = _URL_RE.search(text.strip())
    if match is None:
        return None
    url = match.group(0).rstrip(_TRAILING_PUNCTUATION)
    if _is_bilibili_url(url):
        return _normalize_bilibili_url(url)
    return _normalize_douyin_url(url)


def classify_url(url: str) -> str:
    """判断 URL 类型：'video'（抖音/B站）或 'web'（普通网页）。"""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().rstrip("/")

    douyin_domains = {
        "www.douyin.com", "douyin.com",
        "www.iesdouyin.com", "iesdouyin.com",
        "v.douyin.com",
    }

    if domain in _BILIBILI_DOMAINS or domain in douyin_domains:
        return "video"
    return "web"
