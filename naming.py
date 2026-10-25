"""A suggested park name, from what's ticked, so "save" alone is enough.

Strongest hint first: the git repo you're in, then project folders (VS Code,
terminals), a GitHub repo in a tab, open files, and last the main website.
  repo ka-OS + github.com/kavyan256/ka-OS + localhost  -> "ka-OS"
  DBMS unit 3.pdf + college portal                     -> "DBMS unit 3"
"""
import os
from collections import Counter
from datetime import datetime
from urllib.parse import urlsplit

import store
from items import kind

HOME = os.path.expanduser("~").lower()
# sites too general to name a task after
GENERIC_SITES = {"google", "youtube", "bing", "duckduckgo", "chatgpt", "claude", "gemini", "perplexity",
                 "mail", "outlook", "localhost", "127.0.0.1", "stackoverflow", "reddit", "x", "twitter",
                 "linkedin", "wikipedia", "notion", "docs", "drive"}


def _folder_name(path):
    path = (path or "").rstrip("\\/")
    if not path or path.lower() in (HOME, HOME + "\\desktop", "c:"):
        return None  # the home folder says nothing about the task
    return os.path.basename(path)


def _site(url):
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    parts = host.split(".")
    return parts[-2] if len(parts) >= 2 else host


def suggest(items, found_cues=()):
    votes = Counter()
    for c in found_cues:
        votes[c["repo"]] += 6
    for item in items:
        if not item.get("keep", True):
            continue
        k = kind(item)
        if k == "terminal":
            name = _folder_name(item["folder"])
            if name:
                votes[name] += 3
        elif k == "window" and item.get("targets"):
            for target in item["targets"]:
                if name := _folder_name(target):
                    votes[name] += 4
        elif k == "file":
            stem = os.path.splitext(item["title"])[0]
            if stem and not stem.lower().startswith(("untitled", "book", "document", "presentation")):
                votes[stem] += 2
        elif k == "tab":
            url = item.get("url", "")
            path = urlsplit(url).path.strip("/").split("/")
            if "github.com" in url and len(path) >= 2:
                votes[path[1]] += 3  # github.com/<user>/<repo>
            site = _site(url)
            if site and site not in GENERIC_SITES:
                votes[site] += 1
    if votes:
        name, _ = votes.most_common(1)[0]
        return name[:32]
    return readable_time_name()


def readable_time_name(now=None):
    """Nothing to go on: "Sunday evening", or "Sunday evening 6:40 pm" if that name is taken."""
    now = now or datetime.now()
    if 5 <= now.hour < 12:
        part = "morning"
    elif 12 <= now.hour < 17:
        part = "afternoon"
    elif 17 <= now.hour < 21:
        part = "evening"
    else:
        part = "night"
    name = f"{now:%A} {part}"
    if store.load(name):
        name += " " + now.strftime("%I:%M %p").lstrip("0").lower()
    return name
