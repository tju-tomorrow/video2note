"""集中配置管理，所有硬编码值统一在此定义。"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_env() -> None:
    """加载项目根目录的 .env 文件（仅执行一次）。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)


# ── 路径 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WHISPER_CPP_MODEL_DIR = Path.home() / ".cache" / "whisper-cpp"
COOKIE_CACHE_DIR = Path.home() / ".cache" / "video-extract2note"
MCP_OUTPUT_BASE = Path.home() / "Documents" / "VideoExtract2Note"

# ── 转写引擎 ──
WHISPER_CPP_MODELS = {
    "tiny": "ggml-tiny.bin",
    "base": "ggml-base.bin",
    "small": "ggml-small.bin",
    "medium": "ggml-medium.bin",
}
DEFAULT_TRANSCRIPTION_MODEL = "small"
DEFAULT_INITIAL_PROMPT = "以下是简体中文短视频口播内容，请输出简体中文并保留自然标点。"
LONG_AUDIO_THRESHOLD_SECONDS = 300
MAX_PARALLEL_WORKERS = 8

# ── 格式化 ──
FORMATTER_MAX_CHUNK_CHARS = 4000
FORMATTER_MAX_TOKENS = 8192
FORMATTER_SYSTEM_PROMPT = """你是文字编辑助手。你的唯一任务是将语音转文字结果整理成规范的 Markdown 文档。

严格要求：
1. 修正明显的错别字和同音字错误（根据上下文判断正确用字）
2. 补全缺失的标点符号（句号、逗号、问号等）
3. 按内容逻辑分段，每段之间空一行
4. 如果内容有明显主题转换，添加 ## 二级标题
5. 可以用 - 列表整理要点
6. 绝对不允许：添加原文没有的观点、评价、总结、补充解释
7. 绝对不允许：改写句式使其"更优美"，保持口语原汁原味
8. 只输出格式化后的 Markdown，不要任何前言后语"""

# ── 下载 ──
DOUYIN_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
COOKIE_REFRESH_AFTER_SECONDS = 7200   # 2h 后标记 stale，但仍尝试使用
COOKIE_MAX_USABLE_SECONDS = 86400     # 24h 后彻底丢弃
PARALLEL_DOWNLOAD_CHUNKS = 4
PARALLEL_DOWNLOAD_MIN_SIZE = 5 * 1024 * 1024  # 5 MB

# ── 代理（可选，从环境变量读取）──
HTTP_PROXY = os.environ.get("HTTP_PROXY", "").strip() or None
HTTPS_PROXY = os.environ.get("HTTPS_PROXY", "").strip() or None
PROXY_URL = HTTPS_PROXY or HTTP_PROXY  # 统一代理地址

# ── 网页抓取 ──
JS_HEAVY_DOMAINS = {
    "juejin.cn", "www.juejin.cn",
    "zhuanlan.zhihu.com", "www.zhihu.com",
    "mp.weixin.qq.com",
    "twitter.com", "x.com",
    "www.reddit.com", "old.reddit.com",
}
STEALTH_DOMAINS = {
    "juejin.cn", "www.juejin.cn",
    "zhuanlan.zhihu.com", "www.zhihu.com",
    "mp.weixin.qq.com",
    "blog.csdn.net", "www.csdn.net",
}
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-web-security",
]
MIN_WEB_CONTENT_LENGTH = 200

# ── 数据库 ──
DB_PATH = COOKIE_CACHE_DIR / "data.db"

# ── API ──
MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# ── B站 ──
BILIBILI_DOMAINS = {"www.bilibili.com", "bilibili.com", "m.bilibili.com", "b23.tv"}

# 启动时加载 .env
_load_env()
