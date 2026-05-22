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
