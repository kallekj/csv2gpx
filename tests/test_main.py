from __future__ import annotations

import asyncio

import pytest

from tests.helpers import build_test_config
from voxcpm_wyomming import __main__ as entry


class _Parser:
    prog = "voxcpm"

    def parse_args(self, _argv: list[str] | None = None) -> object:
        return object()

    def print_usage(self, _stream: object) -> None:
        return None


class _FakeEvent:
    def set(self) -> None:
        return None

    async def wait(self) -> None:
        return None


class _FakeLoop:
    def __init__(self) -> None:
        self.handlers: list[int] = []

    def add_signal_handler(self, sig: int, _callback: object) -> None:
        self.handlers.append(sig)


class _FakeService:
    last_instance: _FakeService | None = None

    def __init__(self, _config: object, adapter_factory: object) -> None:
        _ = adapter_factory
        self.started = False
        self.stopped = False
        _FakeService.last_instance = self

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_run_service_starts_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = _FakeLoop()
    cfg = build_test_config(model="test-model")

    monkeypatch.setattr(entry, "build_arg_parser", lambda: _Parser())
    monkeypatch.setattr(entry, "config_from_args", lambda _args: cfg)
    monkeypatch.setattr(entry, "VoxCPMWyomingService", _FakeService)
    monkeypatch.setattr("voxcpm_wyomming.__main__.asyncio.Event", _FakeEvent)
    monkeypatch.setattr("voxcpm_wyomming.__main__.asyncio.get_running_loop", lambda: loop)

    await entry._run_service(["--model", "test-model"])

    instance = _FakeService.last_instance
    assert instance is not None
    assert instance.started
    assert instance.stopped
    assert len(loop.handlers) == 2


def _run_raising(coro: object, err: BaseException) -> None:
    if asyncio.iscoroutine(coro):
        coro.close()
    raise err


def test_main_returns_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(coro: object) -> None:
        if asyncio.iscoroutine(coro):
            coro.close()

    monkeypatch.setattr("voxcpm_wyomming.__main__.asyncio.run", fake_run)
    assert entry.main(["--model", "m"]) == 0


def test_main_handles_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "voxcpm_wyomming.__main__.asyncio.run",
        lambda coro: _run_raising(coro, KeyboardInterrupt()),
    )
    assert entry.main(["--model", "m"]) == 0


def test_main_handles_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "voxcpm_wyomming.__main__.asyncio.run",
        lambda coro: _run_raising(coro, RuntimeError("boom")),
    )
    assert entry.main(["--model", "m"]) == 1


def test_main_handles_system_exit_without_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "voxcpm_wyomming.__main__.asyncio.run",
        lambda coro: _run_raising(coro, SystemExit()),
    )
    assert entry.main(["--model", "m"]) == 1
