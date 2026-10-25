"""What a park holds: one list of items, app windows, browser tabs, terminals and files together.

  {"kind": "window", "app": "code.exe", "title": ..., "targets": [folder], "group": "FULL", "keep": True, ...}
  {"kind": "tab", "browser": "chrome", "window": 1, "title": ..., "url": ..., "keep": True}
  {"kind": "terminal", "folder": ..., "command": "npm run dev", "rerun": True, ...}   (terminals.py)
  {"kind": "file", "app": "excel.exe", "path": ..., "where": {...}, ...}             (office.py)

The more specific kinds replace their app's plain window: a browser's tabs (when
the extension reports), Windows Terminal's shells, and Office's open files. So you
keep or drop each tab, terminal or file on its own.
"""
from dataclasses import asdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import browser
import docs
import office
import terminals
from capture import list_windows

# Browser pages that can't (or shouldn't) be reopened
SKIP_URLS = ("chrome://", "edge://", "about:", "chrome-extension://", "extension://", "devtools://")

# Chat, music and calls are open all day, not part of a task: they start unticked
# (you can still tick them). Matched against app names and website addresses.
NEVER_PARK_APPS = {"whatsapp.exe", "discord.exe", "spotify.exe", "telegram.exe", "slack.exe",
                   "ms-teams.exe", "teams.exe", "zoom.exe", "signal.exe"}
NEVER_PARK_SITES = ("web.whatsapp.com", "discord.com", "open.spotify.com", "music.youtube.com",
                    "web.telegram.org", "teams.microsoft.com", "netflix.com", "primevideo.com",
                    "hotstar.com", "instagram.com", "messenger.com")


def usually_not_work(item):
    if item["app"] in NEVER_PARK_APPS:
        return True
    url = item.get("url", "")
    return any(f"//{site}" in url or f".{site}" in url for site in NEVER_PARK_SITES)


def current_items():
    windows = list_windows()
    tabs = browser.fresh_tabs({w.app for w in windows})
    shells = terminals.current()
    files = office.current()
    apps_with_files = {f["app"] for f in files}
    items = []
    for w in windows:
        if w.group == "SKIP":
            continue
        if browser.BROWSER_OF_APP.get(w.app) in tabs:
            continue  # this browser's tabs are listed one by one below
        if w.app == "windowsterminal.exe" and shells:
            continue  # its shells are listed one by one below
        if w.app in apps_with_files:
            continue  # its open files are listed one by one below
        window = {k: v for k, v in asdict(w).items() if k != "hwnd"}
        items.append({"kind": "window", **window, "keep": True})

    # windows whose title names a file (a PDF in Edge, todo.txt in Notepad) become file items
    if any(docs.name_from_title(i["title"], i["app"]) for i in items if i["app"] in docs.TITLE_APPS | docs.BROWSERS):
        recent = docs.recent_files()
        items = [docs.file_item(i, recent) or i for i in items]

    for name, browser_windows in tabs.items():
        items += tab_items(name, browser_windows)
    items += shells + files
    for item in items:
        item["keep"] = not usually_not_work(item)
    return items


def with_time(url, seconds):
    """A YouTube link that starts at this second: '…watch?v=x' -> '…watch?v=x&t=1390s'."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "t"] + [("t", f"{seconds}s")]
    return urlunsplit(parts._replace(query=urlencode(query)))


def without_time(url):
    """The same link minus its start time, to tell whether a video is already open."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(query=urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != "t"])))


def tab_items(name, browser_windows):
    """One item per tab of one browser, from its extension's report."""
    out = []
    for number, win in enumerate(browser_windows, start=1):
        for tab in win["tabs"]:
            if not tab.get("url") or tab["url"].startswith(SKIP_URLS):
                continue
            url, seconds = tab["url"], tab.get("time")
            if seconds and seconds > 5:  # a video you'd started: resume there
                url = with_time(url, seconds)
            out.append({
                "kind": "tab", "browser": name, "app": browser.EXE[name], "window": number,
                "title": tab.get("title") or tab["url"], "url": url, "video_time": seconds or 0,
                "pinned": tab.get("pinned", False), "tab_group": tab.get("group", ""), "keep": True,
            })
    for item in out:
        item["keep"] = not usually_not_work(item)
    return out


def kind(item):
    return item.get("kind", "window")  # parks from before tabs existed have no kind
