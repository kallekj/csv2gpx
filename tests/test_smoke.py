import pytest

from csv2gpx import __version__
from csv2gpx.__main__ import main


def test_version_is_defined() -> None:
    assert __version__ == "0.1.0"


def test_main_help_succeeds() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
