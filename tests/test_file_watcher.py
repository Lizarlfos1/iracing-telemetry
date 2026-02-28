import pytest
import time
from pathlib import Path
from src.file_watcher import IBTHandler


class TestIBTHandler:
    def test_file_not_ready_immediately(self):
        processed = []
        handler = IBTHandler(on_file_ready=lambda p: processed.append(p))
        handler._update_pending("/fake/file.ibt")
        handler._check_pending()
        assert len(processed) == 0
        handler.stop()

    def test_ignores_non_ibt_on_created(self):
        from watchdog.events import FileCreatedEvent
        processed = []
        handler = IBTHandler(on_file_ready=lambda p: processed.append(p))
        event = FileCreatedEvent("/fake/file.txt")
        handler.on_created(event)
        assert len(handler._pending) == 0
        handler.stop()

    def test_accepts_ibt_on_created(self):
        from watchdog.events import FileCreatedEvent
        processed = []
        handler = IBTHandler(on_file_ready=lambda p: processed.append(p))
        event = FileCreatedEvent("/fake/file.ibt")
        handler.on_created(event)
        assert len(handler._pending) == 1
        handler.stop()

    def test_case_insensitive_extension(self):
        from watchdog.events import FileCreatedEvent
        processed = []
        handler = IBTHandler(on_file_ready=lambda p: processed.append(p))
        event = FileCreatedEvent("/fake/file.IBT")
        handler.on_created(event)
        assert len(handler._pending) == 1
        handler.stop()


class TestProcessedTracker:
    def test_mark_and_check(self, tmp_path):
        from src.config import ProcessedTracker
        log = tmp_path / ".processed.json"
        tracker = ProcessedTracker(log)

        fake_path = tmp_path / "test.ibt"
        fake_path.touch()

        assert not tracker.is_processed(fake_path)
        tracker.mark_processed(fake_path)
        assert tracker.is_processed(fake_path)

    def test_persists_to_disk(self, tmp_path):
        from src.config import ProcessedTracker
        log = tmp_path / ".processed.json"

        fake_path = tmp_path / "test.ibt"
        fake_path.touch()

        tracker1 = ProcessedTracker(log)
        tracker1.mark_processed(fake_path)

        tracker2 = ProcessedTracker(log)
        assert tracker2.is_processed(fake_path)

    def test_clear(self, tmp_path):
        from src.config import ProcessedTracker
        log = tmp_path / ".processed.json"

        fake_path = tmp_path / "test.ibt"
        fake_path.touch()

        tracker = ProcessedTracker(log)
        tracker.mark_processed(fake_path)
        tracker.clear()
        assert not tracker.is_processed(fake_path)
