import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from csv2gpx.video import VideoProbeError, parse_ffprobe_json, probe_video


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


def test_probe_video_handles_ffprobe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailedProcess:
        returncode = 1

        def communicate(self, timeout: float) -> tuple[str, str]:
            return "", "bad video"

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FailedProcess())

    with pytest.raises(VideoProbeError, match="bad video"):
        probe_video(Path("video.mp4"))


def test_probe_video_kills_timed_out_ffprobe(monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowProcess:
        returncode = None
        killed = False

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            if self.killed:
                return "", ""
            raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=timeout or 0)

        def kill(self) -> None:
            self.killed = True

    process = SlowProcess()

    def fake_popen(*args: Any, **kwargs: Any) -> SlowProcess:
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    with pytest.raises(VideoProbeError, match="timed out"):
        probe_video(Path("video.mp4"), timeout_seconds=0.1)

    assert process.killed is True
