# Phase 4: Packaging as Single EXE — Implementation Plan

---

## 1. Overview

Phase 4 packages the entire application into a single Windows `.exe` file using PyInstaller. The goal is a zero-dependency, download-and-run experience — no Python installation, no installer, no setup wizard.

At the end of this phase, we will have:

- A single `iRacingTelemetry.exe` file (~30-50MB)
- All dependencies bundled (pyirsdk, watchdog, pystray, Pillow)
- Tray icon asset embedded in the EXE
- Tested on a clean Windows machine with no Python installed

---

## 2. Dependencies

Add to `requirements.txt` (dev only):

```
# Packaging
pyinstaller>=6.0
```

---

## 3. PyInstaller Configuration

### 3.1 Spec File: `build.spec`

```python
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/icon.ico', 'assets'),
    ],
    hiddenimports=[
        'pystray._win32',    # pystray Windows backend
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',          # Not needed, saves space
        'unittest',
        'email',
        'html',
        'http',
        'xml',
        'pydoc',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='iRacingTelemetry',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,              # Compress with UPX if available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window — tray app only
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon='assets/icon.ico',
)
```

### 3.2 Key Settings

| Setting | Value | Why |
|---------|-------|-----|
| `console=False` | No terminal window | App runs as system tray only |
| `onefile` mode | Single EXE | Via `a.binaries + a.datas` in EXE() |
| `upx=True` | Compress binaries | Smaller download size |
| `icon` | Custom `.ico` | Branded EXE icon |
| `excludes` | tkinter, unittest, etc. | Reduce bundle size |

---

## 4. Build Process

### 4.1 Build Command

```bash
# Install PyInstaller
pip install pyinstaller

# Build the EXE
pyinstaller build.spec --clean

# Output: dist/iRacingTelemetry.exe
```

### 4.2 Build Script: `build.py`

```python
"""Build script for creating the distributable EXE."""

import subprocess
import sys
from pathlib import Path


def build():
    print("Building iRacing Telemetry Collector EXE...")

    # Clean previous builds
    for d in ["build", "dist"]:
        p = Path(d)
        if p.exists():
            import shutil
            shutil.rmtree(p)

    # Run PyInstaller
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "build.spec", "--clean"],
        capture_output=False,
    )

    if result.returncode == 0:
        exe = Path("dist/iRacingTelemetry.exe")
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"\nBuild successful!")
        print(f"  Output: {exe}")
        print(f"  Size:   {size_mb:.1f} MB")
    else:
        print("\nBuild failed!")
        sys.exit(1)


if __name__ == "__main__":
    build()
```

---

## 5. Asset Path Handling

PyInstaller bundles assets into a temp directory at runtime. The code must handle this:

```python
# In src/config.py or wherever assets are loaded

import sys
from pathlib import Path


def get_asset_path(relative_path: str) -> Path:
    """Get path to bundled asset, works in both dev and PyInstaller mode."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        base = Path(sys._MEIPASS)
    else:
        # Running as normal Python script
        base = Path(__file__).parent.parent

    return base / relative_path
```

Update `tray.py` to use this:

```python
def _create_icon_image(self) -> Image.Image:
    icon_path = get_asset_path("assets/icon.ico")
    if icon_path.exists():
        return Image.open(icon_path)
    # Fallback
    return Image.new("RGB", (64, 64), color=(0, 120, 215))
```

---

## 6. Logging in Packaged Mode

When running as an EXE (no console), logs need to go to a file:

```python
# In src/main.py

import sys

def setup_logging():
    log_dir = Path.home() / "Documents" / "iRacing" / "TelemetryCSV"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "telemetry_collector.log"

    handlers = [logging.FileHandler(log_file)]

    # Also log to console if not frozen (dev mode)
    if not getattr(sys, 'frozen', False):
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
```

---

## 7. Testing the EXE

### 7.1 Checklist

- [ ] EXE starts without errors on a clean Windows machine (no Python)
- [ ] System tray icon appears
- [ ] Right-click menu works (Open folder, Quit)
- [ ] Dropping an `.ibt` file into the telemetry folder triggers processing
- [ ] CSV files appear in the output folder
- [ ] App survives running for extended periods without memory leaks
- [ ] Quitting from tray cleanly exits the process
- [ ] Log file is created in the output directory

### 7.2 Test on Clean Machine

Use a Windows VM or clean machine to verify:
1. Download `iRacingTelemetry.exe`
2. Double-click to run
3. Tray icon appears
4. Copy an `.ibt` file to `~/Documents/iRacing/Telemetry/`
5. CSV files appear in `~/Documents/iRacing/TelemetryCSV/`

---

## 8. EXE Size Optimization

Expected size: ~30-50MB. If too large:

1. **UPX compression**: Already enabled in spec (`upx=True`)
2. **Exclude unused stdlib modules**: Already excluding tkinter, unittest, etc.
3. **Strip debug symbols**: Add `strip=True` in spec (may cause issues on Windows)
4. **Use `--onefile`**: Already configured

The Electron alternative would be 150MB+. A 30-50MB Python EXE is very reasonable.

---

## 9. Acceptance Criteria

- [ ] `pyinstaller build.spec` produces a single `iRacingTelemetry.exe`
- [ ] EXE runs on Windows without Python installed
- [ ] System tray icon and menu work correctly
- [ ] File watcher + CSV export work end-to-end from the EXE
- [ ] Log file is written to the output directory
- [ ] Bundle size is under 60MB
- [ ] No console window appears

---

## 10. Future Enhancements (Post-MVP)

- **Auto-start with Windows**: Add to Windows startup registry
- **Auto-update**: Check GitHub releases for newer versions
- **Notifications**: Toast notification when new CSVs are exported
- **Code signing**: Sign the EXE to avoid antivirus false positives
