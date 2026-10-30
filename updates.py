"""Telling you when a newer Shiori is out. It never installs anything by itself.

Once a day it asks GitHub for the latest release's number. That request is the only thing
Shiori sends beyond this PC, it says nothing about you or your desks, and it can be turned
off from the tray. With no internet it simply tries again the next day.
"""
import json
import logging
import time
import urllib.error
import urllib.request

import paths
import settings
from version import VERSION

LATEST = "https://api.github.com/repos/kavyan256/shiori/releases/latest"
RELEASES = "https://github.com/kavyan256/shiori/releases/latest"
FILE = paths.DATA / "update.json"
EVERY = 24 * 3600
FIRST_AFTER = 60   # seconds after starting, so it never slows the start down

log = logging.getLogger("shiori")


def number(version):
    """'v1.10.0' -> (1, 10, 0), so 1.10 counts as newer than 1.9."""
    try:
        return tuple(int(part) for part in version.lstrip("vV").split("."))
    except ValueError:
        return ()


def is_newer(latest, current=VERSION):
    return number(latest) > number(current)


def fetch():
    """The latest release's version, or '' if GitHub can't be reached."""
    request = urllib.request.Request(LATEST, headers={"User-Agent": f"Shiori/{VERSION}",
                                                      "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response).get("tag_name", "")
    except (OSError, ValueError) as e:  # URLError is an OSError
        log.info("update check skipped: %s", e)
        return ""


def known():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def available():
    """The newer version you could install, or ''."""
    latest = known().get("latest", "")
    return latest if is_newer(latest) else ""


def check(get=fetch):
    """Ask GitHub and remember the answer. Returns a version to announce, once per version."""
    latest = get()
    if not latest:
        return ""
    state = known()
    announce = is_newer(latest) and state.get("told") != latest
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps({"latest": latest, "told": latest if announce else state.get("told", "")}), encoding="utf-8")
    return latest if announce else ""


def keep_checking(tell, first=FIRST_AFTER, every=EVERY):
    """Runs for as long as Shiori does. tell(version) is called once for each new version."""
    time.sleep(first)
    while True:
        if settings.get("check_updates"):
            if found := check():
                tell(found)
        time.sleep(every)
