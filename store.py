"""Saving and loading parks.

One JSON file per park name in data/stages/<name>.json. Saving under a name that
already exists adds a new version to its history; resume uses the newest.
Deleting moves the file to data/trash/, so a mistake can be undone by hand.

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
from datetime import datetime
from pathlib import Path

# STAGE_DATA lets tests save somewhere else without touching your real parks
DATA_DIR = Path(os.environ.get("STAGE_DATA", Path(__file__).parent / "data")) / "stages"
TRASH_DIR = DATA_DIR.parent / "trash"


def slug(name):
    """'College DBMS!' -> 'college-dbms', safe to use as a filename."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def path_of(name):
    return DATA_DIR / f"{slug(name)}.json"


def load(name):
    """The whole park (name + every version), or None if it doesn't exist."""
    path = path_of(name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save(stage):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = path_of(stage["name"])
    # Write to a temp file, then swap it in, so a crash never leaves half a file
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(stage, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def park(name, items, note="", steps=None):
    """Save a version under this name (creating it if new). Items keep their keep=True/False."""
    stage = load(name) or {"name": name, "snapshots": []}
    snapshot = {
        "parked_at": datetime.now().isoformat(timespec="seconds"),
        "brain_dump": note,
        "next_steps": steps or [],
        "windows": items,  # app windows and browser tabs (see items.py)
    }
    stage["snapshots"].append(snapshot)
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
    """Move the park to data/trash/ (with a timestamp, so trashing twice never overwrites)."""
    path = path_of(name)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), TRASH_DIR / f"{path.stem}-{datetime.now():%Y%m%d-%H%M%S}.json")


FILLER_WORDS = {"the", "my", "a", "stage", "park", "parks", "part", "parts", "project", "work", "thing", "stuff"}
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


def list_stages():
    """Every park with its versions, most recently parked first."""
    if not DATA_DIR.exists():
        return []
    stages = [json.loads(p.read_text(encoding="utf-8")) for p in DATA_DIR.glob("*.json")]
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
