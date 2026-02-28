"""Build script for creating the distributable EXE."""

import shutil
import subprocess
import sys
from pathlib import Path


def build():
    print("Building iRacing Telemetry Collector EXE...")

    # Clean previous builds
    for d in ["build", "dist"]:
        p = Path(d)
        if p.exists():
            shutil.rmtree(p)

    # Run PyInstaller
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "build.spec", "--clean"],
        capture_output=False,
    )

    if result.returncode == 0:
        exe = Path("dist/iRacingTelemetry.exe")
        if exe.exists():
            size_mb = exe.stat().st_size / (1024 * 1024)
            print(f"\nBuild successful!")
            print(f"  Output: {exe}")
            print(f"  Size:   {size_mb:.1f} MB")
        else:
            print("\nBuild completed but EXE not found at expected path.")
    else:
        print("\nBuild failed!")
        sys.exit(1)


if __name__ == "__main__":
    build()
