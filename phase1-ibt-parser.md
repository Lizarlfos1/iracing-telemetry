# Phase 1: Core IBT Parser — Implementation Plan

---

## 1. Overview

Phase 1 builds the core of the iRacing Telemetry Collector: a Python module that reads iRacing `.ibt` telemetry files, extracts session metadata and per-tick telemetry data for 18 required variables, and splits the data into individual laps — all in memory.

At the end of this phase, we will have:

- A working IBT parser that opens any `.ibt` file and extracts all 18 CSV-column variables
- Session metadata extraction from the embedded YAML header (track, car, date, session type)
- Lap-splitting logic that segments continuous 60 Hz telemetry into discrete laps
- Structured in-memory output: session info + list of laps (each lap = list of row dicts)
- A CLI test command: `python -m src.ibt_parser path/to/file.ibt`
- A test suite validating every component

**No database. No CSV writing. No file watching.** Just pure parsing logic.

---

## 2. Prerequisites & Setup

### 2.1 Python Environment

```bash
cd iracing-telemetry
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (macOS/Linux — for development only, target is Windows)
source .venv/bin/activate
```

### 2.2 Dependencies

Create `requirements.txt`:

```
# Core IBT parsing
pyirsdk>=1.3.5

# YAML parsing (pyirsdk peer dependency)
PyYAML>=5.3

# Testing
pytest>=7.0
```

No SQLAlchemy, no FastAPI, no aiosqlite — those are gone.

---

## 3. Variable Mapping

### 3.1 SDK → CSV Column Map

Create `src/variable_map.py`:

```python
"""Maps iRacing SDK variable names to output CSV column names."""

# Ordered list of (sdk_variable_name, csv_column_name, transform_function)
# Order matches the required CSV column order from OutputDataExample.csv

VARIABLE_MAP = [
    ("Speed",              "Speed",              None),
    ("LapDistPct",         "LapDistPct",         None),
    ("Lat",                "Lat",                None),
    ("Lon",                "Lon",                None),
    ("Brake",              "Brake",              None),
    ("Throttle",           "Throttle",           None),
    ("RPM",                "RPM",                None),
    ("SteeringWheelAngle", "SteeringWheelAngle", None),
    ("Gear",               "Gear",               None),
    ("Clutch",             "Clutch",             None),
    ("BrakeABSactive",     "ABSActive",          lambda v: bool(v)),
    ("DRS_Status",         "DRSActive",          lambda v: v == 3),
    ("LatAccel",           "LatAccel",           None),
    ("LongAccel",          "LongAccel",          None),
    ("VertAccel",          "VertAccel",          None),
    ("Yaw",                "Yaw",                None),
    ("YawRate",            "YawRate",            None),
]

# CSV column headers in exact order
CSV_COLUMNS = [col for _, col, _ in VARIABLE_MAP] + ["PositionType"]
```

### 3.2 Special Cases

- **ABSActive**: SDK gives `BrakeABSactive` as a bool/int. Map to Python `bool`.
- **DRSActive**: SDK gives `DRS_Status` as int (0=off, 3=on). Map `== 3` to `bool`.
- **PositionType**: Not a direct SDK variable — derived from session YAML. Added separately.

---

## 4. IBT Parser Implementation

### 4.1 Module: `src/ibt_parser.py`

```python
"""Parse iRacing .ibt telemetry files into structured lap data."""

import irsdk
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from .variable_map import VARIABLE_MAP


@dataclass
class SessionInfo:
    """Metadata extracted from the IBT file's YAML header."""
    track_name: str
    track_config: Optional[str]
    car_name: str
    session_type: str       # "Practice", "Qualify", "Race"
    session_date: str       # ISO format string
    ibt_file_path: str


@dataclass
class ParsedLap:
    """A single lap's worth of telemetry data."""
    lap_number: int
    rows: list[dict]        # Each dict has all 18 CSV column keys
    lap_time_seconds: Optional[float] = None


@dataclass
class ParsedSession:
    """Complete parsed result from one IBT file."""
    session_info: SessionInfo
    laps: list[ParsedLap] = field(default_factory=list)


def parse_ibt(file_path: str | Path) -> ParsedSession:
    """
    Parse an IBT file and return structured session + lap data.

    Steps:
    1. Open IBT file with pyirsdk
    2. Extract session YAML metadata
    3. Iterate all telemetry ticks at 60Hz
    4. Extract the 18 required variables per tick
    5. Split into laps using LapDistPct rollover
    6. Return ParsedSession with list of ParsedLaps
    """
    file_path = Path(file_path)
    ibt = irsdk.IBT()
    ibt.open(str(file_path))

    # 1. Extract session metadata from YAML header
    session_info = _extract_session_info(ibt, file_path)

    # 2. Read all telemetry ticks
    all_rows = _read_all_ticks(ibt)

    # 3. Split into laps
    laps = _split_into_laps(all_rows)

    ibt.close()

    return ParsedSession(session_info=session_info, laps=laps)
```

### 4.2 Session Metadata Extraction

