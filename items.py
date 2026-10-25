"""What a park holds: one list of items, app windows and browser tabs together.

  {"kind": "window", "app": "code.exe", "title": ..., "targets": [folder], "group": "FULL", "keep": True, ...}
  {"kind": "tab", "browser": "chrome", "window": 1, "title": ..., "url": ..., "keep": True}

When the extension is reporting, a browser's windows are replaced by its tabs,
so you can keep or drop each tab on its own.
"""
from dataclasses import asdict

import browser
from capture import list_windows

# Browser pages that can't (or shouldn't) be reopened
SKIP_URLS = ("chrome://", "edge://", "about:", "chrome-extension://", "extension://", "devtools://")


def current_items():
    windows = list_windows()
    tabs = browser.fresh_tabs({w.app for w in windows})
    items = []
    for w in windows:
        if w.group == "SKIP":
            continue
        if browser.BROWSER_OF_APP.get(w.app) in tabs:
            continue  # this browser's tabs are listed one by one below
        window = {k: v for k, v in asdict(w).items() if k != "hwnd"}
        items.append({"kind": "window", **window, "keep": True})

    for name, browser_windows in tabs.items():
        items += tab_items(name, browser_windows)
    return items


def tab_items(name, browser_windows):
    """One item per tab of one browser, from its extension's report."""
    out = []
    for number, win in enumerate(browser_windows, start=1):
        for tab in win["tabs"]:
            if not tab.get("url") or tab["url"].startswith(SKIP_URLS):
                continue
            out.append({
                "kind": "tab", "browser": name, "app": browser.EXE[name], "window": number,
                "title": tab.get("title") or tab["url"], "url": tab["url"],
                "pinned": tab.get("pinned", False), "tab_group": tab.get("group", ""), "keep": True,
            })
    return out


def kind(item):
    return item.get("kind", "window")  # parks from before tabs existed have no kind
