"""Where your windows were: saved with a desk, put back on resume.

  {"app": "code.exe", "title": ..., "targets": [folder], "rect": [l, t, r, b], "maximized": False}

Only windows the resume itself opened are moved. A window that was already open stays
where you have it. If the monitor a window was on isn't connected, Windows places it.
"""
import ctypes
import logging
import threading
import time

import pywintypes
import win32api
import win32con
import win32gui

from capture import list_windows

WAIT_SECONDS = 20    # slow apps can take this long to open a window
CHECK_EVERY = 1.0
PATIENT_SECONDS = 5  # until then a window must look right, not just be the right app: titles fill in late
MOVE_AGAIN = 2.5     # apps like VS Code place themselves once more as they load: move them back
LOOK_RIGHT = 2       # score of a window that isn't only the same app

log = logging.getLogger("shiori")


def of(windows):
    """Where each window is now. Minimized ones have no place on screen, so they're left out."""
    return [{"app": w.app, "title": w.title, "targets": w.targets, "rect": list(w.rect), "maximized": w.maximized}
            for w in windows if w.group != "SKIP" and not w.minimized]


def wanted(snapshot):
    """The saved places of what's being reopened, leaving out what you unticked."""
    kept = [i for i in snapshot["windows"] if i.get("keep", True)]
    apps = {i["app"] for i in kept}
    folders = {t.lower() for i in kept for t in i.get("targets", [])}
    return [p for p in snapshot.get("layout", []) if p["app"] in apps
            and (not p["targets"] or folders & {t.lower() for t in p["targets"]})]


def score(place, win):
    """How well an open window fits a saved place. 0 means it isn't that window."""
    if win.app != place["app"]:
        return 0
    if place["targets"]:  # an editor or folder: only the same folder will do
        return 4 if {t.lower() for t in place["targets"]} & {t.lower() for t in win.targets} else 0
    if win.title == place["title"]:
        return 3
    return LOOK_RIGHT if max(place["title"].split(" - "), key=len) in win.title else 1


def pairs(places, windows, least=1):
    """Best fits first, each place and window used once."""
    fits = sorted(((score(p, w), i, j) for i, p in enumerate(places) for j, w in enumerate(windows)),
                  key=lambda fit: -fit[0])
    used_places, used_windows, out = set(), set(), []
    for points, i, j in fits:
        if points >= least and i not in used_places and j not in used_windows:
            used_places.add(i)
            used_windows.add(j)
            out.append((places[i], windows[j]))
    return out


def on_screen(rect):
    """Is the middle of this rectangle on a connected monitor?"""
    middle = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
    return bool(win32api.MonitorFromPoint(middle, win32con.MONITOR_DEFAULTTONULL))


def put(hwnd, place):
    """Move a window to its saved place, without taking the focus."""
    left, top, right, bottom = place["rect"]
    try:
        if not on_screen(place["rect"]):
            return
        if ctypes.windll.user32.IsZoomed(hwnd):  # a maximized window can't be moved
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetWindowPos(hwnd, None, left, top, right - left, bottom - top,
                              win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
        if place["maximized"]:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    except pywintypes.error:  # it closed, or it's an admin window Windows won't let us move
        log.info("couldn't move %s", place["title"][:40])


def settle(places, before, look=list_windows, move=put, wait=WAIT_SECONDS, sleep=time.sleep, clock=time.monotonic):
    """Watch for the windows a resume opens and move each to its place as it appears."""
    waiting, moved, again = list(places), set(), {}
    started = clock()
    while (waiting or again) and clock() - started < wait:
        sleep(CHECK_EVERY)
        now = clock()
        fresh = [w for w in look() if w.hwnd not in before and w.hwnd not in moved]
        least = LOOK_RIGHT if now - started < PATIENT_SECONDS else 1
        for place, win in pairs(waiting, fresh, least):
            move(win.hwnd, place)
            waiting.remove(place)
            moved.add(win.hwnd)
            again[win.hwnd] = (place, now + MOVE_AGAIN)
        for hwnd, (place, when) in list(again.items()):
            if now >= when:
                move(hwnd, place)
                del again[hwnd]


def restore_later(snapshot, before):
    """Put the windows of a resume back in place, in the background: they take a while to open."""
    if places := wanted(snapshot):
        threading.Thread(target=settle, args=(places, set(before)), daemon=True).start()
