# Phase 3: File Watcher & System Tray — Implementation Plan

---

## 1. Overview

Phase 3 turns the parser + exporter into a background service that automatically detects and processes new iRacing telemetry files. It adds a system tray icon so the user can see status, access the output folder, and control the app.

At the end of this phase, we will have:

- A `watchdog`-based file watcher monitoring the iRacing telemetry folder
- Automatic processing: new `.ibt` file detected → parse → CSV export
- Debouncing to handle IBT files being written continuously during sessions
- A `.processed` log to avoid re-processing the same file
- A system tray icon with status and menu (pystray)
- First-run historical import of existing IBT files
- A `main.py` entry point that ties everything together

---

## 2. Dependencies

Add to `requirements.txt`:

```
# File watching
watchdog>=3.0

# System tray
pystray>=0.19
Pillow>=9.0    # Required by pystray for icon rendering
```

---

## 3. Configuration

### 3.1 Module: `src/config.py`

```python
"""Application configuration and default paths."""

from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

# Default paths (Windows iRacing standard locations)
DEFAULT_TELEMETRY_DIR = Path.home() / "Documents" / "iRacing" / "Telemetry"
DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "iRacing" / "TelemetryCSV"
PROCESSED_LOG_FILE = DEFAULT_OUTPUT_DIR / ".processed.json"

# Settings file (persists user preferences)
SETTINGS_FILE = Path.home() / "Documents" / "iRacing" / "TelemetryCSV" / ".settings.json"


class Config:
    """Runtime configuration, loaded from settings file or defaults."""

    def __init__(self):
        self.telemetry_dir: Path = DEFAULT_TELEMETRY_DIR
        self.output_dir: Path = DEFAULT_OUTPUT_DIR
        self.processed_log: Path = PROCESSED_LOG_FILE
        self._load()

    def _load(self):
        """Load settings from disk if they exist."""
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
        """Persist current settings to disk."""
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "telemetry_dir": str(self.telemetry_dir),
            "output_dir": str(self.output_dir),
        }
        SETTINGS_FILE.write_text(json.dumps(data, indent=2))
```

---

## 4. Processed File Tracking

Instead of a database, we use a simple JSON file to track which IBT files have been processed.

```python
"""Track which IBT files have already been processed."""

import json
from pathlib import Path
from typing import set


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
```

---

## 5. File Watcher

### 5.1 Module: `src/file_watcher.py`

```python
"""Watch iRacing telemetry folder for new .ibt files."""

import time
import logging
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

logger = logging.getLogger(__name__)

# IBT files are written continuously during a session.
# Wait this long after last modification before processing.
DEBOUNCE_SECONDS = 10


class IBTHandler(FileSystemEventHandler):
    """Handle new/modified .ibt files with debouncing."""

    def __init__(self, on_file_ready):
        self._on_file_ready = on_file_ready
        self._pending: dict[str, float] = {}  # path → last_modified_time
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._start_checker()

    def on_created(self, event):
        if event.src_path.lower().endswith(".ibt"):
            self._update_pending(event.src_path)

    def on_modified(self, event):
        if event.src_path.lower().endswith(".ibt"):
            self._update_pending(event.src_path)

    def _update_pending(self, path: str):
        with self._lock:
            self._pending[path] = time.time()

    def _start_checker(self):
        """Periodically check if any pending files are ready."""
        self._check_pending()
        self._timer = threading.Timer(DEBOUNCE_SECONDS / 2, self._start_checker)
        self._timer.daemon = True
        self._timer.start()

    def _check_pending(self):
        now = time.time()
        ready = []
        with self._lock:
            for path, last_mod in list(self._pending.items()):
                if now - last_mod >= DEBOUNCE_SECONDS:
                    ready.append(path)
                    del self._pending[path]

        for path in ready:
            try:
                self._on_file_ready(Path(path))
            except Exception as e:
                logger.error(f"Error processing {path}: {e}")

    def stop(self):
        if self._timer:
            self._timer.cancel()


class TelemetryWatcher:
    """Watches a directory for new IBT files and triggers processing."""

    def __init__(self, watch_dir: Path, on_file_ready):
        self.watch_dir = watch_dir
        self._handler = IBTHandler(on_file_ready)
        self._observer = Observer()

    def start(self):
        """Start watching the telemetry directory."""
        if not self.watch_dir.exists():
            logger.warning(f"Telemetry dir does not exist: {self.watch_dir}")
            return

        self._observer.schedule(self._handler, str(self.watch_dir), recursive=False)
        self._observer.start()
        logger.info(f"Watching: {self.watch_dir}")

    def stop(self):
        """Stop the file watcher."""
        self._handler.stop()
        self._observer.stop()
        self._observer.join(timeout=5)
        logger.info("Watcher stopped")
```

---

## 6. System Tray

### 6.1 Module: `src/tray.py`

