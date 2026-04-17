"""Audio conversion helpers for Wyoming-compatible PCM output."""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

_FLOAT_CLIP_MIN = -1.0
_FLOAT_CLIP_MAX = 1.0
_INT16_SCALE = 32767.0


def pcm_float32_to_int16_bytes(samples: npt.ArrayLike) -> bytes:
    """Convert float32 waveform samples to little-endian int16 PCM bytes.

    Wyoming audio events expect PCM payloads. VoxCPM yields float32 arrays,
    typically in the range ``[-1.0, 1.0]``.
    """
    array = np.asarray(samples, dtype=np.float32)
    if array.size == 0:
        return b""

    flat = array.reshape(-1)
    safe = np.nan_to_num(flat, nan=0.0, posinf=1.0, neginf=-1.0)
    clipped = np.clip(safe, _FLOAT_CLIP_MIN, _FLOAT_CLIP_MAX)
    pcm = (clipped * _INT16_SCALE).astype(np.int16)
    return pcm.tobytes()


def bytes_to_pcm_int16(samples: bytes) -> npt.NDArray[np.int16]:
    """Decode int16 PCM bytes for tests and internal checks."""
    return np.frombuffer(samples, dtype=np.int16)


def as_float32_array(samples: Any) -> npt.NDArray[np.float32]:
    """Normalize unknown waveform-like data into a float32 numpy array."""
    return np.asarray(samples, dtype=np.float32)
