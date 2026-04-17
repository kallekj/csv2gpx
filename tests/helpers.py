from __future__ import annotations

from typing import Any

from voxcpm_wyomming.config import ServiceConfig


def build_test_config(**overrides: Any) -> ServiceConfig:
    base = {
        "model": "openbmb/VoxCPM2",
        "host": "127.0.0.1",
        "port": 10200,
        "devices": (0,),
        "max_num_batched_tokens": 8192,
        "max_num_seqs": 16,
        "gpu_memory_utilization": 0.95,
        "inference_timesteps": 10,
        "enforce_eager": False,
        "sample_rate_override": None,
        "service_name": "voxcpm",
        "service_description": "VoxCPM Wyoming TTS service",
        "service_version": "0.1.0",
        "voice_name": "default",
        "voice_language": "en",
        "voice_speaker": None,
        "voice_description": "Default VoxCPM voice",
        "voice_version": "0.1.0",
        "attribution_name": "VoxCPM",
        "attribution_url": "https://github.com/OpenBMB/VoxCPM",
        "log_level": "INFO",
    }
    base.update(overrides)
    return ServiceConfig(**base)
