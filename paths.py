"""Where Stage's files are, whether it runs from source (python main.py) or as Stage.exe.

  BUNDLE    read-only files packed into the app (web/bar.html)
  APP_DIR   the folder Stage.exe (or main.py) is in; the Chrome extension sits here
  DATA      your parks and the log. From source: ./data. As Stage.exe: %LOCALAPPDATA%\\Stage,
            because an installed app can't write next to itself. STAGE_DATA overrides both (tests).
"""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)  # True inside Stage.exe (PyInstaller sets it)
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent

if os.environ.get("STAGE_DATA"):
    DATA = Path(os.environ["STAGE_DATA"])
elif FROZEN:
    DATA = Path(os.environ["LOCALAPPDATA"]) / "Stage"
else:
    DATA = APP_DIR / "data"

EXTENSION = APP_DIR / "extension"
