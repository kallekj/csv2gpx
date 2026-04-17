from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Iterable

import numpy as np
import pytest
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event, async_read_event
from wyoming.info import Info
from wyoming.info import Describe
from wyoming.tts import Synthesize, SynthesizeStart

from tests.helpers import build_test_config
from voxcpm_wyomming.adapter import VoxCPMAdapter
from voxcpm_wyomming.audio import bytes_to_pcm_int16
from voxcpm_wyomming.service import VoxCPMWyomingEventHandler, build_info


class FakeStreamWriter:
    def __init__(self) -> None:
        self._undrained_data = bytes()
        self._value = bytes()

    def write(self, data: bytes) -> None:
        self._undrained_data += data

    def writelines(self, data: Iterable[bytes]) -> None:
        for line in data:
            self.write(line)

    async def drain(self) -> None:
        self._value += self._undrained_data
        self._undrained_data = bytes()

    def getvalue(self) -> bytes:
        return self._value


class FakeAdapter(VoxCPMAdapter):
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def sample_rate(self) -> int:
        return 16000

    def generate(self, text: str) -> AsyncIterator[np.ndarray]:
        assert text

        async def _gen() -> AsyncIterator[np.ndarray]:
            yield np.array([0.0, 0.5, -0.5], dtype=np.float32)

        return _gen()


async def _decode_events(raw: bytes) -> list[Event]:
    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    reader.feed_eof()

    events: list[Event] = []
    while True:
        event = await async_read_event(reader)
        if event is None:
            break
        events.append(event)

    return events


@pytest.mark.asyncio
async def test_handler_responds_with_info() -> None:
    config = build_test_config()
    info = build_info(config, sample_rate=16000)

    writer = FakeStreamWriter()
    handler = VoxCPMWyomingEventHandler(
        asyncio.StreamReader(),
        writer,  # type: ignore[arg-type]
        adapter=FakeAdapter(),
        info=info,
        voice_name=config.voice_name,
        voice_language=config.voice_language,
        voice_speaker=config.voice_speaker,
    )

    assert await handler.handle_event(Describe().event())
    events = await _decode_events(writer.getvalue())
    assert len(events) == 1
    assert Info.is_type(events[0].type)


@pytest.mark.asyncio
async def test_handler_synthesize_emits_audio_events() -> None:
    config = build_test_config()
    info = build_info(config, sample_rate=16000)

    writer = FakeStreamWriter()
    handler = VoxCPMWyomingEventHandler(
        asyncio.StreamReader(),
        writer,  # type: ignore[arg-type]
        adapter=FakeAdapter(),
        info=info,
        voice_name=config.voice_name,
        voice_language=config.voice_language,
        voice_speaker=config.voice_speaker,
    )

    assert await handler.handle_event(Synthesize(text="hello").event())

    events = await _decode_events(writer.getvalue())
    assert [event.type for event in events] == ["audio-start", "audio-chunk", "audio-stop"]

    start_event = AudioStart.from_event(events[0])
    chunk_event = AudioChunk.from_event(events[1])
    stop_event = AudioStop.from_event(events[2])

    assert start_event.rate == 16000
    assert start_event.width == 2
    assert start_event.channels == 1

    samples = bytes_to_pcm_int16(chunk_event.audio)
    assert samples.tolist() == [0, 16383, -16383]

    assert stop_event.timestamp is None


@pytest.mark.asyncio
async def test_handler_rejects_streaming_messages() -> None:
    config = build_test_config()
    info = build_info(config, sample_rate=16000)

    writer = FakeStreamWriter()
    handler = VoxCPMWyomingEventHandler(
        asyncio.StreamReader(),
        writer,  # type: ignore[arg-type]
        adapter=FakeAdapter(),
        info=info,
        voice_name=config.voice_name,
        voice_language=config.voice_language,
        voice_speaker=config.voice_speaker,
    )

    assert await handler.handle_event(SynthesizeStart().event())

    events = await _decode_events(writer.getvalue())
    assert len(events) == 1
    assert Error.is_type(events[0].type)
    error = Error.from_event(events[0])
    assert error.code == "streaming_not_supported"
