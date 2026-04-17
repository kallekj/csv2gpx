from voxcpm_wyomming.__main__ import main


def test_main_requires_model() -> None:
    assert main([]) == 2


def test_main_help_succeeds() -> None:
    assert main(["--help"]) == 0
