"""Write per-lap telemetry data to CSV files."""
from __future__ import annotations

import csv
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
        return f"{value}"
    return str(value)


def write_lap_csv(lap: ParsedLap, output_path: Path) -> Path:
    """Write a single lap's telemetry to a CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for row in lap.rows:
            csv_row = [format_value(col, row.get(col, 0)) for col in CSV_COLUMNS]
            writer.writerow(csv_row)

    return output_path


def get_output_dir(session_info: SessionInfo, base_dir: Optional[Path] = None) -> Path:
    """Build the output directory path for a session.
    Format: {base_dir}/{TrackName}_{CarName}_{YYYY-MM-DD_HH-MM}/
    """
    if base_dir is None:
        base_dir = Path.home() / "Documents" / "iRacing" / "TelemetryCSV"

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
    """Export all laps from a parsed session to CSV files."""
    output_dir = get_output_dir(session.session_info, base_dir)
    written_files = []

    for lap in session.laps:
        filename = get_lap_filename(session.session_info, lap)
        output_path = output_dir / filename
        write_lap_csv(lap, output_path)
        written_files.append(output_path)

    return written_files


def process_ibt_file(ibt_path: str | Path, output_dir: Optional[Path] = None) -> list[Path]:
    """Complete pipeline: IBT file -> parse -> CSV files."""
    from .ibt_parser import parse_ibt

    session = parse_ibt(ibt_path)
    return export_session(session, output_dir)


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
