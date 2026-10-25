"""Where Shiori's files are, whether it runs from source (python main.py) or as Shiori.exe.

  BUNDLE    read-only files packed into the app (web/bar.html)
  APP_DIR   the folder Shiori.exe (or main.py) is in; the Chrome extension sits here
  DATA      your parks and the log. From source: ./data. As Shiori.exe: %LOCALAPPDATA%\\Shiori,
            because an installed app can't write next to itself. STAGE_DATA overrides both (tests).
"""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)  # True inside Shiori.exe (PyInstaller sets it)
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent

if os.environ.get("STAGE_DATA"):
    DATA = Path(os.environ["STAGE_DATA"])  # tests
elif FROZEN:
    DATA = Path(os.environ["LOCALAPPDATA"]) / "Shiori"
    OLD = Path(os.environ["LOCALAPPDATA"]) / "Stage"  # this app's name before it was Shiori
    if OLD.is_dir() and not DATA.exists():
        try:
            OLD.rename(DATA)  # your parks come along
        except OSError:
            DATA = OLD  # in use or locked: keep using the old folder rather than lose anything
else:
    DATA = APP_DIR / "data"

EXTENSION = APP_DIR / "extension"
