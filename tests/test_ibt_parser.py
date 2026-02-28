import pytest
from src.ibt_parser import _split_into_laps, ParsedLap
from src.variable_map import CSV_COLUMNS


class TestLapSplitting:
    def test_single_lap(self):
        rows = [{"LapDistPct": i / 100} for i in range(100)]
        laps = _split_into_laps(rows)
        assert len(laps) == 1
        assert laps[0].lap_number == 1
        assert len(laps[0].rows) == 100

    def test_two_laps(self):
        rows = (
            [{"LapDistPct": i / 50} for i in range(50)] +
            [{"LapDistPct": i / 50} for i in range(50)]
        )
        laps = _split_into_laps(rows)
        assert len(laps) == 2
        assert laps[0].lap_number == 1
        assert laps[1].lap_number == 2

    def test_three_laps(self):
        rows = []
        for lap in range(3):
            rows.extend([{"LapDistPct": i / 50} for i in range(50)])
        laps = _split_into_laps(rows)
        assert len(laps) == 3

    def test_empty_input(self):
        assert _split_into_laps([]) == []

    def test_partial_lap(self):
        rows = [{"LapDistPct": i / 200} for i in range(50)]
        laps = _split_into_laps(rows)
        assert len(laps) == 1


class TestVariableMap:
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
