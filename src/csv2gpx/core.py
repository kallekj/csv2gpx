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

EXTENSION_COLUMNS = {
    "sog_knots": "SOG",
    "cog_degrees": "COG",
    "depth_m": "Depth",
    "water_temp_c": "WaterTemp",
    "engine_rpm": "Engine1_RPM",
    "fuel_rate_lph": "FuelRate1",
    "engine_temp_c": "EngineTemp1",
    "oil_pressure": "OilPressure1",
    "coolant_pressure_kpa": "CoolantPressure1",
}


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

    @property
    def start_time(self) -> datetime:
        return self.points[0].time

    @property
    def end_time(self) -> datetime:
        return self.points[-1].time


class CsvLogError(ValueError):
    """Raised when an uploaded log cannot be parsed as a supported CSV log."""


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

        values = {
            extension_name: safe_float(row.get(column_name))
            for extension_name, column_name in EXTENSION_COLUMNS.items()
        }
        points.append(TrackPoint(index=index, time=point_time, lat=lat, lon=lon, values=values))

    if not points:
        raise CsvLogError("CSV file did not contain any usable GPS points.")

    return LogData(source_name=source_name, points=points)


def track_points_between(
    log: LogData,
    start_time: datetime,
    end_time: datetime,
) -> list[TrackPoint]:
    start_utc = ensure_utc(start_time)
    end_utc = ensure_utc(end_time)
    return [point for point in log.points if start_utc <= point.time <= end_utc]


def export_gpx(log: LogData, start_time: datetime, end_time: datetime) -> bytes:
    selected_points = track_points_between(log, start_time, end_time)
    if not selected_points:
        raise CsvLogError("Selected range does not contain any GPS points.")

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
        for extension_name, value in point.values.items():
            if value is None:
                continue
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
