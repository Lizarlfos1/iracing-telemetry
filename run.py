"""Top-level entry point for PyInstaller and direct execution."""

import logging

try:
    from src.main import main
    main()
except Exception as e:
    logging.exception(f"Fatal error: {e}")
    input("Press Enter to exit...")
