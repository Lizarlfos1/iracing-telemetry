# Phase 2: CSV Export — Implementation Plan

---

## 1. Overview

Phase 2 takes the in-memory parsed data from Phase 1 (`ParsedSession` with list of `ParsedLap`) and writes one CSV file per lap to disk. The output must exactly match the format of `OutputDataExample.csv`.

At the end of this phase, we will have:

- A CSV exporter that writes per-lap files matching the reference format exactly
- An output folder structure organized by session (track, car, date)
- An end-to-end pipeline: `.ibt` file → parse → CSV files on disk
- A CLI command: `python -m src.csv_exporter path/to/file.ibt` that processes a file and writes CSVs
- Tests validating format correctness against the reference

---

## 2. CSV Format Specification

Based on analysis of `OutputDataExample.csv`:

| Property | Value |
|----------|-------|
| Delimiter | Comma (`,`) |
| Line endings | LF (`\n`), Unix-style |
| Trailing newline | No |
| BOM | None |
| Encoding | UTF-8 |
| Quoting | None |

### Column Headers (exact order)

```
Speed,LapDistPct,Lat,Lon,Brake,Throttle,RPM,SteeringWheelAngle,Gear,Clutch,ABSActive,DRSActive,LatAccel,LongAccel,VertAccel,Yaw,YawRate,PositionType
```

### Value Formatting Rules

| Column | Type | Format | Example |
|--------|------|--------|---------|
| Speed | float | Full precision, no trailing zeros | `52.367892` |
| LapDistPct | float | Full precision | `0.000213` |
| Lat | float | Full precision | `42.389511` |
| Lon | float | Full precision | `-83.628937` |
| Brake | float | Full precision | `0.0` |
| Throttle | float | Full precision | `0.78` |
| RPM | float | Full precision | `6823.456` |
| SteeringWheelAngle | float | Full precision | `-0.123456` |
| Gear | int | Integer, no decimal | `4` |
| Clutch | float | Full precision | `1.0` |
| ABSActive | bool | Lowercase string | `true` or `false` |
| DRSActive | bool | Lowercase string | `true` or `false` |
| LatAccel | float | Full precision | `-2.345678` |
| LongAccel | float | Full precision | `1.234567` |
| VertAccel | float | Full precision | `9.765432` |
| Yaw | float | Full precision | `1.234567` |
| YawRate | float | Full precision | `0.012345` |
| PositionType | int | Integer, no decimal | `3` |

---

## 3. Implementation

### 3.1 Module: `src/csv_exporter.py`

```python
"""Write per-lap telemetry data to CSV files."""

import csv
import io
from pathlib import Path
from typing import Optional

from .ibt_parser import ParsedSession, ParsedLap, SessionInfo
from .variable_map import CSV_COLUMNS


def format_value(column: str, value) -> str:
    """Format a single value for CSV output."""
    if column in ("ABSActive", "DRSActive"):
        return "true" if value else "false"
    if column in ("Gear", "PositionType"):
        return str(int(value))
    if isinstance(value, float):
        # Use repr-style formatting to preserve full precision
        # but strip unnecessary trailing zeros
        return f"{value}"
    return str(value)


def write_lap_csv(lap: ParsedLap, output_path: Path) -> Path:
    """
    Write a single lap's telemetry to a CSV file.

    Args:
        lap: Parsed lap data with list of row dicts
        output_path: Full path for the output CSV file

    Returns:
        The path of the written file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")

        # Header row
        writer.writerow(CSV_COLUMNS)

        # Data rows
        for row in lap.rows:
            csv_row = [format_value(col, row.get(col, 0)) for col in CSV_COLUMNS]
            writer.writerow(csv_row)

    return output_path


def get_output_dir(session_info: SessionInfo, base_dir: Optional[Path] = None) -> Path:
    """
    Build the output directory path for a session.

    Format: {base_dir}/{TrackName}_{CarName}_{YYYY-MM-DD_HH-MM}/
    """
    if base_dir is None:
        base_dir = Path.home() / "Documents" / "iRacing" / "TelemetryCSV"

    # Sanitize folder name (remove chars invalid in Windows paths)
    def sanitize(name: str) -> str:
        invalid = '<>:"/\\|?*'
        for ch in invalid:
            name = name.replace(ch, "")
        return name.strip()

    folder_name = (
        f"{sanitize(session_info.track_name)}_"
        f"{sanitize(session_info.car_name)}_"
        f"{sanitize(session_info.session_date)}"
    )

    return base_dir / folder_name


def get_lap_filename(session_info: SessionInfo, lap: ParsedLap) -> str:
    """Generate filename for a lap CSV."""
    session_type = session_info.session_type.lower().replace(" ", "_")
    return f"{session_type}_lap_{lap.lap_number:02d}.csv"


def export_session(session: ParsedSession, base_dir: Optional[Path] = None) -> list[Path]:
    """
    Export all laps from a parsed session to CSV files.

    Args:
        session: Complete parsed session from ibt_parser
        base_dir: Base output directory (default: ~/Documents/iRacing/TelemetryCSV/)

    Returns:
        List of paths to written CSV files
    """
    output_dir = get_output_dir(session.session_info, base_dir)
    written_files = []

    for lap in session.laps:
        filename = get_lap_filename(session.session_info, lap)
        output_path = output_dir / filename
        write_lap_csv(lap, output_path)
        written_files.append(output_path)

    return written_files
```

