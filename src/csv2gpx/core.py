"""Core CSV parsing and GPX export helpers."""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
BASE_COLUMNS = {"Time", "Latitude", "Longitude"}


@dataclass(frozen=True)
class TrackPoint:
    index: int
    time: datetime
    lat: float
    lon: float
    values: dict[str, float | None]


@dataclass(frozen=True)
class LogData:
    source_name: str
    points: list[TrackPoint]
    available_columns: list[ColumnInfo]
    column_tags: dict[str, str]

    @property
    def start_time(self) -> datetime:
        return self.points[0].time

    @property
    def end_time(self) -> datetime:
        return self.points[-1].time


class CsvLogError(ValueError):
    """Raised when an uploaded log cannot be parsed as a supported CSV log."""


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    tag: str
    numeric_count: int
    selected: bool = True


def safe_float(value: str | None) -> float | None:
    if value is None:
        return None

    cleaned = value.strip().strip('"')
    if cleaned == "":
        return None

    try:
        return float(cleaned.replace(",", "."))
    except ValueError:
        return None


def parse_csv_log(path: Path) -> LogData:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return parse_csv_log_stream(handle, source_name=path.name)


def parse_csv_log_stream(handle: TextIO, source_name: str) -> LogData:
    reader = csv.DictReader(handle)
    if reader.fieldnames is None:
        raise CsvLogError("CSV file is empty.")

    required = {"Time", "Latitude", "Longitude"}
    missing = required.difference(reader.fieldnames)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise CsvLogError(f"CSV file is missing required column(s): {missing_list}.")

    candidates = [field for field in reader.fieldnames if field not in BASE_COLUMNS]
    numeric_counts = dict.fromkeys(candidates, 0)
    points: list[TrackPoint] = []
    for index, row in enumerate(reader):
        lat = safe_float(row.get("Latitude"))
        lon = safe_float(row.get("Longitude"))
        if lat is None or lon is None:
            continue

        raw_time = row.get("Time", "").strip()
        try:
            point_time = datetime.strptime(raw_time, TIME_FORMAT).replace(tzinfo=UTC)
        except ValueError as exc:
            raise CsvLogError(f"Invalid timestamp at CSV row {index + 2}: {raw_time}") from exc

        values: dict[str, float | None] = {}
        for column_name in candidates:
            value = safe_float(row.get(column_name))
            values[column_name] = value
            if value is not None:
                numeric_counts[column_name] += 1
        points.append(TrackPoint(index=index, time=point_time, lat=lat, lon=lon, values=values))

    if not points:
        raise CsvLogError("CSV file did not contain any usable GPS points.")

    available_columns = [
        ColumnInfo(name=name, tag="", numeric_count=count)
        for name, count in numeric_counts.items()
        if count > 0
    ]
    tag_by_name = unique_column_tags([column.name for column in available_columns])
    available_columns = [
        ColumnInfo(
            name=column.name,
            tag=tag_by_name[column.name],
            numeric_count=column.numeric_count,
        )
        for column in available_columns
    ]

    return LogData(
        source_name=source_name,
        points=points,
        available_columns=available_columns,
        column_tags=tag_by_name,
    )


def track_points_between(
    log: LogData,
    start_time: datetime,
    end_time: datetime,
) -> list[TrackPoint]:
    start_utc = ensure_utc(start_time)
    end_utc = ensure_utc(end_time)
    return [point for point in log.points if start_utc <= point.time <= end_utc]


def export_gpx(
    log: LogData,
    start_time: datetime,
    end_time: datetime,
    selected_columns: list[str] | None = None,
) -> bytes:
    selected_points = track_points_between(log, start_time, end_time)
    if not selected_points:
        raise CsvLogError("Selected range does not contain any GPS points.")

    columns = (
        selected_columns
        if selected_columns is not None
        else [column.name for column in log.available_columns]
    )
    allowed_columns = {column.name for column in log.available_columns}
    columns = [column for column in columns if column in allowed_columns]

    ET.register_namespace("", GPX_NAMESPACE)
    gpx = ET.Element(
        f"{{{GPX_NAMESPACE}}}gpx",
        version="1.1",
        creator="csv2gpx video alignment web app",
    )

    trk = ET.SubElement(gpx, f"{{{GPX_NAMESPACE}}}trk")
    name = ET.SubElement(trk, f"{{{GPX_NAMESPACE}}}name")
    name.text = "NMEA2000 video-aligned log"
    trkseg = ET.SubElement(trk, f"{{{GPX_NAMESPACE}}}trkseg")

    for point in selected_points:
        trkpt = ET.SubElement(
            trkseg,
            f"{{{GPX_NAMESPACE}}}trkpt",
            lat=f"{point.lat:.7f}",
            lon=f"{point.lon:.7f}",
        )
        time_el = ET.SubElement(trkpt, f"{{{GPX_NAMESPACE}}}time")
        time_el.text = format_gpx_time(point.time)

        extensions = ET.SubElement(trkpt, f"{{{GPX_NAMESPACE}}}extensions")
        for column_name in columns:
            value = point.values.get(column_name)
            if value is None:
                continue
            extension_name = log.column_tags[column_name]
            child = ET.SubElement(extensions, extension_name)
            child.text = str(value)

    tree = ET.ElementTree(gpx)
    ET.indent(tree, space="  ", level=0)
    output = io.BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    return output.getvalue()


def format_gpx_time(value: datetime) -> str:
    return ensure_utc(value).isoformat().replace("+00:00", "Z")


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def sanitize_extension_tag(column_name: str) -> str:
    tag = column_name.strip().replace("%", " percent ")
    tag = re.sub(r"[^0-9A-Za-z]+", "_", tag).strip("_").lower()
    tag = re.sub(r"_+", "_", tag)
    if tag == "":
        tag = "value"
    if tag[0].isdigit():
        tag = f"col_{tag}"
    return tag


def unique_column_tags(column_names: list[str]) -> dict[str, str]:
    used: dict[str, int] = {}
    tags: dict[str, str] = {}
    for name in column_names:
        base_tag = sanitize_extension_tag(name)
        count = used.get(base_tag, 0)
        used[base_tag] = count + 1
        tags[name] = base_tag if count == 0 else f"{base_tag}_{count + 1}"
    return tags


def sanitize_download_filename(filename: str) -> str:
    stem = filename.strip()
    if stem.lower().endswith(".gpx"):
        stem = stem[:-4]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    if stem == "":
        stem = "aligned-log"
    return f"{stem}.gpx"


def default_export_filename(log_name: str, video_name: str) -> str:
    log_stem = Path(log_name).stem or "log"
    video_stem = Path(video_name).stem or "video"
    return sanitize_download_filename(f"{log_stem}_{video_stem}.gpx")


def export_filename(
    video_name: str,
    log_name: str,
    start_time: datetime,
    end_time: datetime,
) -> str:
    stem = Path(video_name).stem or Path(log_name).stem or "export"
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "export"
    start = format_gpx_time(start_time).replace(":", "-")
    end = format_gpx_time(end_time).replace(":", "-")
    return f"{safe_stem}_{start}_{end}.gpx"
