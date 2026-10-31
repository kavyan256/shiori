"""The desk you usually work on at this time of day, worked out from when you saved it.

A suggestion only: it shows a notification and never opens or saves anything by itself.
"""
import time
from datetime import datetime

import settings
import store

MIN_DAYS = 3  # different days at about this hour before it counts as a habit
CHECK_EVERY = 900


def usual_desk(stages, now=None):
    """The name of the desk saved at about this hour on the most days, or None."""
    now = now or datetime.now()
    best, most = None, MIN_DAYS - 1
    for stage in stages:
        times = [datetime.fromisoformat(s["parked_at"]) for s in stage["snapshots"]]
        days = {t.date() for t in times if t.date() != now.date() and abs(t.hour - now.hour) <= 1}
        if len(days) > most:
            best, most = stage["name"], len(days)
    return best


def keep_watching(suggest):
    """Runs for as long as Shiori does. Suggests one desk at most, once a day."""
    told = None
    while True:
        time.sleep(CHECK_EVERY)
        try:
            today = datetime.now().date()
            if told != today and settings.get("save_reminders"):
                name = usual_desk(store.list_stages())
                if name:
                    told = today
                    suggest(name)
        except Exception:  # a suggestion must never take Shiori down
            pass
