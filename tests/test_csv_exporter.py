import pytest
import csv
from pathlib import Path
from src.csv_exporter import (
    format_value, write_lap_csv, get_output_dir, get_lap_filename, export_session
)
from src.ibt_parser import ParsedLap, ParsedSession, SessionInfo
from src.variable_map import CSV_COLUMNS


class TestFormatValue:
    def test_bool_true(self):
        assert format_value("ABSActive", True) == "true"

    def test_bool_false(self):
        assert format_value("DRSActive", False) == "false"

    def test_bool_truthy(self):
        assert format_value("ABSActive", 1) == "true"

    def test_bool_falsy(self):
        assert format_value("DRSActive", 0) == "false"

    def test_gear_int(self):
        assert format_value("Gear", 4) == "4"
        assert format_value("Gear", 4.0) == "4"

    def test_float_precision(self):
        result = format_value("Speed", 52.367892)
        assert "52.367892" in result

    def test_position_type_int(self):
        assert format_value("PositionType", 3) == "3"
        assert format_value("PositionType", 0) == "0"


def _make_session_info(**kwargs):
    defaults = dict(
        track_name="Spa",
        track_config=None,
        car_name="GT3",
        session_type="Race",
        session_date="2024-01-15",
        ibt_file_path="test.ibt",
    )
    defaults.update(kwargs)
    return SessionInfo(**defaults)


def _make_lap(lap_number=1, num_rows=10):
    rows = [{col: 0 for col in CSV_COLUMNS} for _ in range(num_rows)]
    return ParsedLap(lap_number=lap_number, rows=rows)


class TestWriteLapCsv:
    def test_writes_correct_header(self, tmp_path):
        lap = _make_lap()
        out = tmp_path / "test.csv"
        write_lap_csv(lap, out)

        with open(out) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == CSV_COLUMNS

    def test_writes_correct_row_count(self, tmp_path):
        lap = _make_lap(num_rows=10)
        out = tmp_path / "test.csv"
        write_lap_csv(lap, out)

        with open(out) as f:
            lines = f.readlines()
            assert len(lines) == 11  # 1 header + 10 data

    def test_creates_parent_dirs(self, tmp_path):
        lap = _make_lap()
        out = tmp_path / "sub" / "dir" / "test.csv"
        write_lap_csv(lap, out)
        assert out.exists()


class TestOutputDir:
    def test_default_base_dir(self):
        info = _make_session_info()
        result = get_output_dir(info)
        assert "TelemetryCSV" in str(result)
        assert "Spa" in str(result)

    def test_custom_base_dir(self, tmp_path):
        info = _make_session_info()
        result = get_output_dir(info, tmp_path)
        assert str(result).startswith(str(tmp_path))

    def test_sanitizes_special_chars(self, tmp_path):
        info = _make_session_info(track_name="Track:Name", car_name="Car<>Model")
        result = get_output_dir(info, tmp_path)
        assert ":" not in result.name
        assert "<" not in result.name


class TestLapFilename:
    def test_basic(self):
        info = _make_session_info(session_type="Race")
        lap = _make_lap(lap_number=3)
        assert get_lap_filename(info, lap) == "race_lap_03.csv"

    def test_practice(self):
        info = _make_session_info(session_type="Practice")
        lap = _make_lap(lap_number=1)
        assert get_lap_filename(info, lap) == "practice_lap_01.csv"

    def test_lone_qualify(self):
        info = _make_session_info(session_type="Lone Qualify")
        lap = _make_lap(lap_number=5)
        assert get_lap_filename(info, lap) == "lone_qualify_lap_05.csv"


class TestExportSession:
    def test_exports_all_laps(self, tmp_path):
        info = _make_session_info()
        laps = [_make_lap(lap_number=i) for i in range(1, 4)]
        session = ParsedSession(session_info=info, laps=laps)
        files = export_session(session, tmp_path)
        assert len(files) == 3
        for f in files:
            assert f.exists()
