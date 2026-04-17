from __future__ import annotations

import asyncio
import builtins
from collections.abc import AsyncIterator

import numpy as np
import pytest

from tests.helpers import build_test_config
from voxcpm_wyomming.adapter import NanovllmVoxCPMAdapter, _maybe_await


class FakeAsyncServer:
    def __init__(self) -> None:
        self.waited = False
        self.stopped = False

    async def wait_for_ready(self) -> None:
        self.waited = True

    async def get_model_info(self) -> dict[str, int]:
        return {"sample_rate": 22050}

    async def stop(self) -> None:
        self.stopped = True

    def generate(self, target_text: str) -> AsyncIterator[np.ndarray]:
        assert target_text

        async def _gen() -> AsyncIterator[np.ndarray]:
            yield np.array([0.0, 0.5, -0.5], dtype=np.float32)

        return _gen()


class FakeSyncServer:
    def __init__(self) -> None:
        self.stopped = False

    async def get_model_info(self) -> dict[str, str]:
        return {"sample_rate": "bad", "output_sample_rate": "22050"}

    def generate(self, target_text: str) -> list[np.ndarray]:
        assert target_text
        return [np.array([0.25], dtype=np.float32)]

    async def stop(self) -> None:
        self.stopped = True


class FakeNoStopServer:
    stop = None

    def generate(self, target_text: str) -> list[np.ndarray]:
        assert target_text
        return []


@pytest.mark.asyncio
async def test_adapter_lifecycle_and_generate() -> None:
    fake_server = FakeAsyncServer()
    adapter = NanovllmVoxCPMAdapter(
        build_test_config(),
        server_factory=lambda _: fake_server,
    )

    await adapter.start()
    assert fake_server.waited
    assert await adapter.sample_rate() == 22050

    chunks = [chunk async for chunk in adapter.generate("hello")]
    assert len(chunks) == 1
    assert chunks[0].dtype == np.float32

    await adapter.stop()
    assert fake_server.stopped


@pytest.mark.asyncio
async def test_adapter_uses_sample_rate_override() -> None:
    fake_server = FakeAsyncServer()
    adapter = NanovllmVoxCPMAdapter(
        build_test_config(sample_rate_override=16000),
        server_factory=lambda _: fake_server,
    )

    await adapter.start()
    assert await adapter.sample_rate() == 16000


@pytest.mark.asyncio
async def test_maybe_await_handles_plain_and_awaitable_values() -> None:
    assert await _maybe_await(123) == 123
    assert await _maybe_await(asyncio.sleep(0, result=456)) == 456


def test_create_server_raises_runtime_error_without_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = NanovllmVoxCPMAdapter(build_test_config())
    original_import = builtins.__import__

    def fake_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "nanovllm_voxcpm":
            raise ImportError("missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="nanovllm_voxcpm is not installed"):
        adapter._create_server()


@pytest.mark.asyncio
async def test_adapter_handles_sync_generation_and_stop_variants() -> None:
    sync_server = FakeSyncServer()
    adapter = NanovllmVoxCPMAdapter(build_test_config(), server_factory=lambda _: sync_server)

    await adapter.start()
    assert await adapter.sample_rate() == 22050

    chunks = [chunk async for chunk in adapter.generate("sync")]
    assert len(chunks) == 1
    assert chunks[0].tolist() == [0.25]

    await adapter.stop()
    assert sync_server.stopped

    adapter_no_stop = NanovllmVoxCPMAdapter(
        build_test_config(),
        server_factory=lambda _: FakeNoStopServer(),
    )
    await adapter_no_stop.start()
    await adapter_no_stop.stop()

    adapter_none = NanovllmVoxCPMAdapter(
        build_test_config(), server_factory=lambda _: FakeNoStopServer()
    )
    await adapter_none.stop()


@pytest.mark.asyncio
async def test_adapter_raises_when_sampling_or_generating_before_start() -> None:
    adapter = NanovllmVoxCPMAdapter(
        build_test_config(), server_factory=lambda _: FakeNoStopServer()
    )

    with pytest.raises(RuntimeError, match="has not been started"):
        await adapter.sample_rate()

    with pytest.raises(RuntimeError, match="has not been started"):
        async for _chunk in adapter.generate("hello"):
            pass
