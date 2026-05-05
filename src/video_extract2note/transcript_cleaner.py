import re
from typing import Any

try:
    from opencc import OpenCC
except ImportError:
    OpenCC = None  # type: ignore[assignment]


class TranscriptCleaningError(RuntimeError):
    pass


_CHINESE_CHAR = r"\u3400-\u4dbf\u4e00-\u9fff"
_SPACE_BETWEEN_CHINESE_RE = re.compile(
    rf"(?<=[{_CHINESE_CHAR}])\s+(?=[{_CHINESE_CHAR}])"
)
_MULTISPACE_RE = re.compile(r"[ \t\r\f\v]+")
_REPEATED_PUNCTUATION = (
    ("。", re.compile(r"。{2,}")),
    ("，", re.compile(r"，{2,}")),
    ("！", re.compile(r"！{2,}")),
    ("？", re.compile(r"？{2,}")),
)


def _opencc() -> Any:
    if OpenCC is None:
        raise TranscriptCleaningError(
            "OpenCC 未安装，请先运行：python -m pip install opencc-python-reimplemented"
        )
    return OpenCC("t2s")


def clean_transcript(text: str) -> str:
    converted = _opencc().convert(text)
    converted = converted.strip()
    converted = converted.replace(",", "，").replace("!", "！").replace("?", "？")
    converted = _MULTISPACE_RE.sub(" ", converted)
    converted = _SPACE_BETWEEN_CHINESE_RE.sub("", converted)
    for replacement, pattern in _REPEATED_PUNCTUATION:
        converted = pattern.sub(replacement, converted)
    return converted.strip()
