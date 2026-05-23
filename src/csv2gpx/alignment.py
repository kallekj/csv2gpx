"""Timestamp alignment helpers for logs and videos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from csv2gpx.core import LogData, ensure_utc
from csv2gpx.video import VideoMetadata


@dataclass(frozen=True)
class AlignmentResult:
    status: str
    log_start: datetime
    log_end: datetime
    video_start: datetime | None
    video_end: datetime | None
    export_start: datetime | None
    export_end: datetime | None
    overlap_seconds: float


class AlignmentError(ValueError):
    """Raised when a video clip cannot be mapped onto the log timeline."""


def compute_alignment(
    log: LogData,
    video: VideoMetadata,
    *,
    offset_seconds: float = 0,
) -> AlignmentResult:
    log_start = ensure_utc(log.start_time)
    log_end = ensure_utc(log.end_time)

    if video.creation_time is None:
        return AlignmentResult(
            status="missing_video_time",
            log_start=log_start,
            log_end=log_end,
            video_start=None,
            video_end=None,
            export_start=None,
            export_end=None,
            overlap_seconds=0,
        )

    video_start = ensure_utc(video.creation_time) + timedelta(seconds=offset_seconds)
    video_end = video_start + timedelta(seconds=video.duration_seconds)
    export_start = max(log_start, video_start)
    export_end = min(log_end, video_end)
    overlap_seconds = max(0.0, (export_end - export_start).total_seconds())
    status = "aligned" if overlap_seconds > 0 else "no_overlap"

    return AlignmentResult(
        status=status,
        log_start=log_start,
        log_end=log_end,
        video_start=video_start,
        video_end=video_end,
        export_start=export_start if overlap_seconds > 0 else None,
        export_end=export_end if overlap_seconds > 0 else None,
        overlap_seconds=overlap_seconds,
    )


def clip_range_to_log_range(
    alignment: AlignmentResult,
    clip_start_seconds: float,
    clip_end_seconds: float,
    *,
    manual_log_start: datetime | None = None,
) -> tuple[datetime, datetime]:
    if clip_start_seconds < 0 or clip_end_seconds < 0:
        raise AlignmentError("Clip times must be positive.")
    if clip_end_seconds <= clip_start_seconds:
        raise AlignmentError("Clip end must be after clip start.")

    duration = timedelta(seconds=clip_end_seconds - clip_start_seconds)
    if alignment.video_start is not None:
        start = alignment.video_start + timedelta(seconds=clip_start_seconds)
        end = alignment.video_start + timedelta(seconds=clip_end_seconds)
    elif manual_log_start is not None:
        start = ensure_utc(manual_log_start)
        end = start + duration
    else:
        raise AlignmentError("Manual log start is required when video start time is missing.")

    if start < alignment.log_start or end > alignment.log_end:
        raise AlignmentError("Selected video range falls outside the log time range.")

    return start, end
