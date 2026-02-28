"""IBT file parser for iRacing telemetry data.

Reads .ibt telemetry files using pyirsdk, extracts session metadata
and telemetry variables, and splits the data into per-lap records.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import irsdk

from .variable_map import VARIABLE_MAP

# When LapDistPct drops by more than this threshold between consecutive
# ticks, we treat it as a lap boundary (rollover from ~1.0 to ~0.0).
LAP_DIST_ROLLOVER_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SessionInfo:
    """Metadata extracted from the IBT session YAML header."""
    track_name: str
    track_config: str
    car_name: str
    session_type: str
    session_date: str
    ibt_file_path: str


@dataclass
class ParsedLap:
    """A single lap of telemetry rows."""
    lap_number: int
    rows: list[dict] = field(default_factory=list)
    lap_time_seconds: Optional[float] = None


@dataclass
class ParsedSession:
    """Complete parsed result: session metadata + list of laps."""
    session_info: SessionInfo
    laps: list[ParsedLap] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_session_info(ibt: irsdk.IRSDK, file_path: str) -> SessionInfo:
    """Extract session metadata from the IBT YAML header.

    Uses:
      - WeekendInfo for track name, track config, and date.
      - DriverInfo.Drivers[0].CarScreenName for the car.
      - SessionInfo.Sessions[-1].SessionName for the session type.
    """
    weekend = ibt["WeekendInfo"]
    track_name = weekend.get("TrackName", "")
    track_config = weekend.get("TrackConfigName", "")
    session_date = weekend.get("WeekendOptions", {}).get("Date", "")

    drivers = ibt["DriverInfo"]["Drivers"]
    car_name = drivers[0].get("CarScreenName", "") if drivers else ""

    sessions = ibt["SessionInfo"]["Sessions"]
    session_type = sessions[-1].get("SessionName", "") if sessions else ""

    return SessionInfo(
        track_name=track_name,
        track_config=track_config,
        car_name=car_name,
        session_type=session_type,
        session_date=session_date,
        ibt_file_path=str(file_path),
    )


def _read_all_ticks(ibt: irsdk.IRSDK) -> list[dict]:
    """Iterate over every telemetry tick and extract the mapped variables.

    Each row is a dict keyed by CSV column name.  The ``PositionType``
    column is hard-coded to ``0`` for every tick.
    """
    rows: list[dict] = []

    while ibt.get_next():
        row: dict = {}
        for sdk_name, csv_name, transform in VARIABLE_MAP:
            value = ibt[sdk_name]
            if transform is not None and value is not None:
                value = transform(value)
            row[csv_name] = value
        row["PositionType"] = 0
        rows.append(row)

    return rows


def _split_into_laps(rows: list[dict]) -> list[ParsedLap]:
    """Split a flat list of telemetry rows into per-lap segments.

    A new lap begins whenever ``LapDistPct`` drops by more than
    ``LAP_DIST_ROLLOVER_THRESHOLD`` between consecutive ticks (i.e. the
    car crosses the start/finish line and the value rolls over from
    ~1.0 back to ~0.0).
    """
    if not rows:
        return []

    laps: list[ParsedLap] = []
    current_rows: list[dict] = [rows[0]]
    prev_dist = rows[0]["LapDistPct"]

    for row in rows[1:]:
        cur_dist = row["LapDistPct"]
        if prev_dist - cur_dist > LAP_DIST_ROLLOVER_THRESHOLD:
            # Lap boundary detected
            laps.append(ParsedLap(lap_number=len(laps) + 1, rows=current_rows))
            current_rows = []
        current_rows.append(row)
        prev_dist = cur_dist

    # Append the final (possibly partial) lap
    if current_rows:
        laps.append(ParsedLap(lap_number=len(laps) + 1, rows=current_rows))

    return laps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_ibt(file_path: str) -> ParsedSession:
    """Open an IBT file and return a fully parsed session.

    Parameters
    ----------
    file_path:
        Path to the ``.ibt`` telemetry file.

    Returns
    -------
    ParsedSession
        Session metadata together with a list of ``ParsedLap`` objects.
    """
    ibt = irsdk.IRSDK()
    ibt.startup(test_file=str(file_path))

    try:
        session_info = _extract_session_info(ibt, file_path)
        rows = _read_all_ticks(ibt)
        laps = _split_into_laps(rows)
    finally:
        ibt.shutdown()

    return ParsedSession(session_info=session_info, laps=laps)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.ibt_parser <path_to_ibt_file>")
        sys.exit(1)

    ibt_path = Path(sys.argv[1])
    if not ibt_path.exists():
        print(f"File not found: {ibt_path}")
        sys.exit(1)

    result = parse_ibt(str(ibt_path))
    info = result.session_info

    print("=== Session Summary ===")
    print(f"  Track:    {info.track_name} ({info.track_config})")
    print(f"  Car:      {info.car_name}")
    print(f"  Session:  {info.session_type}")
    print(f"  Date:     {info.session_date}")
    print(f"  IBT file: {info.ibt_file_path}")
    print(f"  Laps:     {len(result.laps)}")
    for lap in result.laps:
        tick_count = len(lap.rows)
        print(f"    Lap {lap.lap_number}: {tick_count} ticks")
