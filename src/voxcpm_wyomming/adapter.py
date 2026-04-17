"""Adapter layer between this service and nanovllm-voxcpm."""

from __future__ import annotations

import asyncio
import inspect
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import Any

import numpy as np
import numpy.typing as npt

from .audio import as_float32_array
from .config import ServiceConfig

WaveChunk = npt.NDArray[np.float32]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value

    return value


class VoxCPMAdapter(ABC):
    """Abstract interface for waveform generation backends."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize and warm up the backend."""

    @abstractmethod
    async def stop(self) -> None:
        """Release backend resources."""

    @abstractmethod
    async def sample_rate(self) -> int:
        """Return output sample rate in Hz."""

    @abstractmethod
    def generate(self, text: str) -> AsyncIterator[WaveChunk]:
        """Generate waveform chunks for the given text."""


class NanovllmVoxCPMAdapter(VoxCPMAdapter):
    """VoxCPM adapter backed by the `nano-vllm-voxcpm` package."""

    def __init__(
        self,
        config: ServiceConfig,
        server_factory: Callable[[ServiceConfig], Any] | None = None,
    ) -> None:
        self._config = config
        self._server_factory = server_factory
        self._server: Any | None = None
        self._sample_rate: int | None = None

    def _create_server(self) -> Any:
        if self._server_factory is not None:
            return self._server_factory(self._config)

        try:
            from nanovllm_voxcpm import VoxCPM
        except ImportError as err:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "nanovllm_voxcpm is not installed. Install with "
                "`pip install voxcpm-wyomming[voxcpm]`."
            ) from err

        return VoxCPM.from_pretrained(
            model=self._config.model,
            devices=list(self._config.devices),
            inference_timesteps=self._config.inference_timesteps,
            max_num_batched_tokens=self._config.max_num_batched_tokens,
            max_num_seqs=self._config.max_num_seqs,
            gpu_memory_utilization=self._config.gpu_memory_utilization,
            enforce_eager=self._config.enforce_eager,
        )

    async def start(self) -> None:
        self._server = self._create_server()

        wait_for_ready = getattr(self._server, "wait_for_ready", None)
        if callable(wait_for_ready):
            await _maybe_await(wait_for_ready())

        self._sample_rate = await self._detect_sample_rate()

    async def stop(self) -> None:
        if self._server is None:
            return

        stop_fn = getattr(self._server, "stop", None)
        if callable(stop_fn):
            await _maybe_await(stop_fn())

        self._server = None

    async def sample_rate(self) -> int:
        if self._sample_rate is not None:
            return self._sample_rate

        self._sample_rate = await self._detect_sample_rate()
        return self._sample_rate

    async def _detect_sample_rate(self) -> int:
        if self._config.sample_rate_override is not None:
            return self._config.sample_rate_override

        if self._server is None:
            raise RuntimeError("VoxCPM server has not been started")

        model_info_fn = getattr(self._server, "get_model_info", None)
        if callable(model_info_fn):
            model_info = await _maybe_await(model_info_fn())
            if isinstance(model_info, dict):
                for key in ("sample_rate", "output_sample_rate"):
                    value = model_info.get(key)
                    if value is not None:
                        try:
                            return int(value)
                        except (TypeError, ValueError):
                            pass

        return 16000

    async def _async_generate(self, text: str) -> AsyncIterator[WaveChunk]:
        if self._server is None:
            raise RuntimeError("VoxCPM server has not been started")

        stream = self._server.generate(target_text=text)

        if hasattr(stream, "__aiter__"):
            async for chunk in stream:
                yield as_float32_array(chunk).reshape(-1)
            return

        for chunk in stream:
            yield as_float32_array(chunk).reshape(-1)
            await asyncio.sleep(0)

    def generate(self, text: str) -> AsyncIterator[WaveChunk]:
        return self._async_generate(text)
