"""Wyoming TCP service implementation for VoxCPM TTS."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from wyoming.audio import AudioChunk, AudioFormat, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event
from wyoming.info import Attribution, Info, SndProgram, TtsProgram, TtsVoice, TtsVoiceSpeaker
from wyoming.info import Describe
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize, SynthesizeChunk, SynthesizeStart, SynthesizeStop, SynthesizeVoice

from .adapter import VoxCPMAdapter
from .audio import pcm_float32_to_int16_bytes
from .config import ServiceConfig

_PCM_WIDTH_BYTES = 2
_PCM_CHANNELS = 1


def build_info(config: ServiceConfig, sample_rate: int) -> Info:
    """Build Wyoming `info` response describing this TTS service."""
    attribution = Attribution(name=config.attribution_name, url=config.attribution_url)

    speakers: list[TtsVoiceSpeaker] | None = None
    if config.voice_speaker:
        speakers = [TtsVoiceSpeaker(name=config.voice_speaker)]

    voice = TtsVoice(
        name=config.voice_name,
        languages=[config.voice_language],
        speakers=speakers,
        attribution=attribution,
        installed=True,
        description=config.voice_description,
        version=config.voice_version,
    )

    tts_program = TtsProgram(
        name=config.service_name,
        voices=[voice],
        supports_synthesize_streaming=False,
        attribution=attribution,
        installed=True,
        description=config.service_description,
        version=config.service_version,
    )

    snd_program = SndProgram(
        name=f"{config.service_name}-output",
        snd_format=AudioFormat(rate=sample_rate, width=_PCM_WIDTH_BYTES, channels=_PCM_CHANNELS),
        attribution=attribution,
        installed=True,
        description="PCM audio emitted by VoxCPM synthesis",
        version=config.service_version,
    )

    return Info(tts=[tts_program], snd=[snd_program])


class VoxCPMWyomingEventHandler(AsyncEventHandler):
    """Handle Wyoming events for a single client connection."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        adapter: VoxCPMAdapter,
        info: Info,
        voice_name: str,
        voice_language: str,
        voice_speaker: str | None,
    ) -> None:
        super().__init__(reader, writer)
        self._adapter = adapter
        self._info = info
        self._voice_name = voice_name
        self._voice_language = voice_language
        self._voice_speaker = voice_speaker

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self._info.event())
            return True

        if Synthesize.is_type(event.type):
            synth = Synthesize.from_event(event)
            await self._handle_synthesize(synth)
            return True

        if (
            SynthesizeStart.is_type(event.type)
            or SynthesizeChunk.is_type(event.type)
            or SynthesizeStop.is_type(event.type)
        ):
            await self.write_event(
                Error(
                    text=(
                        "Streaming synthesis is not supported by this service build. "
                        "Use `synthesize` requests."
                    ),
                    code="streaming_not_supported",
                ).event()
            )
            return True

        return True

    def _voice_is_supported(self, voice: SynthesizeVoice | None) -> bool:
        if voice is None:
            return True

        if voice.name and voice.name != self._voice_name:
            return False

        if voice.language and voice.language != self._voice_language:
            return False

        if voice.speaker:
            if self._voice_speaker is None:
                return False
            if voice.speaker != self._voice_speaker:
                return False

        return True

    async def _handle_synthesize(self, synth: Synthesize) -> None:
        if not synth.text.strip():
            await self.write_event(Error(text="Text is required", code="invalid_request").event())
            return

        if not self._voice_is_supported(synth.voice):
            await self.write_event(
                Error(
                    text="Requested voice is not available in this service instance",
                    code="voice_not_supported",
                ).event()
            )
            return

        audio_started = False
        try:
            sample_rate = await self._adapter.sample_rate()
            await self.write_event(
                AudioStart(rate=sample_rate, width=_PCM_WIDTH_BYTES, channels=_PCM_CHANNELS).event()
            )
            audio_started = True

            async for waveform_chunk in self._adapter.generate(synth.text):
                payload = pcm_float32_to_int16_bytes(waveform_chunk)
                if not payload:
                    continue

                await self.write_event(
                    AudioChunk(
                        rate=sample_rate,
                        width=_PCM_WIDTH_BYTES,
                        channels=_PCM_CHANNELS,
                        audio=payload,
                    ).event()
                )

            await self.write_event(AudioStop().event())
        except Exception as err:
            if audio_started:
                await self.write_event(AudioStop().event())

            await self.write_event(Error(text=f"Synthesis failed: {err}", code="synthesis_failed").event())


class VoxCPMWyomingService:
    """Lifecycle wrapper for adapter startup and Wyoming TCP server."""

    def __init__(
        self,
        config: ServiceConfig,
        adapter_factory: Callable[[ServiceConfig], VoxCPMAdapter],
    ) -> None:
        self._config = config
        self._adapter = adapter_factory(config)
        self._server: AsyncServer | None = None
        self._info: Info | None = None

    async def start(self) -> None:
        await self._adapter.start()
        sample_rate = await self._adapter.sample_rate()
        self._info = build_info(self._config, sample_rate)

        self._server = AsyncServer.from_uri(self._config.uri)
        await self._server.start(self._handler_factory)

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.stop()
            self._server = None

        await self._adapter.stop()

    def _handler_factory(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> VoxCPMWyomingEventHandler:
        if self._info is None:
            raise RuntimeError("Service info has not been initialized")

        return VoxCPMWyomingEventHandler(
            reader,
            writer,
            adapter=self._adapter,
            info=self._info,
            voice_name=self._config.voice_name,
            voice_language=self._config.voice_language,
            voice_speaker=self._config.voice_speaker,
        )
