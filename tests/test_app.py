import asyncio
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import UploadFile
from fastapi.exceptions import HTTPException
from fastapi.routing import APIRoute
from starlette.responses import Response

from csv2gpx.app import JOBS, JobState, cleanup_sessions, create_app
from csv2gpx.video import VideoMetadata, VideoProbeError

ROOT = Path(__file__).resolve().parents[1]


def test_app_upload_and_export_with_mocked_video_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(run_app_upload_and_export(monkeypatch))


async def run_app_upload_and_export(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_probe_video(_path: Path) -> VideoMetadata:
        return VideoMetadata(3, datetime(2026, 5, 18, 12, 0, tzinfo=UTC))

    monkeypatch.setattr("csv2gpx.app.probe_video", fake_probe_video)
    app = create_app()

    try:
        create_job = route_endpoint(app, "/api/jobs", "POST")
        job_status = route_endpoint(app, "/api/jobs/{job_id}", "GET")
        export = route_endpoint(app, "/api/export", "POST")

        job_payload = await create_job(
            log_file=UploadFile(
                filename="00010012.csv",
                file=BytesIO((ROOT / "00010012.csv").read_bytes()),
            ),
            video_file=UploadFile(filename="GX010123.MP4", file=BytesIO(b"fake-video")),
        )
        assert job_payload["status"] == "analyzing"

        payload = await wait_for_ready_job(job_status, str(job_payload["jobId"]))
        session = payload["session"]

        assert session["alignment"]["status"] == "aligned"
        assert session["log"]["defaultFilename"] == "00010012_GX010123.gpx"
        assert "preview" not in session["log"]
        assert session["log"]["availableColumns"][0]["selected"] is True

        response = await export(
            session_id=session["sessionId"],
            start_time=session["alignment"]["exportStart"],
            end_time=session["alignment"]["exportEnd"],
            filename="my clip",
            selected_columns=["SOG"],
        )

        assert isinstance(response, Response)
        assert response.media_type == "application/gpx+xml"
        assert response.headers["content-disposition"] == 'attachment; filename="my_clip.gpx"'
        assert b"2026-05-18T12:00:00Z" in response.body
        assert b"<sog>" in response.body
        assert b"<cog>" not in response.body
    finally:
        cleanup_sessions()


def test_cancel_job_cleans_up_state() -> None:
    app = create_app()
    cancel_job = route_endpoint(app, "/api/jobs/{job_id}", "DELETE")
    try:
        job_id = "cancel-me"
        job_dir = ROOT / ".pytest-cancel-job"
        job_dir.mkdir(exist_ok=True)
        JOBS[job_id] = JobState(
            id=job_id,
            directory=job_dir,
            log_path=job_dir / "log.csv",
            video_path=job_dir / "video.mp4",
            video_filename="video.mp4",
            status="analyzing",
        )

        payload = asyncio.run(cancel_job(job_id))

        assert payload["status"] == "cancelled"
        assert not job_dir.exists()
    finally:
        cleanup_sessions()


def test_job_upload_rejects_dat_logs() -> None:
    app = create_app()
    create_job = route_endpoint(app, "/api/jobs", "POST")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            create_job(
                log_file=UploadFile(filename="00010020.DAT", file=BytesIO(b"raw")),
                video_file=UploadFile(filename="GX010123.MP4", file=BytesIO(b"fake-video")),
            )
        )

    assert exc_info.value.status_code == 400
    assert "DAT import is not implemented" in exc_info.value.detail


def test_job_payload_reports_failed_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_probe_video(_path: Path) -> VideoMetadata:
        raise VideoProbeError("unexpected")

    monkeypatch.setattr("csv2gpx.app.probe_video", fake_probe_video)
    app = create_app()
    create_job = route_endpoint(app, "/api/jobs", "POST")
    job_status = route_endpoint(app, "/api/jobs/{job_id}", "GET")

    try:
        job_payload = asyncio.run(
            create_job(
                log_file=UploadFile(
                    filename="00010012.csv",
                    file=BytesIO((ROOT / "00010012.csv").read_bytes()),
                ),
                video_file=UploadFile(filename="GX010123.MP4", file=BytesIO(b"fake-video")),
            )
        )

        payload = asyncio.run(wait_for_terminal_job(job_status, str(job_payload["jobId"])))

        assert payload["status"] == "failed"
    finally:
        cleanup_sessions()


async def wait_for_ready_job(job_status: Any, job_id: str) -> dict[str, Any]:
    for _ in range(20):
        payload = await job_status(job_id)
        if payload["status"] == "ready":
            return cast(dict[str, Any], payload)
        await asyncio.sleep(0.01)
    raise AssertionError("Job did not become ready.")


async def wait_for_terminal_job(job_status: Any, job_id: str) -> dict[str, Any]:
    for _ in range(20):
        payload = await job_status(job_id)
        if payload["status"] in {"ready", "failed", "cancelled"}:
            return cast(dict[str, Any], payload)
        await asyncio.sleep(0.01)
    raise AssertionError("Job did not finish.")


def route_endpoint(app: Any, path: str, method: str) -> Any:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route.endpoint
    raise AssertionError(f"Route not found: {method} {path}")
