"""FastAPI application for uploading, aligning, previewing, and exporting logs."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from csv2gpx.alignment import AlignmentResult, compute_alignment
from csv2gpx.core import CsvLogError, LogData, export_filename, export_gpx, parse_csv_log
from csv2gpx.video import VideoMetadata, VideoProbeError, probe_video

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
UPLOAD_ROOT = Path(tempfile.gettempdir()) / "csv2gpx-web"


@dataclass
class SessionState:
    id: str
    directory: Path
    log: LogData
    log_path: Path
    video_path: Path
    video_filename: str
    video: VideoMetadata


SESSIONS: dict[str, SessionState] = {}


def create_app() -> FastAPI:
    app = FastAPI(title="CSV-to-GPX Video Alignment")
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    @app.get("/")
    async def index(request: Request) -> Response:
        return TEMPLATES.TemplateResponse(request, "index.html")

    @app.post("/api/session")
    async def create_session(
        log_file: Annotated[UploadFile, File()],
        video_file: Annotated[UploadFile, File()],
    ) -> dict[str, object]:
        log_name = log_file.filename or "log.csv"
        video_name = video_file.filename or "video"

        if Path(log_name).suffix.lower() == ".dat":
            raise HTTPException(
                status_code=400,
                detail="DAT import is not implemented yet. Export the logger data to CSV first.",
            )
        if Path(log_name).suffix.lower() != ".csv":
            raise HTTPException(status_code=400, detail="Only CSV log uploads are supported in v1.")

        session_id = uuid.uuid4().hex
        session_dir = UPLOAD_ROOT / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        log_path = session_dir / safe_upload_name(log_name)
        video_path = session_dir / safe_upload_name(video_name)

        await save_upload(log_file, log_path)
        await save_upload(video_file, video_path)

        try:
            log = parse_csv_log(log_path)
            video = probe_video(video_path)
        except CsvLogError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VideoProbeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        state = SessionState(
            id=session_id,
            directory=session_dir,
            log=log,
            log_path=log_path,
            video_path=video_path,
            video_filename=video_name,
            video=video,
        )
        SESSIONS[session_id] = state

        return session_payload(state, compute_alignment(log, video))

    @app.get("/api/session/{session_id}/alignment")
    async def alignment(session_id: str, offset_seconds: float = 0) -> dict[str, object]:
        state = get_session(session_id)
        alignment_result = compute_alignment(
            state.log,
            state.video,
            offset_seconds=offset_seconds,
        )
        return session_payload(state, alignment_result)

    @app.post("/api/export")
    async def export(
        session_id: Annotated[str, Form()],
        start_time: Annotated[str, Form()],
        end_time: Annotated[str, Form()],
    ) -> Response:
        state = get_session(session_id)
        start = parse_iso_utc(start_time)
        end = parse_iso_utc(end_time)
        if end < start:
            raise HTTPException(status_code=400, detail="Export end time must be after start time.")

        try:
            content = export_gpx(state.log, start, end)
        except CsvLogError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        filename = export_filename(state.video_filename, state.log_path.name, start, end)
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=content, media_type="application/gpx+xml", headers=headers)

    @app.get("/video/{session_id}")
    async def video(session_id: str) -> FileResponse:
        state = get_session(session_id)
        return FileResponse(state.video_path)

    return app


async def save_upload(upload: UploadFile, destination: Path) -> None:
    with destination.open("wb") as handle:
        upload.file.seek(0)
        while chunk := upload.file.read(1024 * 1024):
            handle.write(chunk)


def safe_upload_name(filename: str) -> str:
    name = Path(filename).name.replace("/", "_").replace("\\", "_")
    return name or uuid.uuid4().hex


def get_session(session_id: str) -> SessionState:
    try:
        return SESSIONS[session_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Upload session was not found.") from exc


def session_payload(state: SessionState, alignment: AlignmentResult) -> dict[str, object]:
    return {
        "sessionId": state.id,
        "videoUrl": f"/video/{state.id}",
        "log": {
            "filename": state.log_path.name,
            "pointCount": len(state.log.points),
            "start": iso_or_none(state.log.start_time),
            "end": iso_or_none(state.log.end_time),
            "preview": track_preview(state.log),
        },
        "video": {
            "filename": state.video_filename,
            "durationSeconds": state.video.duration_seconds,
            "creationTime": iso_or_none(state.video.creation_time),
        },
        "alignment": {
            "status": alignment.status,
            "videoStart": iso_or_none(alignment.video_start),
            "videoEnd": iso_or_none(alignment.video_end),
            "exportStart": iso_or_none(alignment.export_start),
            "exportEnd": iso_or_none(alignment.export_end),
            "overlapSeconds": alignment.overlap_seconds,
        },
    }


def track_preview(log: LogData, limit: int = 600) -> list[dict[str, float]]:
    if len(log.points) <= limit:
        points = log.points
    else:
        step = len(log.points) / limit
        points = [log.points[int(index * step)] for index in range(limit)]

    return [{"lat": point.lat, "lon": point.lon} for point in points]


def iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_iso_utc(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp: {value}") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def cleanup_sessions() -> None:
    for state in SESSIONS.values():
        shutil.rmtree(state.directory, ignore_errors=True)
    SESSIONS.clear()