```python
"""System tray icon and menu using pystray."""

import logging
import subprocess
import sys
from pathlib import Path

import pystray
from PIL import Image

logger = logging.getLogger(__name__)


class TrayApp:
    """System tray application."""

    def __init__(self, config, on_quit):
        self.config = config
        self._on_quit = on_quit
        self._status = "Idle"
        self._icon = None

    def set_status(self, status: str):
        """Update the tray tooltip status text."""
        self._status = status
        if self._icon:
            self._icon.title = f"iRacing Telemetry - {status}"

    def _create_icon_image(self) -> Image.Image:
        """Create or load the tray icon."""
        icon_path = Path(__file__).parent.parent / "assets" / "icon.ico"
        if icon_path.exists():
            return Image.open(icon_path)
        # Fallback: generate a simple colored square
        img = Image.new("RGB", (64, 64), color=(0, 120, 215))
        return img

    def _open_output_folder(self):
        """Open the CSV output folder in the file explorer."""
        folder = self.config.output_dir
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(folder)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                lambda _: f"Status: {self._status}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Output Folder", lambda: self._open_output_folder()),
            pystray.MenuItem("Reprocess All Files", lambda: self._reprocess_all()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self._quit()),
        )

    def _reprocess_all(self):
        """Signal to reprocess all IBT files (clears processed log)."""
        logger.info("Reprocess all requested")
        # Clear the processed log so everything gets re-exported
        if self.config.processed_log.exists():
            self.config.processed_log.unlink()

    def _quit(self):
        if self._icon:
            self._icon.stop()
        self._on_quit()

    def run(self):
        """Start the system tray icon (blocks the calling thread)."""
        self._icon = pystray.Icon(
            name="iracing-telemetry",
            icon=self._create_icon_image(),
            title=f"iRacing Telemetry - {self._status}",
            menu=self._build_menu(),
        )
        self._icon.run()
```

---

## 7. Main Entry Point

### 7.1 Module: `src/main.py`

```python
"""Entry point: starts file watcher + system tray."""

import logging
import threading
from pathlib import Path

from .config import Config
from .csv_exporter import process_ibt_file
from .file_watcher import TelemetryWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    config = Config()
    tracker = ProcessedTracker(config.processed_log)

    def on_file_ready(ibt_path: Path):
        """Called when a new/modified IBT file is ready to process."""
        if tracker.is_processed(ibt_path):
            logger.info(f"Already processed: {ibt_path.name}")
            return

        logger.info(f"Processing: {ibt_path.name}")
        tray.set_status(f"Processing {ibt_path.name}...")

        try:
            files = process_ibt_file(ibt_path, config.output_dir)
            tracker.mark_processed(ibt_path)
            logger.info(f"Exported {len(files)} CSVs from {ibt_path.name}")
        except Exception as e:
            logger.error(f"Failed to process {ibt_path.name}: {e}")

        tray.set_status("Watching")

    # First-run: process any existing IBT files
    def initial_scan():
        if config.telemetry_dir.exists():
            for ibt_file in sorted(config.telemetry_dir.glob("*.ibt")):
                on_file_ready(ibt_file)

    # Start file watcher in background thread
    watcher = TelemetryWatcher(config.telemetry_dir, on_file_ready)
    watcher.start()

    # Run initial scan in background
    scan_thread = threading.Thread(target=initial_scan, daemon=True)
    scan_thread.start()

    # System tray runs on the main thread (required by pystray)
    from .tray import TrayApp

    def on_quit():
        watcher.stop()
        logger.info("Application exiting")

    tray = TrayApp(config, on_quit)
    tray.set_status("Watching")
    tray.run()  # Blocks until quit


if __name__ == "__main__":
    main()
```

---

## 8. Testing

```python
# tests/test_file_watcher.py

import pytest
import time
from pathlib import Path
from src.file_watcher import IBTHandler


class TestDebouncing:
    def test_file_not_ready_immediately(self):
        """File should not be processed until debounce period elapses."""
        processed = []
        handler = IBTHandler(on_file_ready=lambda p: processed.append(p))

        # Simulate file creation event
        handler._update_pending("/fake/file.ibt")

        # Should not be processed immediately
        handler._check_pending()
        assert len(processed) == 0
        handler.stop()

    def test_ignores_non_ibt_files(self):
        """Handler should ignore non-.ibt files."""
        from watchdog.events import FileCreatedEvent

        processed = []
        handler = IBTHandler(on_file_ready=lambda p: processed.append(p))

        event = FileCreatedEvent("/fake/file.txt")
        handler.on_created(event)

        assert len(handler._pending) == 0
        handler.stop()
```

---

## 9. Acceptance Criteria

- [ ] File watcher detects new `.ibt` files in the telemetry folder
- [ ] Debouncing prevents processing files still being written
- [ ] Already-processed files are skipped
- [ ] System tray icon appears with correct menu items
- [ ] "Open Output Folder" opens the CSV output directory
- [ ] First-run scans and processes all existing IBT files
- [ ] `main.py` starts cleanly and runs until user quits from tray
- [ ] Graceful shutdown when user clicks Quit

---

## 10. What's Next

Phase 4 packages everything into a single `.exe` with PyInstaller.
