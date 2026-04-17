from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np
import pytest

from tests.helpers import build_test_config
from voxcpm_wyomming.adapter import NanovllmVoxCPMAdapter


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
