"""Clearing the desk after a park, and taking back (undoing) a resume.

"Park and clear" closes what you just saved, the way clicking X would, so apps
still ask about unsaved work. Some things are never closed, and say why:
  - terminals: closing one stops whatever is running in it
  - browser windows Shiori only saw as a window (no extension): their other tabs weren't saved
  - Office files with unsaved changes: Shiori won't throw your edits away
"""
import win32con
import win32gui

import browser
import docs
import office
from capture import list_windows
from items import kind


def close_windows(hwnds):
    for hwnd in hwnds:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)  # same as clicking X
        except Exception:
            pass


def close_items(items):
    """Close the kept items of a park. Returns (what was closed, what was left open and why)."""
    open_now = list_windows()
    to_close, closed, left = set(), [], []
    tab_urls = {}
    for item in [i for i in items if i.get("keep", True)]:
        k, app = kind(item), item["app"]
        if k == "terminal":
            left.append(f"{item['title']}: closing a terminal would stop what's running in it")
        elif k == "tab":
            tab_urls.setdefault(item["browser"], []).append(item["url"])
        elif k == "file" and app in office.APPS:
            if office.close(item["path"]):
                closed.append(item["title"])
            else:
                left.append(f"{item['title']}: has unsaved changes")
        elif app in docs.BROWSERS:
            left.append(f"{item['title'][:40]}: only its front tab was saved")
        elif k == "file":
            wins = [w for w in open_now if w.app == app and item["title"].lower() in w.title.lower()]
            to_close |= {w.hwnd for w in wins}
            closed += [item["title"]] if wins else []
        elif item.get("targets"):  # VS Code / Explorer: the windows on those folders
            wanted = {t.lower() for t in item["targets"]}
            wins = [w for w in open_now if w.app == app and wanted & {t.lower() for t in w.targets}]
            to_close |= {w.hwnd for w in wins}
            closed += [item["title"][:40]] if wins else []
        elif app == "code.exe":  # VS Code on a single file: match the title
            wins = [w for w in open_now if w.app == app and w.title == item["title"]]
            to_close |= {w.hwnd for w in wins}
            closed += [item["title"][:40]] if wins else []
        else:
            wins = [w for w in open_now if w.app == app]
            to_close |= {w.hwnd for w in wins}
            closed += [item["title"][:40]] if wins else []
    for name, urls in tab_urls.items():
        if browser.close_tabs(name, urls):
            closed.append(f"{len(urls)} {name.title()} tab{'s' if len(urls) > 1 else ''}")
        else:
            left.append(f"{len(urls)} {name.title()} tabs: the Shiori extension isn't connected")
    close_windows(to_close)
    return list(dict.fromkeys(closed)), list(dict.fromkeys(left))


def undo_resume(before_hwnds, apps, park_name, reopened_files):
    """Close what a resume opened: new windows of the apps it reopened (never a window
    of some other app you opened meanwhile), the park's tab group, and the Office files
    it reopened (unless you've edited them since)."""
    # Office apps are left out: each workbook has its own window there, and other files you
    # have open (maybe with unsaved edits) could share it. Its files close one by one below.
    windowed = set(apps) - set(office.APPS)
    new = [w.hwnd for w in list_windows() if w.hwnd not in before_hwnds and w.app in windowed]
    close_windows(new)
    for name in browser.EXE:
        browser.close_group(name, park_name)
    closed_files = sum(1 for path in reopened_files if office.close(path))
    return len(new) + closed_files
