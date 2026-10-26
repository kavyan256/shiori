"""Time limits for things that can hang: Office over COM, files on a network drive.

Excel with a "Save changes?" box open, or a cell being edited, can leave a COM call
waiting forever. Checking a file on a network share that has gone offline can take
30 seconds. Shiori must never freeze on either, so those calls run in a thread and
are given up on after a few seconds: you get a desk with that one thing missing,
never a frozen bar.

A call that is given up on keeps running in the background (Python can't stop a
thread) but nothing waits for it, and it can't keep Shiori from quitting.
"""
import logging
import os
import threading
import time

log = logging.getLogger("shiori")

OFFICE_SECONDS = 3.0  # Office normally answers in well under a second
FILE_SECONDS = 1.5    # a local disk answers in microseconds; only a dead network drive is slower


def within(seconds, fn, *args, default=None, what=""):
    """fn(*args), or `default` if it takes longer than `seconds` or fails."""
    result = {}

    def run():
        try:
            result["value"] = fn(*args)
        except Exception as e:  # the caller gets the default; the log says why
            result["error"] = e

    worker = threading.Thread(target=run, daemon=True, name=f"limit:{what or fn.__name__}")
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        log.warning("gave up on %s after %.1f s (not answering)", what or fn.__name__, seconds)
        return default
    if "error" in result:
        log.info("%s failed: %s", what or fn.__name__, result["error"])
        return default
    return result.get("value", default)


def exist(paths, seconds=FILE_SECONDS):
    """{path: True/False} for each path, checked side by side; a path that doesn't answer
    in time (an offline network drive) counts as missing."""
    found = {}

    def check(path):
        found[path] = os.path.exists(path)

    workers = [threading.Thread(target=check, args=(p,), daemon=True) for p in dict.fromkeys(paths)]
    for w in workers:
        w.start()
    deadline = time.monotonic() + seconds
    for w in workers:
        w.join(max(0, deadline - time.monotonic()))  # `seconds` in total, however many hang
    slow = [p for p in dict.fromkeys(paths) if p not in found]
    if slow:
        log.warning("gave up checking %d path(s) after %.1f s: %s", len(slow), seconds, slow[:3])
    return {p: found.get(p, False) for p in paths}
