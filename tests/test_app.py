import asyncio
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi import UploadFile
from fastapi.routing import APIRoute
from starlette.responses import Response

from csv2gpx.app import cleanup_sessions, create_app
from csv2gpx.video import VideoMetadata

ROOT = Path(__file__).resolve().parents[1]


def test_app_upload_and_export_with_mocked_video_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(run_app_upload_and_export(monkeypatch))


async def run_app_upload_and_export(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_probe_video(_path: Path) -> VideoMetadata:
        return VideoMetadata(3, datetime(2026, 5, 18, 12, 0, tzinfo=UTC))

    monkeypatch.setattr("csv2gpx.app.probe_video", fake_probe_video)
    app = create_app()

    try:
        create_session = route_endpoint(app, "/api/session")
        export = route_endpoint(app, "/api/export")

        payload = await create_session(
            log_file=UploadFile(
                filename="00010012.csv",
                file=BytesIO((ROOT / "00010012.csv").read_bytes()),
            ),
            video_file=UploadFile(filename="GX010123.MP4", file=BytesIO(b"fake-video")),
        )

        assert payload["alignment"]["status"] == "aligned"

        response = await export(
            session_id=payload["sessionId"],
            start_time=payload["alignment"]["exportStart"],
            end_time=payload["alignment"]["exportEnd"],
        )

        assert isinstance(response, Response)
        assert response.media_type == "application/gpx+xml"
        assert b"2026-05-18T12:00:00Z" in response.body
    finally:
        cleanup_sessions()


def route_endpoint(app: Any, path: str) -> Any:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path:
            return route.endpoint
    raise AssertionError(f"Route not found: {path}")
