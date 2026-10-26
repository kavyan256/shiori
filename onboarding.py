"""The first-run guide: three steps that tick off as you actually do them.

  1. open Shiori with the hotkey     (ticked when you press Ctrl+Alt+S)
  2. save my desk, then save       (ticked when a desk is saved)
  3. resume it                      (ticked when you resume or start one)

Progress lives in onboarding.json next to your parks. The guide shows on the home
screen until all three are done (or you hide it), and on the very first launch the
bar opens by itself so you see it.
"""
import json

import paths

FILE = paths.DATA / "onboarding.json"
STEPS = ("hotkey", "saved", "resumed")


def _load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def first_run():
    """True only the very first time Shiori starts for this user."""
    return not FILE.exists()


def start(has_parks=False):
    """Create the progress file, so the next start isn't a first run. Someone who already
    has parks (from before the guide existed) starts with 'saved' ticked."""
    if first_run():
        FILE.parent.mkdir(parents=True, exist_ok=True)
        progress = {step: False for step in STEPS} | {"saved": has_parks}
        FILE.write_text(json.dumps(progress), encoding="utf-8")


def mark(step):
    progress = _load()
    if progress and not progress.get(step):
        progress[step] = True
        FILE.write_text(json.dumps(progress), encoding="utf-8")


def hide():
    progress = _load() or {step: False for step in STEPS}
    progress["hidden"] = True
    FILE.write_text(json.dumps(progress), encoding="utf-8")


def guide():
    """What the home screen shows: the steps and which are done, or None once finished or hidden."""
    progress = _load()
    if not progress or progress.get("hidden") or all(progress.get(s) for s in STEPS):
        return None
    return {step: bool(progress.get(step)) for step in STEPS}
