"""Your settings, in settings.json next to your desks. Changed from the tray menu.

  desk_pictures  keep a picture of the screen with each save (shown when you resume)
  hotkey         the keys that open Shiori, one of HOTKEYS
  autosave       quietly keep what's open, for after a restart or a crash (see autosave.py)
  check_updates  ask GitHub once a day whether a newer version is out (see updates.py)
"""
import json

import paths

FILE = paths.DATA / "settings.json"
DEFAULTS = {"desk_pictures": True, "hotkey": "Ctrl+Alt+S", "autosave": True, "check_updates": True}

# The choices offered in the tray. Kept to a short list of combinations that are rarely
# taken by other apps, so you can't pick one that silently never works.
HOTKEYS = ["Ctrl+Alt+S", "Ctrl+Alt+D", "Ctrl+Alt+K", "Ctrl+Shift+Space", "Alt+Shift+S"]


def load():
    try:
        saved = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    out = DEFAULTS | {k: v for k, v in saved.items() if k in DEFAULTS}
    if out["hotkey"] not in HOTKEYS:
        out["hotkey"] = DEFAULTS["hotkey"]
    return out


def get(key):
    return load()[key]


def change(key, value):
    current = load() | {key: value}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
