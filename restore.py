"""Resume a park by reopening what was saved in its newest version.

Run:
  python restore.py coding          # reopen everything
  python restore.py coding --dry    # only print what it would do
"""
import os
import shutil
import subprocess
import sys

import psutil

import win32con
import win32gui
import win32process

import browser
import docs
import limits
import office
import store
import terminals
from capture import EDITORS, app_id_of, list_windows
from commands import app_name
from items import kind, without_time

# Store apps all run inside this host, so its exe can't relaunch a specific app.
# Python on its own opens nothing (and old parks may hold Shiori's own popup).
CANT_RELAUNCH = {"applicationframehost.exe", "unknown", "python.exe", "pythonw.exe", "stage.exe", "shiori.exe"}
# Terminal windows saved as plain windows (old parks): a fresh window opens
CONSOLES = {"cmd.exe", "powershell.exe", "pwsh.exe"}

# What isn't restored yet, and why
LATER = {
    "chrome.exe": "parked before the extension was installed, so its tabs weren't saved",
    "msedge.exe": "parked before the extension was installed, so its tabs weren't saved",
    "winword.exe": "no saved file was open in it when you parked",
    "excel.exe": "no saved file was open in it when you parked",
    "powerpnt.exe": "no saved file was open in it when you parked",
}


def launch(args):
    # CREATE_NO_WINDOW stops a console flashing up for code.cmd
    subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)


def new_console(exe):
    return lambda: subprocess.Popen([exe], creationflags=subprocess.CREATE_NEW_CONSOLE)


def unminimize(hwnds):
    return lambda: [win32gui.ShowWindow(h, win32con.SW_RESTORE) for h in hwnds]


def running_app_id(app):
    """App ID of a running Store-style app, for parks saved before Shiori recorded it.
    Looks only at processes that own a window (a tray app has a hidden one) and are
    packaged apps, instead of asking every process on the PC for its name (~0.7 s)."""
    pids = set()
    win32gui.EnumWindows(lambda hwnd, _: pids.add(win32process.GetWindowThreadProcessId(hwnd)[1]), None)
    for pid in pids:
        if found := app_id_of(pid):
            try:
                if psutil.Process(pid).name().lower() == app:
                    return found
            except psutil.Error:
                pass
    return ""


def start_command(w):
    """How to start this app with no window open, or None if Shiori can't."""
    exe, app = w.get("exe", ""), w["app"]
    if app in CONSOLES and exe:
        return new_console(exe)
    if "\\windowsapps\\" in exe.lower():  # Store-style app: start it by its app ID
        app_id = w.get("app_id") or running_app_id(app)
        return ["explorer.exe", f"shell:AppsFolder\\{app_id}"] if app_id else None
    if app in CANT_RELAUNCH or not exe:
        return None
    return [exe]