```python
def _extract_session_info(ibt: irsdk.IBT, file_path: Path) -> SessionInfo:
    """Extract session metadata from IBT YAML header."""
    yaml_data = ibt.session_info

    # Navigate the YAML structure
    weekend_info = yaml_data.get("WeekendInfo", {})
    session_info_list = yaml_data.get("SessionInfo", {}).get("Sessions", [])

    # Determine session type from the sessions list
    # Use the last session in the file (typically the main event)
    session_type = "Unknown"
    if session_info_list:
        last_session = session_info_list[-1]
        session_type = last_session.get("SessionName", "Unknown")

    driver_info = yaml_data.get("DriverInfo", {})
    drivers = driver_info.get("Drivers", [{}])
    car_name = drivers[0].get("CarScreenName", "Unknown") if drivers else "Unknown"

    return SessionInfo(
        track_name=weekend_info.get("TrackDisplayName", "Unknown"),
        track_config=weekend_info.get("TrackConfigName", None),
        car_name=car_name,
        session_type=session_type,
        session_date=weekend_info.get("SessionDate", ""),  # Will need formatting
        ibt_file_path=str(file_path),
    )
```

### 4.3 Telemetry Tick Reading

```python
def _read_all_ticks(ibt: irsdk.IBT) -> list[dict]:
    """Read all telemetry ticks and extract the 18 required variables."""
    rows = []

    while ibt.get_next():
        row = {}
        for sdk_var, csv_col, transform in VARIABLE_MAP:
            value = ibt.get(sdk_var)
            if value is None:
                value = 0  # Default for missing variables
            if transform is not None:
                value = transform(value)
            row[csv_col] = value

        # PositionType: derive from session info or use default
        # In race sessions this comes from session YAML; default to 0
        row["PositionType"] = 0  # TODO: derive from session context

        rows.append(row)

    return rows
```

### 4.4 Lap Splitting

```python
LAP_DIST_ROLLOVER_THRESHOLD = 0.5  # LapDistPct drops from ~1.0 to ~0.0


def _split_into_laps(rows: list[dict]) -> list[ParsedLap]:
    """
    Split continuous telemetry into discrete laps.

    Detection: When LapDistPct drops by more than the threshold
    (e.g., from 0.98 to 0.01), a new lap has started.
    """
    if not rows:
        return []

    laps = []
    current_lap_rows = []
    lap_number = 1
    prev_dist = 0.0

    for row in rows:
        dist = row.get("LapDistPct", 0.0)

        # Detect lap boundary: large drop in LapDistPct
        if prev_dist - dist > LAP_DIST_ROLLOVER_THRESHOLD and current_lap_rows:
            laps.append(ParsedLap(
                lap_number=lap_number,
                rows=current_lap_rows,
            ))
            lap_number += 1
            current_lap_rows = []

        current_lap_rows.append(row)
        prev_dist = dist

    # Don't forget the last (possibly incomplete) lap
    if current_lap_rows:
        laps.append(ParsedLap(
            lap_number=lap_number,
            rows=current_lap_rows,
        ))

    return laps
```

---

## 5. CLI Test Entry Point

Add to `src/ibt_parser.py`:

```python
if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python -m src.ibt_parser <path_to_ibt_file>")
        sys.exit(1)

    result = parse_ibt(sys.argv[1])
    print(f"Track: {result.session_info.track_name}")
    print(f"Car: {result.session_info.car_name}")
    print(f"Session: {result.session_info.session_type}")
    print(f"Laps found: {len(result.laps)}")
    for lap in result.laps:
        print(f"  Lap {lap.lap_number}: {len(lap.rows)} ticks ({len(lap.rows)/60:.1f}s)")
```

---

## 6. Testing

### 6.1 Test File: `tests/test_ibt_parser.py`

```python
import pytest
from src.ibt_parser import parse_ibt, _split_into_laps, ParsedLap
from src.variable_map import CSV_COLUMNS


class TestLapSplitting:
    """Test lap boundary detection logic."""

    def test_single_lap(self):
        """Monotonically increasing LapDistPct = 1 lap."""
        rows = [{"LapDistPct": i / 100} for i in range(100)]
        laps = _split_into_laps(rows)
        assert len(laps) == 1
        assert laps[0].lap_number == 1
        assert len(laps[0].rows) == 100

    def test_two_laps(self):
        """LapDistPct rollover at midpoint = 2 laps."""
        rows = (
            [{"LapDistPct": i / 50} for i in range(50)] +  # 0.0 → 0.98
            [{"LapDistPct": i / 50} for i in range(50)]     # 0.0 → 0.98
        )
        laps = _split_into_laps(rows)
        assert len(laps) == 2
        assert laps[0].lap_number == 1
        assert laps[1].lap_number == 2

    def test_empty_input(self):
        """No rows = no laps."""
        assert _split_into_laps([]) == []


class TestVariableMap:
    """Verify CSV column order and completeness."""

    def test_column_count(self):
        assert len(CSV_COLUMNS) == 18

    def test_column_order(self):
        expected = [
            "Speed", "LapDistPct", "Lat", "Lon", "Brake", "Throttle",
            "RPM", "SteeringWheelAngle", "Gear", "Clutch", "ABSActive",
            "DRSActive", "LatAccel", "LongAccel", "VertAccel", "Yaw",
            "YawRate", "PositionType",
        ]
        assert CSV_COLUMNS == expected
```

---

## 7. Acceptance Criteria

- [ ] `parse_ibt("path/to/file.ibt")` returns a `ParsedSession` with correct metadata
- [ ] All 18 CSV columns are extracted per tick
- [ ] Laps are correctly split at `LapDistPct` rollover boundaries
- [ ] Variable name mapping works (`BrakeABSactive` → `ABSActive`, `DRS_Status` → `DRSActive` bool)
- [ ] CLI prints session summary when run directly
- [ ] All tests pass
- [ ] No database dependency — everything is in-memory data structures

---

## 8. What's Next

Phase 2 takes the `ParsedSession` output from this phase and writes per-lap CSV files to disk, matching the exact format of `OutputDataExample.csv`.
