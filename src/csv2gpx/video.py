"""Video metadata probing through ffprobe."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float
    creation_time: datetime | None


class VideoProbeError(RuntimeError):
    """Raised when ffprobe cannot read enough video metadata."""


def probe_video(path: Path, timeout_seconds: float = 30) -> VideoMetadata:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:format_tags=creation_time:stream_tags=creation_time",
        "-of",
        "json",
        str(path),
    ]
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise VideoProbeError("ffprobe is not installed or not available on PATH.") from exc

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate()
        raise VideoProbeError("ffprobe timed out while reading the video.") from exc

    if process.returncode != 0:
        detail = stderr.strip() or stdout.strip() or "unknown ffprobe error"
        raise VideoProbeError(f"ffprobe could not read the video: {detail}")

    return parse_ffprobe_json(stdout)


def parse_ffprobe_json(payload: str) -> VideoMetadata:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise VideoProbeError("ffprobe returned invalid JSON.") from exc

    raw_duration = data.get("format", {}).get("duration")
    try:
        duration_seconds = float(raw_duration)
    except (TypeError, ValueError) as exc:
        raise VideoProbeError("ffprobe did not return a usable video duration.") from exc

    if duration_seconds <= 0:
        raise VideoProbeError("ffprobe returned a non-positive video duration.")

    return VideoMetadata(
        duration_seconds=duration_seconds,
        creation_time=find_creation_time(data),
    )


def find_creation_time(data: dict[str, Any]) -> datetime | None:
    candidates: list[str] = []
    format_tags = data.get("format", {}).get("tags", {})
    if isinstance(format_tags, dict) and isinstance(format_tags.get("creation_time"), str):
        candidates.append(format_tags["creation_time"])

    streams = data.get("streams", [])
    if isinstance(streams, list):
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            tags = stream.get("tags", {})
            if isinstance(tags, dict) and isinstance(tags.get("creation_time"), str):
                candidates.append(tags["creation_time"])

    for candidate in candidates:
        parsed = parse_video_time(candidate)
        if parsed is not None:
            return parsed
    return None


def parse_video_time(value: str) -> datetime | None:
    normalized = value.strip()
    if normalized == "":
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