def plan(snapshot, name=""):
    """Turn a snapshot into (description, command) pairs, skipping what's already open.
    A command is either a program to start or a function to call."""
    open_now = list_windows()
    # (app, folder) -> its open windows, so the same folder in VS Code and Explorer counts twice
    open_targets = {}
    for win in open_now:
        for t in win.targets:
            open_targets.setdefault((win.app, t.lower()), []).append(win)
    windows_of = {}  # app -> its open windows
    for win in open_now:
        windows_of.setdefault(win.app, []).append(win)
    code_cmd = shutil.which("code")
    tabs = {}  # browser -> {its window number: URLs to reopen together as one tab group}
    wanted_terminals, wanted_files, local_tabs = [], [], []
    handled_apps = set()

    def already_open(label, wins):
        """Open but maybe minimized: bring minimized ones back, else nothing to do."""
        hidden = [x.hwnd for x in wins if x.minimized]
        if hidden and len(hidden) == len(wins):
            actions.append((f"Show {label}", unminimize(hidden)))
        else:
            skipped.append(f"{label} (already open)")

    actions, skipped = [], []
    for w in snapshot["windows"]:
        if not w.get("keep", True):
            continue  # you dropped it when parking
        if kind(w) == "tab":
            if w["url"].startswith("file:"):  # extensions can't open local files: Shiori does
                local_tabs.append(w)
            else:
                tabs.setdefault(w["browser"], {}).setdefault(w.get("window", 1), []).append(w["url"])
            continue
        if kind(w) == "terminal":
            wanted_terminals.append(w)
            continue
        if kind(w) == "file":
            wanted_files.append(w)
            continue
        app = w["app"]
        targets = w.get("targets", [])  # snapshots from before step 3 don't have it

        if (app in EDITORS or app == "explorer.exe") and targets:
            for target in targets:
                label = f"{app_name(w)} {target.rsplit(chr(92), 1)[-1]}"
                if (app, target.lower()) in open_targets:
                    already_open(label, open_targets[(app, target.lower())])
                elif app == "code.exe" and code_cmd:
                    actions.append((f"VS Code   {target}", [code_cmd, "-n", target]))
                elif app in EDITORS and w.get("exe") and os.path.exists(w["exe"]):  # Cursor, Windsurf…: their own exe
                    actions.append((f"{app_name(w)}   {target}", [w["exe"], "-n", target]))
                elif app in EDITORS:
                    skipped.append(f"{app_name(w)} {target} (couldn't find the editor to open it)")
                else:
                    actions.append((f"Explorer  {target}", ["explorer", target]))
                open_targets.setdefault((app, target.lower()), [])  # don't open the same folder twice

        elif app in LATER:
            skipped.append(f"{app} ({LATER[app]})")

        elif w["group"] == "SHOT" or app == "windowsterminal.exe" or app in CONSOLES:
            if app in handled_apps:
                continue  # one per app: two Claude windows saved still means start Claude once
            handled_apps.add(app)
            if windows_of.get(app):  # judge by windows, not processes: Claude keeps running in the tray
                already_open(app_name(w), windows_of[app])
            elif command := start_command(w):
                actions.append((f"App       {app_name(w)}", command))
            else:
                skipped.append(f"{w['title'][:40]} (can't start this app)")

        elif w["group"] == "TITLE":
            skipped.append(f"{app_name(w)} {w['title'][:40]} (couldn't tell which file: not in Recent items)")

        else:
            skipped.append(f"{app} {w['title'][:40]} (no folder found)")

    # Terminals: skip ones already running in that folder (with that command, if it re-runs)
    if wanted_terminals:
        running = terminals.current()
        new = []
        for t in wanted_terminals:
            same_place = [r for r in running if r["folder"].lower() == t["folder"].lower()]
            if any(not t.get("rerun") or r["command"] == t["command"] for r in same_place):
                skipped.append(f"Terminal {t['title']} (already open)")
            else:
                new.append(t)
            if t["command"] and not t.get("rerun"):
                skipped.append(f"“{t['command']}” wasn't re-run: only dev servers and watchers are")
        if new:
            actions.append((f"Terminal  {len(new)} tab{'s' if len(new) > 1 else ''}",
                            lambda n=new: terminals.open_all(n)))

    # Files: skip ones already open. Office ones reopen at the same sheet/cell or slide;
    # others (a PDF in Edge, a .txt in Notepad) reopen in the same app.
    if wanted_files:
        open_paths = {f["path"].lower() for f in office.current()}
        if any(f["app"] not in office.APPS for f in wanted_files):
            recent = docs.recent_files()
            for win in open_now:
                found = docs.file_item({"app": win.app, "title": win.title, "exe": win.exe}, recent)
                if found:
                    open_paths.add(found["path"].lower())
        there = limits.exist([f["path"] for f in wanted_files if "://" not in f["path"]])
        for f in wanted_files:
            if f["path"].lower() in open_paths:
                skipped.append(f"{f['title']} (already open)")
            elif "://" not in f["path"] and not there[f["path"]]:
                skipped.append(f"{f['title']} (the file isn't there, or its drive isn't connected)")
            else:
                place = f" · {f['where_text']}" if f.get("where_text") else ""
                opener = office.reopen if f["app"] in office.APPS else docs.reopen
                actions.append((f"{app_name(f)}  {f['title']}{place}", lambda f=f, o=opener: o(f)))

    # Local files open in a browser tab (file:///…pdf): Shiori opens them in that browser
    for t in local_tabs:
        exe = browser.browser_exe(t["browser"])
        actions.append((f"{t['browser'].title()}  {t['title']}", lambda e=exe, u=t["url"]: subprocess.Popen([e, u])))

    open_tabs = browser.fresh_tabs({w.app for w in open_now})
    for name_of_browser, by_window in tabs.items():
        urls = [u for window in by_window.values() for u in window]
        # compare without YouTube start times: the same video open at another minute is still open
        already = {without_time(t["url"]) for win in open_tabs.get(name_of_browser, []) for t in win["tabs"]}
        seen, windows = set(), []  # no duplicates, nothing already open
        for window in by_window.values():
            new = [u for u in dict.fromkeys(window) if without_time(u) not in already and u not in seen]
            seen.update(new)
            if new:
                windows.append(new)
        if len(seen) < len(urls):
            skipped.append(f"{len(urls) - len(seen)} {name_of_browser} tab(s) (already open)")
        for n, new in enumerate(windows):
            where = f" · window {n + 1}" if len(windows) > 1 else ""
            label = f"{name_of_browser.title()}  {len(new)} tab{'s' if len(new) > 1 else ''}{where}"
            actions.append((label, lambda b=name_of_browser, u=new, extra=n > 0: browser.open_tabs(b, u, name or "Shiori", extra)))

    return actions, skipped


def reopen(snapshot, name="", dry=False):
    """Open everything in the plan. Returns (opened descriptions, skipped reasons)."""
    actions, skipped = plan(snapshot, name)
    if not dry:
        for _, command in actions:
            command() if callable(command) else launch(command)
    return [description for description, _ in actions], skipped


def resume(name, dry=False):
    snapshot = store.latest(name)
    if not snapshot:
        sys.exit(f"No Shiori called '{name}'")

    # The note comes first: getting your head back matters more than windows
    print(f"Resuming '{name}', parked {store.ago(snapshot['parked_at'])}\n")
    print(f"🧠 {snapshot['brain_dump'] or '(no note)'}")
    for step in snapshot["next_steps"]:
        print(f"   ☐ {step}")

    opened, skipped = reopen(snapshot, name, dry)
    print(f"\n{'Would open' if dry else 'Opening'} ({len(opened)}):")
    for description in opened:
        print(f"   ✅ {description}")
    if skipped:
        print(f"\nNot opened ({len(skipped)}):")
        for reason in skipped:
            print(f"   ·  {reason}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if a != "--dry"]
    if not args:
        sys.exit(__doc__)
    resume(args[0], dry="--dry" in sys.argv)
