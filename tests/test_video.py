from datetime import UTC, datetime

import pytest

from csv2gpx.video import VideoProbeError, parse_ffprobe_json


def test_parse_ffprobe_json_uses_format_creation_time() -> None:
    metadata = parse_ffprobe_json(
        """
        {
          "format": {
            "duration": "12.5",
            "tags": {"creation_time": "2026-05-18T12:03:00.000000Z"}
          },
          "streams": []
        }
        """
    )

    assert metadata.duration_seconds == 12.5
    assert metadata.creation_time == datetime(2026, 5, 18, 12, 3, tzinfo=UTC)


def test_parse_ffprobe_json_uses_stream_creation_time() -> None:
    metadata = parse_ffprobe_json(
        """
        {
          "format": {"duration": "7"},
          "streams": [
            {"tags": {"creation_time": "2026-05-18T12:04:00+00:00"}}
          ]
        }
        """
    )

    assert metadata.creation_time == datetime(2026, 5, 18, 12, 4, tzinfo=UTC)


def test_parse_ffprobe_json_allows_missing_creation_time() -> None:
    metadata = parse_ffprobe_json('{"format": {"duration": "7"}, "streams": []}')

    assert metadata.duration_seconds == 7
    assert metadata.creation_time is None


def test_parse_ffprobe_json_requires_duration() -> None:
    with pytest.raises(VideoProbeError):
        parse_ffprobe_json('{"format": {}, "streams": []}')
