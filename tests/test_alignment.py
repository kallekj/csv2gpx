from datetime import UTC, datetime

from csv2gpx.alignment import compute_alignment
from csv2gpx.core import LogData, TrackPoint
from csv2gpx.video import VideoMetadata


def make_log() -> LogData:
    return LogData(
        source_name="test.csv",
        points=[
            TrackPoint(0, datetime(2026, 5, 18, 12, 0, tzinfo=UTC), 58.0, 11.0, {}),
            TrackPoint(1, datetime(2026, 5, 18, 12, 10, tzinfo=UTC), 58.1, 11.1, {}),
        ],
    )


def test_alignment_fully_inside_log() -> None:
    result = compute_alignment(
        make_log(),
        VideoMetadata(60, datetime(2026, 5, 18, 12, 2, tzinfo=UTC)),
    )

    assert result.status == "aligned"
    assert result.export_start == datetime(2026, 5, 18, 12, 2, tzinfo=UTC)
    assert result.export_end == datetime(2026, 5, 18, 12, 3, tzinfo=UTC)
    assert result.overlap_seconds == 60


def test_alignment_partially_overlaps_log() -> None:
    result = compute_alignment(
        make_log(),
        VideoMetadata(120, datetime(2026, 5, 18, 11, 59, tzinfo=UTC)),
    )

    assert result.status == "aligned"
    assert result.export_start == datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    assert result.export_end == datetime(2026, 5, 18, 12, 1, tzinfo=UTC)
    assert result.overlap_seconds == 60


def test_alignment_no_overlap() -> None:
    result = compute_alignment(
        make_log(),
        VideoMetadata(60, datetime(2026, 5, 18, 12, 30, tzinfo=UTC)),
    )

    assert result.status == "no_overlap"
    assert result.export_start is None
    assert result.export_end is None


def test_alignment_missing_creation_time() -> None:
    result = compute_alignment(make_log(), VideoMetadata(60, None))

    assert result.status == "missing_video_time"
    assert result.video_start is None
    assert result.export_start is None


def test_alignment_applies_offset() -> None:
    result = compute_alignment(
        make_log(),
        VideoMetadata(60, datetime(2026, 5, 18, 12, 2, tzinfo=UTC)),
        offset_seconds=30,
    )

    assert result.video_start == datetime(2026, 5, 18, 12, 2, 30, tzinfo=UTC)
