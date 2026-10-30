"""A quiet save of what's open, every few minutes, so a restart or a crash doesn't lose your desk.

  last-session.json       the newest quiet save. A normal Quit removes it.
  recovered-session.json  at start, a last-session.json still there means Shiori didn't get to
                          quit normally: it moves here and "restore last session" brings it back.

It is one file that keeps being replaced, never a desk of its own. Turn it off from the tray.
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta

import browser
import layout
import paths
import settings
import store
from capture import list_windows
from items import current_items

FILE = paths.DATA / "last-session.json"
RECOVERED = paths.DATA / "recovered-session.json"
EVERY = 300        # seconds between quiet saves
KEEP_DAYS = 3      # older than this, it's no use to anyone

log = logging.getLogger("shiori")


def fingerprint(items):
    return sorted(i.get("url") or i.get("path") or i.get("folder") or i["title"] for i in items if i.get("keep", True))


def read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write(items, places):
    """Replace the quiet save, unless nothing is open: while Windows shuts down, apps close
    one by one, and an emptying desk must not replace the real one."""
    if not any(i.get("keep", True) for i in items):
        return False
    old = read(FILE)
    now = datetime.now().isoformat(timespec="seconds")
    if old and fingerprint(old["windows"]) == fingerprint(items):
        old["layout"], old["checked_at"] = places, now  # same things open: only the layout may differ
        session = old
    else:
        session = {"parked_at": now, "checked_at": now, "brain_dump": "", "next_steps": [],
                   "windows": items, "layout": places, "cues": []}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(session, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, FILE)
    return True


def save_now():
    browser.request_reports()
    return write(current_items(), layout.of(list_windows()))


def keep_saving(every=EVERY):
    """Runs for as long as Shiori does."""
    while True:
        time.sleep(every)
        if settings.get("autosave"):
            try:
                save_now()
            except Exception:  # never let a quiet save take Shiori down
                log.exception("quiet save failed")


def at_start():
    """A quiet save left behind means Shiori was stopped by a restart or a crash."""
    if FILE.exists():
        os.replace(FILE, RECOVERED)


def finished():
    """Quit on purpose: nothing to recover."""
    FILE.unlink(missing_ok=True)
    FILE.with_suffix(".tmp").unlink(missing_ok=True)


def offer():
    """The session you could bring back, or None. Not if it's old, or if you've saved a desk since."""
    session = read(RECOVERED)
    if not session:
        return None
    saved_at = session.get("checked_at", session["parked_at"])
    parks = store.list_stages()
    stale = datetime.fromisoformat(saved_at) < datetime.now() - timedelta(days=KEEP_DAYS)
    if stale or (parks and parks[0]["snapshots"][-1]["parked_at"] > saved_at):
        forget()
        return None
    return session


def forget():
    RECOVERED.unlink(missing_ok=True)
