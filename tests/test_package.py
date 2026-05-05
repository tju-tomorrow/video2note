from video_extract2note import __version__
from video_extract2note.cli import main


def test_package_exposes_version():
    assert __version__ == "0.1.0"


def test_cli_main_is_callable():
    assert callable(main)
