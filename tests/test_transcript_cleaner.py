import pytest

from video_extract2note.transcript_cleaner import (
    TranscriptCleaningError,
    clean_transcript,
)


def test_clean_transcript_converts_traditional_to_simplified():
    assert clean_transcript("週末一起看視頻") == "周末一起看视频"


def test_clean_transcript_removes_spaces_between_chinese_characters():
    assert clean_transcript("你 好   世界") == "你好世界"


def test_clean_transcript_collapses_repeated_punctuation():
    assert clean_transcript("你好。。。。今天，，很好！！") == "你好。今天，很好！"


def test_clean_transcript_keeps_space_between_english_words():
    assert clean_transcript("hello   world  週末") == "hello world 周末"


def test_clean_transcript_reports_missing_opencc(monkeypatch):
    import video_extract2note.transcript_cleaner as cleaner

    monkeypatch.setattr(cleaner, "OpenCC", None)

    with pytest.raises(TranscriptCleaningError, match="OpenCC 未安装"):
        clean_transcript("週末")
