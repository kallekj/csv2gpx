from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import cast

import numpy as np
import pytest
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event, async_read_event
from wyoming.info import Describe, Info
from wyoming.tts import Synthesize, SynthesizeStart, SynthesizeVoice

from tests.helpers import build_test_config
from voxcpm_wyomming.adapter import VoxCPMAdapter
from voxcpm_wyomming.audio import bytes_to_pcm_int16
from voxcpm_wyomming.service import VoxCPMWyomingEventHandler, VoxCPMWyomingService, build_info


class FakeStreamWriter:
    def __init__(self) -> None:
        self._undrained_data = b""
        self._value = b""

    def write(self, data: bytes) -> None:
        self._undrained_data += data

    def writelines(self, data: Iterable[bytes]) -> None:
        for line in data:
            self.write(line)

    async def drain(self) -> None:
        self._value += self._undrained_data
        self._undrained_data = b""

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


class EmptyAdapter(FakeAdapter):
    def generate(self, text: str) -> AsyncIterator[np.ndarray]:
        assert text

        async def _gen() -> AsyncIterator[np.ndarray]:
            yield np.array([], dtype=np.float32)

        return _gen()


class BrokenSampleRateAdapter(FakeAdapter):
    async def sample_rate(self) -> int:
        raise RuntimeError("sample-rate-failure")


class BrokenGenerateAdapter(FakeAdapter):
    def generate(self, text: str) -> AsyncIterator[np.ndarray]:
        assert text

        class _BrokenIterator:
            def __aiter__(self) -> _BrokenIterator:
                return self

            async def __anext__(self) -> np.ndarray:
                raise RuntimeError("generate-failure")

        return _BrokenIterator()


class LifecycleAdapter(FakeAdapter):
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class FakeWyomingServer:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self, _handler_factory: object) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


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


@pytest.mark.asyncio
async def test_handler_rejects_empty_text() -> None:
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

    assert await handler.handle_event(Synthesize(text="  ").event())
    events = await _decode_events(writer.getvalue())
    assert len(events) == 1
    assert Error.from_event(events[0]).code == "invalid_request"


@pytest.mark.asyncio
async def test_handler_rejects_unsupported_voice() -> None:
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

    voice = SynthesizeVoice(name="other")
    assert await handler.handle_event(Synthesize(text="hello", voice=voice).event())
    events = await _decode_events(writer.getvalue())
    assert len(events) == 1
    assert Error.from_event(events[0]).code == "voice_not_supported"


@pytest.mark.asyncio
async def test_handler_handles_generation_error_after_audio_start() -> None:
    config = build_test_config()
    info = build_info(config, sample_rate=16000)

    writer = FakeStreamWriter()
    handler = VoxCPMWyomingEventHandler(
        asyncio.StreamReader(),
        writer,  # type: ignore[arg-type]
        adapter=BrokenGenerateAdapter(),
        info=info,
        voice_name=config.voice_name,
        voice_language=config.voice_language,
        voice_speaker=config.voice_speaker,
    )

    assert await handler.handle_event(Synthesize(text="hello").event())
    events = await _decode_events(writer.getvalue())
    assert [event.type for event in events] == ["audio-start", "audio-stop", "error"]


@pytest.mark.asyncio
async def test_handler_handles_sample_rate_error_before_audio_start() -> None:
    config = build_test_config()
    info = build_info(config, sample_rate=16000)

    writer = FakeStreamWriter()
    handler = VoxCPMWyomingEventHandler(
        asyncio.StreamReader(),
        writer,  # type: ignore[arg-type]
        adapter=BrokenSampleRateAdapter(),
        info=info,
        voice_name=config.voice_name,
        voice_language=config.voice_language,
        voice_speaker=config.voice_speaker,
    )

    assert await handler.handle_event(Synthesize(text="hello").event())
    events = await _decode_events(writer.getvalue())
    assert [event.type for event in events] == ["error"]


@pytest.mark.asyncio
async def test_handler_ignores_empty_pcm_chunk() -> None:
    config = build_test_config()
    info = build_info(config, sample_rate=16000)

    writer = FakeStreamWriter()
    handler = VoxCPMWyomingEventHandler(
        asyncio.StreamReader(),
        writer,  # type: ignore[arg-type]
        adapter=EmptyAdapter(),
        info=info,
        voice_name=config.voice_name,
        voice_language=config.voice_language,
        voice_speaker=config.voice_speaker,
    )

    assert await handler.handle_event(Synthesize(text="hello").event())
    events = await _decode_events(writer.getvalue())
    assert [event.type for event in events] == ["audio-start", "audio-stop"]


@pytest.mark.asyncio
async def test_handler_returns_true_for_unknown_event() -> None:
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

    assert await handler.handle_event(Event(type="unknown"))
    assert writer.getvalue() == b""


def test_build_info_includes_speaker_when_configured() -> None:
    config = build_test_config(voice_speaker="speaker-1")
    info = build_info(config, sample_rate=22050)
    speaker = info.tts[0].voices[0].speakers
    assert speaker is not None
    assert speaker[0].name == "speaker-1"


@pytest.mark.asyncio
async def test_service_lifecycle_start_stop_and_handler_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = build_test_config()
    adapter = LifecycleAdapter()
    server = FakeWyomingServer()

    monkeypatch.setattr("voxcpm_wyomming.service.AsyncServer.from_uri", lambda _uri: server)

    service = VoxCPMWyomingService(config, adapter_factory=lambda _cfg: adapter)
    await service.start()
    assert adapter.started
    assert server.started

    handler = service._handler_factory(
        asyncio.StreamReader(),
        cast(asyncio.StreamWriter, FakeStreamWriter()),
    )
    assert isinstance(handler, VoxCPMWyomingEventHandler)

    await service.stop()
    assert server.stopped
    assert adapter.stopped


@pytest.mark.asyncio
async def test_service_handler_factory_raises_before_start() -> None:
    config = build_test_config()
    service = VoxCPMWyomingService(config, adapter_factory=lambda _cfg: LifecycleAdapter())

    with pytest.raises(RuntimeError, match="not been initialized"):
        service._handler_factory(
            asyncio.StreamReader(),
            cast(asyncio.StreamWriter, FakeStreamWriter()),
        )


@pytest.mark.asyncio
async def test_service_stop_without_started_server_still_stops_adapter() -> None:
    config = build_test_config()
    adapter = LifecycleAdapter()
    service = VoxCPMWyomingService(config, adapter_factory=lambda _cfg: adapter)

    await service.stop()
    assert adapter.stopped
