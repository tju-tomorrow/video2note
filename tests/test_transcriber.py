from types import SimpleNamespace

import pytest

from pathlib import Path

from video_extract2note.transcriber import (
    TranscriptionError,
    get_transcription_options,
    join_segments,
    load_model,
    transcribe_audio,
    transcribe_audio_detailed,
)


class FakeWhisperModel:
    received_args = None
    received_transcribe_kwargs = None

    def __init__(self, model_name, device, compute_type):
        FakeWhisperModel.received_args = {
            "model_name": model_name,
            "device": device,
            "compute_type": compute_type,
        }

    def transcribe(self, audio_path, **kwargs):
        assert audio_path.endswith("audio.mp3")
        FakeWhisperModel.received_transcribe_kwargs = kwargs
        segments = [
            SimpleNamespace(text="  第一段 "),
            SimpleNamespace(text=""),
            SimpleNamespace(text="第二段"),
        ]
        return segments, SimpleNamespace(language="zh")


class EmptyWhisperModel:
    def __init__(self, model_name, device, compute_type):
        pass

    def transcribe(self, audio_path, **kwargs):
        return [SimpleNamespace(text="   ")], SimpleNamespace(language="zh")


class RaisingWhisperModel:
    def __init__(self, model_name, device, compute_type):
        raise RuntimeError("model download failed")


def test_join_segments_trims_and_joins_non_empty_text():
    segments = [
        SimpleNamespace(text="  你好"),
        SimpleNamespace(text=""),
        SimpleNamespace(text="世界  "),
    ]

    assert join_segments(segments) == "你好 世界"


def test_transcribe_audio_uses_cpu_friendly_defaults(tmp_path):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake audio")

    text = transcribe_audio(audio_path, model_factory=FakeWhisperModel)

    assert text == "第一段第二段"
    assert FakeWhisperModel.received_args == {
        "model_name": "small",
        "device": "auto",
        "compute_type": "auto",
    }
    assert FakeWhisperModel.received_transcribe_kwargs == {
        "language": "zh",
        "vad_filter": True,
        "initial_prompt": "以下是简体中文短视频口播内容，请输出简体中文并保留自然标点。",
        "beam_size": 1,
    }


def test_transcribe_audio_detailed_returns_raw_and_cleaned_text(tmp_path):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake audio")

    result = transcribe_audio_detailed(audio_path, model_factory=TraditionalModel)

    assert result.raw_text == "週末 一起 看 視頻"
    assert result.cleaned_text == "周末一起看视频"
    assert result.language == "zh"
    assert result.model_name == "small"


def test_get_transcription_options_returns_named_profiles():
    assert get_transcription_options("fast").model_name == "base"
    assert get_transcription_options("standard").model_name == "small"
    assert get_transcription_options("quality").model_name == "medium"


def test_get_transcription_options_rejects_unknown_profile():
    with pytest.raises(TranscriptionError, match="未知转写质量配置"):
        get_transcription_options("slow")


def test_transcribe_audio_reports_empty_text(tmp_path):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake audio")

    with pytest.raises(TranscriptionError, match="未识别到可用语音内容"):
        transcribe_audio(audio_path, model_factory=EmptyWhisperModel)


def test_transcribe_audio_reports_model_errors(tmp_path):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake audio")

    with pytest.raises(TranscriptionError, match="转写失败"):
        transcribe_audio(audio_path, model_factory=RaisingWhisperModel)


def test_transcribe_audio_reports_missing_faster_whisper(tmp_path):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake audio")

    with pytest.raises(TranscriptionError, match="faster-whisper 未安装"):
        transcribe_audio(audio_path, model_factory=None)


class TraditionalModel:
    def __init__(self, model_name, device, compute_type):
        pass

    def transcribe(self, audio_path, **kwargs):
        return [SimpleNamespace(text="週末 一起 看 視頻")], SimpleNamespace(language="zh")


class PreloadedTestModel:
    calls = []

    def __init__(self, model_name, **kwargs):
        self.model_name = model_name

    def transcribe(self, audio_path, **kwargs):
        PreloadedTestModel.calls.append({
            "audio_path": audio_path,
            "kwargs": kwargs,
        })

        class FakeInfo:
            language = "zh"
            duration = 10.0

        class FakeSegment:
            text = "预加载模型转写结果"

        return iter([FakeSegment]), FakeInfo()


class PreloadedModelFactoryCallCounter:
    last_call = None

    def __call__(self, model_name, **kwargs):
        PreloadedModelFactoryCallCounter.last_call = {
            "model_name": model_name,
            "kwargs": kwargs,
        }
        return PreloadedTestModel(model_name, **kwargs)


def test_load_model_returns_whisper_model():
    PreloadedTestModel.calls = []
    PreloadedModelFactoryCallCounter.last_call = None

    model = load_model("small", model_factory=PreloadedModelFactoryCallCounter())

    assert isinstance(model, PreloadedTestModel)
    assert model.model_name == "small"
    assert PreloadedModelFactoryCallCounter.last_call is not None


def test_transcribe_audio_detailed_uses_preloaded_model():
    PreloadedTestModel.calls = []
    PreloadedModelFactoryCallCounter.last_call = None

    preloaded = load_model("base", model_factory=PreloadedModelFactoryCallCounter())

    # Reset counter after load_model to verify transcribe doesn't call factory again
    PreloadedModelFactoryCallCounter.last_call = None

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        audio_path = Path(f.name)

    try:
        result = transcribe_audio_detailed(
            audio_path,
            model=preloaded,
            model_factory=PreloadedModelFactoryCallCounter(),
        )

        assert result.cleaned_text == "预加载模型转写结果"
        # model_factory should NOT have been called again
        assert PreloadedModelFactoryCallCounter.last_call is None
        assert len(PreloadedTestModel.calls) == 1
    finally:
        audio_path.unlink()


def test_load_model_raises_when_faster_whisper_not_installed():
    with pytest.raises(TranscriptionError, match="faster-whisper 未安装"):
        load_model("small", model_factory=None)
