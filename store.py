"""Saving and loading parks.

One JSON file per park name in data/stages/<name>.json. Saving under a name that
already exists adds a new version to its history; resume uses the newest.
Deleting moves the file to data/trash/, so a mistake can be undone by hand.

Nothing grows forever: a desk keeps its newest KEEP_VERSIONS versions, the trash is
emptied of desks deleted more than TRASH_DAYS ago, and desk pictures no desk uses
any more are removed (see tidy(), run when Shiori starts).

Run:
  python store.py list
  python store.py show coding
"""
import difflib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import paths

DATA_DIR = paths.DATA / "stages"  # see paths.py: ./data from source, %LOCALAPPDATA%\Shiori as Shiori.exe
TRASH_DIR = DATA_DIR.parent / "trash"
SHOTS_DIR = DATA_DIR.parent / "shots"  # desk pictures (see desk.py)
KEEP_VERSIONS = 10  # older versions of a desk are dropped when a new one is saved
TRASH_DAYS = 30     # deleted desks stay this long, so a mistake can still be put back


def slug(name):
    """'College DBMS!' -> 'college-dbms', safe to use as a filename."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def path_of(name):
    return DATA_DIR / f"{slug(name)}.json"


def load(name):
    """The whole park (name + every version), or None if it doesn't exist."""
    path = path_of(name)
    return _read(path) if path.exists() else None


