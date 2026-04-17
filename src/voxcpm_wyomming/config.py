"""Configuration and CLI parsing for the VoxCPM Wyoming service."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    """Runtime configuration for the Wyoming TCP service."""

    model: str
    host: str
    port: int
    devices: tuple[int, ...]
    max_num_batched_tokens: int
    max_num_seqs: int
    gpu_memory_utilization: float
    inference_timesteps: int
    enforce_eager: bool
    sample_rate_override: int | None
    service_name: str
    service_description: str | None
    service_version: str | None
    voice_name: str
    voice_language: str
    voice_speaker: str | None
    voice_description: str | None
    voice_version: str | None
    attribution_name: str
    attribution_url: str
    log_level: str

    @property
    def uri(self) -> str:
        """Return the Wyoming TCP URI for this service instance."""
        return f"tcp://{self.host}:{self.port}"


def _parse_devices(raw: str) -> tuple[int, ...]:
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    if not parts:
        raise ValueError("devices list is empty")

    try:
        devices = tuple(int(item) for item in parts)
    except ValueError as err:  # pragma: no cover - handled in caller tests
        raise ValueError("devices must be a comma-separated list of integers") from err

    if any(device < 0 for device in devices):
        raise ValueError("devices must be non-negative integers")

    return devices


def build_arg_parser() -> argparse.ArgumentParser:
    """Create and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="voxcpm",
        description="VoxCPM Wyoming text-to-speech service (TCP).",
    )

    parser.add_argument(
        "--model",
        default=os.getenv("VOXCPM_MODEL"),
        help="Model path or HuggingFace repo id (env: VOXCPM_MODEL).",
    )
    parser.add_argument("--host", default=os.getenv("VOXCPM_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("VOXCPM_PORT", "10200")))
    parser.add_argument("--devices", default=os.getenv("VOXCPM_DEVICES", "0"))
    parser.add_argument(
        "--max-num-batched-tokens",
        type=int,
        default=int(os.getenv("VOXCPM_MAX_NUM_BATCHED_TOKENS", "8192")),
    )
    parser.add_argument(
        "--max-num-seqs",
        type=int,
        default=int(os.getenv("VOXCPM_MAX_NUM_SEQS", "16")),
    )
    parser.add_argument(
        "--gpu-memory-utilization",
        type=float,
        default=float(os.getenv("VOXCPM_GPU_MEMORY_UTILIZATION", "0.95")),
    )
    parser.add_argument(
        "--inference-timesteps",
        type=int,
        default=int(os.getenv("VOXCPM_INFERENCE_TIMESTEPS", "10")),
    )
    parser.add_argument("--enforce-eager", action="store_true")
    parser.add_argument("--sample-rate-override", type=int, default=None)

    parser.add_argument("--service-name", default=os.getenv("VOXCPM_SERVICE_NAME", "voxcpm"))
    parser.add_argument(
        "--service-description",
        default=os.getenv("VOXCPM_SERVICE_DESCRIPTION", "VoxCPM Wyoming TTS service"),
    )
    parser.add_argument("--service-version", default=os.getenv("VOXCPM_SERVICE_VERSION", None))

    parser.add_argument("--voice-name", default=os.getenv("VOXCPM_VOICE_NAME", "default"))
    parser.add_argument("--voice-language", default=os.getenv("VOXCPM_VOICE_LANGUAGE", "en"))
    parser.add_argument("--voice-speaker", default=os.getenv("VOXCPM_VOICE_SPEAKER", None))
    parser.add_argument(
        "--voice-description",
        default=os.getenv("VOXCPM_VOICE_DESCRIPTION", "Default VoxCPM voice"),
    )
    parser.add_argument("--voice-version", default=os.getenv("VOXCPM_VOICE_VERSION", None))

    parser.add_argument(
        "--attribution-name",
        default=os.getenv("VOXCPM_ATTRIBUTION_NAME", "VoxCPM"),
    )
    parser.add_argument(
        "--attribution-url",
        default=os.getenv("VOXCPM_ATTRIBUTION_URL", "https://github.com/OpenBMB/VoxCPM"),
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("VOXCPM_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    return parser


def config_from_args(args: argparse.Namespace) -> ServiceConfig:
    """Validate parsed arguments and convert them to service config."""
    model = str(args.model or "").strip()
    if not model:
        raise ValueError("--model is required (or set VOXCPM_MODEL)")

    if args.port <= 0 or args.port > 65535:
        raise ValueError("--port must be between 1 and 65535")

    if args.max_num_batched_tokens < 1:
        raise ValueError("--max-num-batched-tokens must be >= 1")

    if args.max_num_seqs < 1:
        raise ValueError("--max-num-seqs must be >= 1")

    if not (0 < args.gpu_memory_utilization <= 1):
        raise ValueError("--gpu-memory-utilization must be in (0, 1]")

    devices = _parse_devices(args.devices)

    return ServiceConfig(
        model=model,
        host=args.host,
        port=args.port,
        devices=devices,
        max_num_batched_tokens=args.max_num_batched_tokens,
        max_num_seqs=args.max_num_seqs,
        gpu_memory_utilization=args.gpu_memory_utilization,
        inference_timesteps=args.inference_timesteps,
        enforce_eager=args.enforce_eager,
        sample_rate_override=args.sample_rate_override,
        service_name=args.service_name,
        service_description=args.service_description,
        service_version=args.service_version,
        voice_name=args.voice_name,
        voice_language=args.voice_language,
        voice_speaker=args.voice_speaker,
        voice_description=args.voice_description,
        voice_version=args.voice_version,
        attribution_name=args.attribution_name,
        attribution_url=args.attribution_url,
        log_level=args.log_level,
    )
