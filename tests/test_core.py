import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import pytest

from csv2gpx.core import (
    default_export_filename,
    export_filename,
    export_gpx,
    parse_csv_log,
    safe_float,
    sanitize_download_filename,
    sanitize_extension_tag,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ('""', None),
        ("12.5", 12.5),
        ("12,5", 12.5),
        ("not-a-number", None),
    ],
)
def test_safe_float(value: str | None, expected: float | None) -> None:
    assert safe_float(value) == expected


def test_parse_csv_log_reads_included_sample() -> None:
    log = parse_csv_log(ROOT / "00010012.csv")

    assert len(log.points) == 2772
    assert log.start_time == datetime(2026, 5, 18, 11, 59, 41, tzinfo=UTC)
    assert log.end_time == datetime(2026, 5, 18, 12, 45, 43, tzinfo=UTC)
    assert log.points[0].values["SOG"] == 5.19006
    assert log.column_tags["Fuel_1(%)"] == "fuel_1_percent"
    assert any(column.name == "Depth(min)" for column in log.available_columns)


def test_export_gpx_limits_rows_and_preserves_utc_time() -> None:
    log = parse_csv_log(ROOT / "00010012.csv")
    start = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    end = datetime(2026, 5, 18, 12, 0, 2, tzinfo=UTC)

    content = export_gpx(log, start, end, ["SOG", "Depth"])
    root = ET.fromstring(content)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    points = root.findall(".//g:trkpt", ns)
    time_elements = [point.find("g:time", ns) for point in points]
    assert all(element is not None for element in time_elements)
    times = [element.text for element in time_elements if element is not None]

    assert times == [
        "2026-05-18T12:00:00Z",
        "2026-05-18T12:00:01Z",
        "2026-05-18T12:00:02Z",
    ]
    extensions = points[0].find("g:extensions", ns)
    assert extensions is not None
    sog = extensions.find("g:sog", ns)
    assert sog is not None
    assert sog.text == "5.40389"
    assert extensions.find("g:cog", ns) is None


def test_export_gpx_can_omit_all_extension_columns() -> None:
    log = parse_csv_log(ROOT / "00010012.csv")
    content = export_gpx(
        log,
        datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC),
        datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC),
        [],
    )

    root = ET.fromstring(content)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    extensions = root.find(".//g:extensions", ns)
    assert extensions is not None
    assert list(extensions) == []


@pytest.mark.parametrize(
    ("column_name", "tag"),
    [
        ("Depth(min)", "depth_min"),
        ("Fuel_1(%)", "fuel_1_percent"),
        ("Engine Temp C", "engine_temp_c"),
        ("123 RPM", "col_123_rpm"),
    ],
)
def test_sanitize_extension_tag(column_name: str, tag: str) -> None:
    assert sanitize_extension_tag(column_name) == tag


def test_export_filename_uses_video_stem_and_range() -> None:
    start = datetime(2026, 5, 18, 12, 3, tzinfo=UTC)
    end = datetime(2026, 5, 18, 12, 7, 30, tzinfo=UTC)

    filename = export_filename("GX010123.MP4", "00010012.csv", start, end)

    assert filename == "GX010123_2026-05-18T12-03-00Z_2026-05-18T12-07-30Z.gpx"


def test_download_filename_helpers() -> None:
    assert sanitize_download_filename("My Export") == "My_Export.gpx"
    assert sanitize_download_filename("../bad name.gpx") == "bad_name.gpx"
    assert default_export_filename("00010012.csv", "GX010834.MP4") == "00010012_GX010834.gpx"
