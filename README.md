# CSV to GPX Video Alignment

Local web app for aligning a Simrad/NMEA2000 CSV log with GoPro video footage and exporting a GPX file trimmed to the video section.

## Requirements

- Python 3.12+
- uv
- ffmpeg/ffprobe available on `PATH`

## Install

```bash
uv sync --extra dev
```

## Run

```bash
uv run csv2gpx-web
```

Then open:

```text
http://127.0.0.1:8000
```

The app accepts CSV logs in the Simrad export shape used by `00010012.csv`. DAT uploads are rejected in v1 because the raw format still needs a parser.

## Workflow

1. Upload a CSV log and a video.
2. The app reads the log timestamps and probes video duration/start time with `ffprobe`.
3. If video `creation_time` is present, the overlapping range is selected automatically.
4. Adjust the offset or trim start/end if the camera clock needs correction.
5. Export the trimmed GPX.

## Quality Commands

```bash
make format
make lint
make typecheck
make test
make check
```

## Docker

```bash
make docker-build
docker run --rm -p 8000:8000 csv2gpx:latest
```