### 3.2 End-to-End Pipeline

```python
def process_ibt_file(ibt_path: str | Path, output_dir: Optional[Path] = None) -> list[Path]:
    """
    Complete pipeline: IBT file → parse → CSV files.

    This is the main entry point used by the file watcher in Phase 3.
    """
    from .ibt_parser import parse_ibt

    session = parse_ibt(ibt_path)
    return export_session(session, output_dir)
```

### 3.3 CLI Entry Point

```python
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.csv_exporter <path_to_ibt_file> [output_dir]")
        sys.exit(1)

    ibt_path = sys.argv[1]
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    files = process_ibt_file(ibt_path, output_dir)
    print(f"Exported {len(files)} lap CSV files:")
    for f in files:
        print(f"  {f}")
```

---

## 4. Testing

### 4.1 Test File: `tests/test_csv_exporter.py`

```python
import pytest
import csv
from pathlib import Path
from src.csv_exporter import (
    format_value, write_lap_csv, get_output_dir, export_session
)
from src.ibt_parser import ParsedLap, ParsedSession, SessionInfo
from src.variable_map import CSV_COLUMNS


class TestFormatValue:
    def test_bool_true(self):
        assert format_value("ABSActive", True) == "true"

    def test_bool_false(self):
        assert format_value("DRSActive", False) == "false"

    def test_gear_int(self):
        assert format_value("Gear", 4) == "4"
        assert format_value("Gear", 4.0) == "4"

    def test_float_precision(self):
        result = format_value("Speed", 52.367892)
        assert "52.367892" in result

    def test_position_type_int(self):
        assert format_value("PositionType", 3) == "3"


class TestWriteLapCsv:
    def test_writes_correct_header(self, tmp_path):
        lap = ParsedLap(lap_number=1, rows=[
            {col: 0 for col in CSV_COLUMNS}
        ])
        out = tmp_path / "test.csv"
        write_lap_csv(lap, out)

        with open(out) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == CSV_COLUMNS

    def test_writes_correct_row_count(self, tmp_path):
        rows = [{col: 0 for col in CSV_COLUMNS} for _ in range(10)]
        lap = ParsedLap(lap_number=1, rows=rows)
        out = tmp_path / "test.csv"
        write_lap_csv(lap, out)

        with open(out) as f:
            lines = f.readlines()
            assert len(lines) == 11  # 1 header + 10 data rows


class TestOutputDir:
    def test_default_base_dir(self):
        info = SessionInfo(
            track_name="Spa",
            track_config=None,
            car_name="GT3",
            session_type="Race",
            session_date="2024-01-15",
            ibt_file_path="test.ibt",
        )
        result = get_output_dir(info)
        assert "TelemetryCSV" in str(result)
        assert "Spa" in str(result)

    def test_custom_base_dir(self, tmp_path):
        info = SessionInfo(
            track_name="Spa",
            track_config=None,
            car_name="GT3",
            session_type="Race",
            session_date="2024-01-15",
            ibt_file_path="test.ibt",
        )
        result = get_output_dir(info, tmp_path)
        assert str(result).startswith(str(tmp_path))
```

---

## 5. Acceptance Criteria

- [ ] `write_lap_csv()` produces CSV matching `OutputDataExample.csv` format exactly
- [ ] Header row has all 18 columns in correct order
- [ ] Boolean values render as lowercase `true`/`false`
- [ ] Integer columns (Gear, PositionType) have no decimal point
- [ ] Output folder structure follows `{track}_{car}_{date}/` convention
- [ ] `process_ibt_file()` runs end-to-end: IBT → CSV files on disk
- [ ] CLI works: `python -m src.csv_exporter file.ibt`
- [ ] All tests pass

---

## 6. What's Next

Phase 3 adds automatic file watching (detect new IBT files) and a system tray icon so the app runs in the background and processes sessions hands-free.
