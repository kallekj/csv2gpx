"""FastAPI application for uploading, aligning, previewing, and exporting logs."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from csv2gpx.alignment import AlignmentResult, compute_alignment
from csv2gpx.core import (
    CsvLogError,
    LogData,
    default_export_filename,
    export_gpx,
    parse_csv_log,
    sanitize_download_filename,
)
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


@dataclass
class JobState:
    id: str
    directory: Path
    log_path: Path
    video_path: Path
    video_filename: str
    status: str = "queued"
    progress: int = 0
    message: str = "Queued"
    error: str | None = None
    session_id: str | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)


SESSIONS: dict[str, SessionState] = {}
JOBS: dict[str, JobState] = {}


def create_app() -> FastAPI:
    app = FastAPI(title="CSV-to-GPX Video Alignment")
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    @app.get("/")
    async def index(request: Request) -> Response:
        return TEMPLATES.TemplateResponse(request, "index.html")

    @app.post("/api/jobs")
    async def create_job(
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

        job_id = uuid.uuid4().hex
        job_dir = UPLOAD_ROOT / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        log_path = job_dir / safe_upload_name(log_name)
        video_path = job_dir / safe_upload_name(video_name)

        await save_upload(log_file, log_path)
        await save_upload(video_file, video_path)

        job = JobState(
            id=job_id,
            directory=job_dir,
            log_path=log_path,
            video_path=video_path,
            video_filename=video_name,
            status="analyzing",
            progress=55,
            message="Analyzing log and video",
        )
        JOBS[job_id] = job
        job.task = asyncio.create_task(analyze_job(job))
        return job_payload(job)

    @app.post("/api/session")
    async def create_session_legacy(
        log_file: Annotated[UploadFile, File()],
        video_file: Annotated[UploadFile, File()],
    ) -> dict[str, object]:
        job_response = await create_job(log_file, video_file)
        job_id = str(job_response["jobId"])
        while True:
            job = get_job(job_id)
            if job.status == "ready" and job.session_id is not None:
                return session_payload(
                    SESSIONS[job.session_id],
                    compute_alignment_for_session(job.session_id),
                )
            if job.status == "failed":
                raise HTTPException(status_code=400, detail=job.error or "Analysis failed.")
            if job.status == "cancelled":
                raise HTTPException(status_code=400, detail="Analysis was cancelled.")
            await asyncio.sleep(0.02)

    @app.get("/api/jobs/{job_id}")
    async def job_status(job_id: str) -> dict[str, object]:
        return job_payload(get_job(job_id))

    @app.delete("/api/jobs/{job_id}")
    async def cancel_job(job_id: str) -> dict[str, object]:
        job = get_job(job_id)
        if job.status not in {"ready", "failed", "cancelled"}:
            job.status = "cancelled"
            job.progress = 0
            job.message = "Cancelled"
            if job.task is not None:
                job.task.cancel()
        if job.session_id is not None:
            SESSIONS.pop(job.session_id, None)
        shutil.rmtree(job.directory, ignore_errors=True)
        return job_payload(job)

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
        filename: Annotated[str, Form()] = "",
        selected_columns: Annotated[list[str] | None, Form()] = None,
    ) -> Response:
        state = get_session(session_id)
        start = parse_iso_utc(start_time)
        end = parse_iso_utc(end_time)
        if end < start:
            raise HTTPException(status_code=400, detail="Export end time must be after start time.")

        try:
            content = export_gpx(state.log, start, end, selected_columns or [])
        except CsvLogError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        download_name = sanitize_download_filename(
            filename or default_export_filename(state.log_path.name, state.video_filename)
        )
        headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
        return Response(content=content, media_type="application/gpx+xml", headers=headers)

    @app.get("/video/{session_id}")
    async def video(session_id: str) -> FileResponse:
        state = get_session(session_id)
        return FileResponse(state.video_path)

    return app


async def analyze_job(job: JobState) -> None:
    try:
        job.status = "analyzing"
        job.progress = 65
        job.message = "Parsing CSV log"
        log = parse_csv_log(job.log_path)
        if job.status == "cancelled":
            return

        job.progress = 80
        job.message = "Reading video metadata"
        video = probe_video(job.video_path)
        if job.status == "cancelled":
            return

        session_id = uuid.uuid4().hex
        SESSIONS[session_id] = SessionState(
            id=session_id,
            directory=job.directory,
            log=log,
            log_path=job.log_path,
            video_path=job.video_path,
            video_filename=job.video_filename,
            video=video,
        )
        job.session_id = session_id
        job.status = "ready"
        job.progress = 100
        job.message = "Ready"
    except asyncio.CancelledError:
        job.status = "cancelled"
        job.progress = 0
        job.message = "Cancelled"
        raise
    except (CsvLogError, VideoProbeError) as exc:
        job.status = "failed"
        job.progress = 100
        job.error = str(exc)
        job.message = "Analysis failed"


def compute_alignment_for_session(session_id: str) -> AlignmentResult:
    state = get_session(session_id)
    return compute_alignment(state.log, state.video)


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


def get_job(job_id: str) -> JobState:
    try:
        return JOBS[job_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Analysis job was not found.") from exc


def job_payload(job: JobState) -> dict[str, object]:
    payload: dict[str, object] = {
        "jobId": job.id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
    }
    if job.status == "ready" and job.session_id is not None:
        state = SESSIONS[job.session_id]
        payload["session"] = session_payload(state, compute_alignment(state.log, state.video))
    return payload


def session_payload(state: SessionState, alignment: AlignmentResult) -> dict[str, object]:
    return {
        "sessionId": state.id,
        "videoUrl": f"/video/{state.id}",
        "log": {
            "filename": state.log_path.name,
            "pointCount": len(state.log.points),
            "start": iso_or_none(state.log.start_time),
            "end": iso_or_none(state.log.end_time),
            "defaultFilename": default_export_filename(state.log_path.name, state.video_filename),
            "availableColumns": [
                {
                    "name": column.name,
                    "tag": column.tag,
                    "numericCount": column.numeric_count,
                    "selected": column.selected,
                }
                for column in state.log.available_columns
            ],
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
    for job in JOBS.values():
        if job.task is not None and not job.task.done():
            job.task.cancel()
    for state in SESSIONS.values():
        shutil.rmtree(state.directory, ignore_errors=True)
    SESSIONS.clear()
    JOBS.clear()
