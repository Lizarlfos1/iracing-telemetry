"""Application configuration and default paths."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Default paths (Windows iRacing standard locations)
DEFAULT_TELEMETRY_DIR = Path.home() / "Documents" / "iRacing" / "Telemetry"
DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "iRacing" / "TelemetryCSV"
PROCESSED_LOG_FILE = DEFAULT_OUTPUT_DIR / ".processed.json"
SETTINGS_FILE = DEFAULT_OUTPUT_DIR / ".settings.json"


def get_asset_path(relative_path: str) -> Path:
    """Get path to bundled asset, works in both dev and PyInstaller mode."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent.parent
    return base / relative_path


class Config:
    """Runtime configuration, loaded from settings file or defaults."""

    def __init__(self):
        self.telemetry_dir: Path = DEFAULT_TELEMETRY_DIR
        self.output_dir: Path = DEFAULT_OUTPUT_DIR
        self.processed_log: Path = PROCESSED_LOG_FILE
        self._load()

    def _load(self):
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text())
                if "telemetry_dir" in data:
                    self.telemetry_dir = Path(data["telemetry_dir"])
                if "output_dir" in data:
                    self.output_dir = Path(data["output_dir"])
            except Exception as e:
                logger.warning(f"Could not load settings: {e}")

    def save(self):
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "telemetry_dir": str(self.telemetry_dir),
            "output_dir": str(self.output_dir),
        }
        SETTINGS_FILE.write_text(json.dumps(data, indent=2))


class ProcessedTracker:
    """Tracks processed IBT files using a JSON log file."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self._processed: set[str] = set()
        self._load()

    def _load(self):
        if self.log_path.exists():
            try:
                data = json.loads(self.log_path.read_text())
                self._processed = set(data.get("files", []))
            except Exception:
                self._processed = set()

    def _save(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"files": sorted(self._processed)}
        self.log_path.write_text(json.dumps(data, indent=2))

    def is_processed(self, ibt_path: Path) -> bool:
        return str(ibt_path.resolve()) in self._processed

    def mark_processed(self, ibt_path: Path):
        self._processed.add(str(ibt_path.resolve()))
        self._save()

    def clear(self):
        self._processed.clear()
        self._save()
