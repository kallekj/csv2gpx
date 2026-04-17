from __future__ import annotations

import numpy as np

from voxcpm_wyomming.audio import bytes_to_pcm_int16, pcm_float32_to_int16_bytes


def test_pcm_float32_to_int16_bytes_clamps_and_scales() -> None:
    pcm = pcm_float32_to_int16_bytes(np.array([-2.0, -1.0, 0.0, 1.0, 2.0], dtype=np.float32))
    values = bytes_to_pcm_int16(pcm).tolist()
    assert values == [-32767, -32767, 0, 32767, 32767]


def test_pcm_float32_to_int16_bytes_handles_nan_and_inf() -> None:
    pcm = pcm_float32_to_int16_bytes(np.array([np.nan, np.inf, -np.inf], dtype=np.float32))
    values = bytes_to_pcm_int16(pcm).tolist()
    assert values == [0, 32767, -32767]


def test_pcm_float32_to_int16_bytes_empty() -> None:
    assert pcm_float32_to_int16_bytes(np.array([], dtype=np.float32)) == b""
