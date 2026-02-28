"""Entry point: starts file watcher + system tray."""

import logging
import sys
import threading
from pathlib import Path

from .config import Config, ProcessedTracker
from .csv_exporter import process_ibt_file
from .file_watcher import TelemetryWatcher


def setup_logging():
    log_dir = Path.home() / "Documents" / "iRacing" / "TelemetryCSV"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "telemetry_collector.log"

    handlers = [
        logging.FileHandler(log_file),
        logging.StreamHandler(),  # Always show logs in console (useful for debugging EXE)
    ]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    config = Config()
    tracker = ProcessedTracker(config.processed_log)

    tray = None  # Forward reference

    def on_file_ready(ibt_path: Path):
        if tracker.is_processed(ibt_path):
            logger.info(f"Already processed: {ibt_path.name}")
            return

        logger.info(f"Processing: {ibt_path.name}")
        if tray:
            tray.set_status(f"Processing {ibt_path.name}...")

        try:
            files = process_ibt_file(ibt_path, config.output_dir)
            tracker.mark_processed(ibt_path)
            logger.info(f"Exported {len(files)} CSVs from {ibt_path.name}")
        except Exception as e:
            logger.error(f"Failed to process {ibt_path.name}: {e}")

        if tray:
            tray.set_status("Watching")

    def initial_scan():
        if config.telemetry_dir.exists():
            for ibt_file in sorted(config.telemetry_dir.glob("*.ibt")):
                on_file_ready(ibt_file)

    def on_reprocess():
        tracker.clear()
        scan_thread = threading.Thread(target=initial_scan, daemon=True)
        scan_thread.start()

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

    tray = TrayApp(config, on_quit, on_reprocess=on_reprocess)
    tray.set_status("Watching")
    tray.run()  # Blocks until quit


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
        input("Press Enter to exit...")  # Keep console open so you can read the error
