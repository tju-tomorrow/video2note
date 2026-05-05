import json
from pathlib import Path

from video_extract2note import desktop_bridge


def test_run_link_returns_cleaned_text(
    capsys, monkeypatch, tmp_path
):
    def fake_run_pipeline(url: str, output_dir: Path) -> str:
        assert url == "https://v.douyin.com/abc123/"
        return "流转写结果"

    monkeypatch.setattr(desktop_bridge, "run_pipeline", fake_run_pipeline)

    assert desktop_bridge.run_link("分享 https://v.douyin.com/abc123/") == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["text"] == "流转写结果"
    assert payload["error"] is None
    assert "正在并行下载" in payload["logs"][0]
