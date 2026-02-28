"""Watch iRacing telemetry folder for new .ibt files."""
from __future__ import annotations

import time
import logging
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 10


class IBTHandler(FileSystemEventHandler):
    """Handle new/modified .ibt files with debouncing."""

    def __init__(self, on_file_ready):
        self._on_file_ready = on_file_ready
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._running = True
        self._start_checker()

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".ibt"):
            self._update_pending(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".ibt"):
            self._update_pending(event.src_path)

    def _update_pending(self, path: str):
        with self._lock:
            self._pending[path] = time.time()

    def _start_checker(self):
        if not self._running:
            return
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
        self._running = False
        if self._timer:
            self._timer.cancel()


class TelemetryWatcher:
    """Watches a directory for new IBT files and triggers processing."""

    def __init__(self, watch_dir: Path, on_file_ready):
        self.watch_dir = watch_dir
        self._handler = IBTHandler(on_file_ready)
        self._observer = Observer()

    def start(self):
        if not self.watch_dir.exists():
            logger.warning(f"Telemetry dir does not exist: {self.watch_dir}")
            return

        self._observer.schedule(self._handler, str(self.watch_dir), recursive=False)
        self._observer.start()
        logger.info(f"Watching: {self.watch_dir}")

    def stop(self):
        self._handler.stop()
        self._observer.stop()
        self._observer.join(timeout=5)
        logger.info("Watcher stopped")
