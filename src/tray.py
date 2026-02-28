"""System tray icon and menu using pystray."""

import logging
import subprocess
import sys
from pathlib import Path

import pystray
from PIL import Image

from .config import get_asset_path

logger = logging.getLogger(__name__)


class TrayApp:
    """System tray application."""

    def __init__(self, config, on_quit, on_reprocess=None):
        self.config = config
        self._on_quit = on_quit
        self._on_reprocess = on_reprocess
        self._status = "Idle"
        self._icon = None

    def set_status(self, status: str):
        self._status = status
        if self._icon:
            self._icon.title = f"iRacing Telemetry - {status}"

    def _create_icon_image(self) -> Image.Image:
        icon_path = get_asset_path("assets/icon.ico")
        if icon_path.exists():
            return Image.open(icon_path)
        img = Image.new("RGB", (64, 64), color=(0, 120, 215))
        return img

    def _open_output_folder(self):
        folder = self.config.output_dir
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(folder)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                lambda _: f"Status: {self._status}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Output Folder", lambda: self._open_output_folder()),
            pystray.MenuItem("Reprocess All Files", lambda: self._reprocess()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self._quit()),
        )

    def _reprocess(self):
        logger.info("Reprocess all requested")
        if self._on_reprocess:
            self._on_reprocess()

    def _quit(self):
        if self._icon:
            self._icon.stop()
        self._on_quit()

    def run(self):
        self._icon = pystray.Icon(
            name="iracing-telemetry",
            icon=self._create_icon_image(),
            title=f"iRacing Telemetry - {self._status}",
            menu=self._build_menu(),
        )
        self._icon.run()