def save(stage):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = path_of(stage["name"])
    # Write to a temp file, then swap it in, so a crash never leaves half a file
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(stage, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def park(name, items, note="", steps=None, cues=None, shot="", layout=None):
    """Save a version under this name (creating it if new). Items keep their keep=True/False."""
    stage = load(name) or {"name": name, "snapshots": []}
    snapshot = {
        "parked_at": datetime.now().isoformat(timespec="seconds"),
        "brain_dump": note,
        "next_steps": steps or [],
        "windows": items,  # app windows, tabs, terminals and files (see items.py)
        "cues": cues or [],  # git branch / changes per repo (see cues.py)
        "layout": layout or [],  # where each window was (see layout.py)
    }
    if shot:
        snapshot["shot"] = shot  # a picture of the desk when you saved (see desk.py)
    stage["snapshots"].append(snapshot)
    stage["snapshots"] = stage["snapshots"][-KEEP_VERSIONS:]  # their pictures go in the next tidy()
    save(stage)
    return snapshot


def set_pins(name, items):
    """Make this park a preset: these items open on "start <name>". None removes the pins."""
    stage = load(name)
    if items is None:
        stage.pop("pinned", None)
    else:
        stage["pinned"] = [{**i, "keep": True} for i in items]
    save(stage)


def delete(name):
    """Move the park to data/trash/ (with a timestamp, so trashing twice never overwrites).
    Returns where it went, so it can be put back."""
    path = path_of(name)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    trashed = TRASH_DIR / f"{path.stem}-{datetime.now():%Y%m%d-%H%M%S}.json"
    shutil.move(str(path), trashed)
    return trashed


def undelete(trashed, name):
    """Put a trashed park back (undo). False if a park with that name exists again."""
    if path_of(name).exists() or not Path(trashed).exists():
        return False
    shutil.move(str(trashed), path_of(name))
    return True


FILLER_WORDS = {"the", "my", "a", "shiori", "stage", "desk", "desks", "disk", "park", "parks", "part", "parts", "project", "work", "thing", "stuff"}
NUMBERS = {w: str(n) for n, w in enumerate("zero one two three four five six seven eight nine ten".split())}


def words_of(key):
    """'test-parking-one' -> {'test', 'parking', '1'}: spoken numbers count as digits."""
    return {NUMBERS.get(w, w) for w in key.split("-")} - FILLER_WORDS


def find(spoken):
    """Match a spoken name to a saved park's real name, or None.

    Tries an exact match, then a saved name inside what was said, then shared
    words ('the college one' -> 'College DBMS', 'part one' -> 'test parking 1'),
    then the closest spelling ('hackaton'). Ties go to the most recently parked.
    """
    names = {slug(s["name"]): s["name"] for s in list_stages()}  # most recent first
    key = slug(spoken)
    if not key:
        return None
    if key in names:
        return names[key]
    inside = [k for k in names if k in key or key in k]
    if inside:
        return names[max(inside, key=len)]

    def score(k):
        shared = words_of(key) & words_of(k)
        # a shared number alone is weak evidence ("the college one" isn't "test parking 1")
        return sum(0.5 if w.isdigit() else 1 for w in shared)

    best = max(names, key=score, default=None)
    matching = [k for k in names if score(k) > 0]
    if best and (score(best) >= 1 or matching == [best]):  # a number alone is fine if only one park has it
        return names[best]
    close = difflib.get_close_matches(key, names, n=1, cutoff=0.6)
    return names[close[0]] if close else None


def latest(name):
    """The most recent version, the one resume uses."""
    stage = load(name)
    return stage["snapshots"][-1] if stage else None


_texts = {}  # path -> (modified time, size, text): opening files is the slow part, parsing isn't


def _text(path):
    """A park file's text, re-read from disk only when it has changed."""
    st = path.stat()
    key = (st.st_mtime_ns, st.st_size)
    cached = _texts.get(path)
    if not cached or cached[0] != key:
        cached = _texts[path] = (key, path.read_text(encoding="utf-8"))
    return cached[1]


def _read(path):
    """A park, or None if the file is damaged (edited by hand, disk trouble). A damaged
    file is renamed to .broken, so it can't break the list and nothing is lost."""
    try:
        stage = json.loads(_text(path))
        stage["snapshots"][-1]["parked_at"]  # the parts everything relies on
        return stage
    except (ValueError, KeyError, IndexError, TypeError):
        path.replace(path.with_suffix(".broken"))
        return None


def set_step(name, index, done):
    """Tick (or untick) one next step of the newest version. Returns the ticked step numbers (0-based)."""
    stage = load(name)
    snap = stage["snapshots"][-1]
    ticked = set(snap.get("done", []))
    if done:
        ticked.add(index)
    else:
        ticked.discard(index)
    snap["done"] = sorted(i for i in ticked if 0 <= i < len(snap["next_steps"]))
    save(stage)
    return snap["done"]


def tidy(now=None):
    """Empty old trash and remove desk pictures nothing uses. Returns (trash files, pictures) removed.
    A picture is only removed once it's a day old, so one being saved right now is never touched."""
    now = now or time.time()
    removed_trash = 0
    for f in TRASH_DIR.glob("*.json") if TRASH_DIR.exists() else []:
        if now - f.stat().st_mtime > TRASH_DAYS * 86400:
            f.unlink(missing_ok=True)
            removed_trash += 1
    if not SHOTS_DIR.exists():
        return removed_trash, 0
    used = set()
    for f in [*DATA_DIR.glob("*.json"), *TRASH_DIR.glob("*.json")]:  # a trashed desk can be put back
        try:
            stage = json.loads(f.read_text(encoding="utf-8"))
            used.update(s.get("shot", "") for s in stage.get("snapshots", []))
        except (OSError, ValueError, AttributeError):
            return removed_trash, 0  # can't tell what's used: remove nothing
    removed_shots = 0
    for f in SHOTS_DIR.glob("*.jpg"):
        if f.name not in used and now - f.stat().st_mtime > 86400:
            f.unlink(missing_ok=True)
            removed_shots += 1
    return removed_trash, removed_shots


def delete_pictures():
    """Every desk picture, gone (when you turn desk pictures off). Returns how many."""
    shots = list(SHOTS_DIR.glob("*.jpg")) if SHOTS_DIR.exists() else []
    for f in shots:
        f.unlink(missing_ok=True)
    return len(shots)


def list_stages():
    """Every park with its versions, most recently parked first."""
    if not DATA_DIR.exists():
        return []
    stages = [s for s in map(_read, DATA_DIR.glob("*.json")) if s]
    return sorted(stages, key=lambda s: s["snapshots"][-1]["parked_at"], reverse=True)


def ago(iso_time):
    seconds = (datetime.now() - datetime.fromisoformat(iso_time)).total_seconds()
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            n = int(seconds // size)
            return f"{n} {unit}{'s' if n > 1 else ''} ago"
    return "just now"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    command, *args = sys.argv[1:] or ["list"]
    if command == "list":
        for s in list_stages():
            last = s["snapshots"][-1]
            print(f"● {s['name']:<24} {ago(last['parked_at']):<16} {len(s['snapshots'])} version(s)")
    elif command == "show" and args:
        snap = latest(args[0])
        if not snap:
            sys.exit(f"No park called '{args[0]}'")
        print(json.dumps(snap, indent=2, ensure_ascii=False))
    else:
        sys.exit(__doc__)
