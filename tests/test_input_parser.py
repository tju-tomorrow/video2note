from video_extract2note.input_parser import extract_first_url


def test_extracts_bare_https_url():
    assert extract_first_url("https://v.douyin.com/abc123/") == "https://v.douyin.com/abc123/"


def test_extracts_first_url_from_share_text():
    text = "复制这条消息，打开抖音看看 https://v.douyin.com/iRxyZ12/ 更多内容"
    assert extract_first_url(text) == "https://v.douyin.com/iRxyZ12/"


def test_extracts_http_url():
    assert extract_first_url("链接 http://example.com/video") == "http://example.com/video"


def test_strips_common_trailing_punctuation():
    assert extract_first_url("看这个：https://v.douyin.com/abc123/，") == "https://v.douyin.com/abc123/"


def test_returns_none_when_no_url_exists():
    assert extract_first_url("没有链接的分享文本") is None


def test_normalizes_douyin_self_modal_url_to_video_url():
    text = (
        "https://www.douyin.com/user/self?from_tab_name=main"
        "&modal_id=7632608679321722266&showTab=like"
    )

    assert extract_first_url(text) == "https://www.douyin.com/video/7632608679321722266"
