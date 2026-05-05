import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import video_extract2note.config as cfg

logger = logging.getLogger(__name__)

FORMATTER_SYSTEM_PROMPT = cfg.FORMATTER_SYSTEM_PROMPT
MAX_CHUNK_CHARS = cfg.FORMATTER_MAX_CHUNK_CHARS
DEEPSEEK_MAX_TOKENS = cfg.FORMATTER_MAX_TOKENS


class FormatterError(RuntimeError):
    pass


def _load_formatter_client() -> Any:
    try:
        from openai import OpenAI
    except ImportError:
        raise FormatterError("openai 未安装，请运行：pip install openai")
    mimo_key = os.environ.get("MIMO_API_KEY", "").strip()
    if mimo_key:
        return OpenAI(api_key=mimo_key, base_url=cfg.MIMO_BASE_URL)
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if deepseek_key:
        return OpenAI(api_key=deepseek_key, base_url=cfg.DEEPSEEK_BASE_URL)
    raise FormatterError("未设置 MIMO_API_KEY 或 DEEPSEEK_API_KEY 环境变量")


def _split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """按句子边界拆分，避免截断句意。"""
    sentences = re.split(r'(?<=[。！？\n])(?=[^。！？\n])', text)
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) > max_chars and current:
            chunks.append(current.strip())
            current = sent
        else:
            current += sent
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _format_one_chunk(client: Any, text: str, index: int = 0) -> str:
    output_limit = min(DEEPSEEK_MAX_TOKENS, max(4096, int(len(text) * 0.8)))
    model = cfg.MIMO_MODEL if "xiaomimimo" in str(client.base_url) else cfg.DEEPSEEK_MODEL
    logger.debug("格式化 chunk %d (%d 字符), model=%s", index, len(text), model)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": FORMATTER_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
        max_tokens=output_limit,
    )
    return response.choices[0].message.content.strip()


def format_transcript(text: str, client: Any = None) -> str:
    """将转写文本格式化为规范 Markdown 文档，自动拆分长文本并行处理。"""
    if client is None:
        client = _load_formatter_client()

    chunks = _split_into_chunks(text)
    logger.info("文本拆分为 %d 个 chunk，开始并行格式化", len(chunks))

    if len(chunks) == 1:
        return _format_one_chunk(client, chunks[0], index=0)

    with ThreadPoolExecutor(max_workers=min(len(chunks), 4)) as executor:
        futures = [
            executor.submit(_format_one_chunk, client, chunk, i)
            for i, chunk in enumerate(chunks)
        ]
        formatted = [f.result() for f in futures]

    return "\n\n".join(formatted)
