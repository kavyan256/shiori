"""Step 1: list every open window and sort it into a restore group.

Run:  python capture.py
"""
import ctypes
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

import psutil
import pythoncom
import win32api
import win32com.client
import win32con
import win32gui
import win32process

import limits

# --- Which group each app goes in -------------------------------------------
# FULL  = we can reopen the exact thing inside it (folder, tabs, file, command)
# TITLE = the title usually holds a filename we can look up in Recent files
# SHOT  = we can only relaunch the app, so we keep a screenshot as a cue
# SKIP  = system windows and stuff that isn't "work"
# VS Code and the editors built from it keep the same records, each in its own folder
EDITORS = {"code.exe": "Code", "code - insiders.exe": "Code - Insiders", "cursor.exe": "Cursor",
           "windsurf.exe": "Windsurf"}
FULL_APPS = {
    *EDITORS,                                     # VS Code, Cursor… -> folder
    "explorer.exe",                               # File Explorer -> folder
    "chrome.exe", "msedge.exe", "brave.exe", "opera.exe",  # browser -> tabs (extension)
    "windowsterminal.exe", "cmd.exe",
    "powershell.exe", "pwsh.exe",                 # terminal -> saved command
    "winword.exe", "excel.exe", "powerpnt.exe",   # Office -> file path via COM
}
TITLE_APPS = {
    "notepad.exe", "notepad++.exe", "mspaint.exe",
    "acrobat.exe", "acrord32.exe", "sumatrapdf.exe",
}
SKIP_APPS = {
    "textinputhost.exe", "shellexperiencehost.exe", "searchhost.exe",
    "startmenuexperiencehost.exe", "lockapp.exe", "systemsettings.exe",
}
# Explorer owns the taskbar and desktop too. Only this class is a real folder window.
EXPLORER_FOLDER_CLASS = "CabinetWClass"

DWMWA_CLOAKED = 14  # "hidden but still reported" windows (Store apps, other desktops)


@dataclass
class Window:
    hwnd: int        # Windows' id for the window
    title: str
    app: str         # process name, e.g. "code.exe"
    exe: str         # full path, so we can relaunch it later
    class_name: str
    rect: tuple      # (left, top, right, bottom) in screen pixels
    minimized: bool
    monitor: str     # e.g. "\\\\.\\DISPLAY1"
    group: str = ""
    # What to reopen inside the app: folder paths for VS Code / Explorer (one per tab)
    targets: list = field(default_factory=list)
    # Store-style apps (installed under WindowsApps, e.g. Claude, Terminal) can't be
    # started from their .exe; Windows starts them by this app ID instead
    app_id: str = ""
    maximized: bool = False


def app_id_of(pid):
    """The 'AppUserModelID' of a Store-style app, e.g. 'Claude_pzs8…!Claude'; '' for normal apps."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        length = ctypes.c_uint32(512)
        buffer = ctypes.create_unicode_buffer(length.value)
        if kernel32.GetApplicationUserModelId(handle, ctypes.byref(length), buffer) != 0:
            return ""  # not a packaged app
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def is_cloaked(hwnd):
    value = ctypes.c_int(0)
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value)
    )
    return value.value != 0


def is_real_window(hwnd):
    """A window you'd see on the taskbar: visible, titled, not a tool popup."""
    if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
        return False
    if win32gui.GetWindow(hwnd, win32con.GW_OWNER):  # dialogs owned by another window
        return False
    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    if ex_style & win32con.WS_EX_TOOLWINDOW:
        return False
    return not is_cloaked(hwnd)


def process_of(hwnd):
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        proc = psutil.Process(pid)
        return proc.name().lower(), proc.exe()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        # Admin apps hide their details from normal programs
        return "unknown", ""


def monitor_of(hwnd):
    handle = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    return win32api.GetMonitorInfo(handle)["Device"]


def group_of(win):
    if win.app in SKIP_APPS or win.app == "unknown":
        return "SKIP"
    if win.app == "explorer.exe":
        return "FULL" if win.class_name == EXPLORER_FOLDER_CLASS else "SKIP"
    if win.app in FULL_APPS:
        return "FULL"
    if win.app in TITLE_APPS:
        return "TITLE"
    return "SHOT"


# --- Finding what's open inside VS Code and Explorer ---------------------------
def editor_storage(app="code.exe"):
    """Where VS Code (or Cursor, Windsurf…) keeps its list of open and recent folders."""
    return Path(os.environ["APPDATA"]) / EDITORS[app] / "User" / "globalStorage"


def uri_to_path(uri):
    """'file:///c%3A/Users/x' -> 'c:\\Users\\x'. Remote URIs (WSL, SSH) -> None."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return str(Path(unquote(parsed.path).lstrip("/")))


def vscode_known_folders(app="code.exe"):
    """Folder paths VS Code (or a sibling editor) remembers: open windows, backups, recently opened.

    The window title only says 'file - showme - Visual Studio Code', so we
    match that folder name against these full paths.
    """
    uris = []
    storage_dir = editor_storage(app)
    try:
        storage = json.loads((storage_dir / "storage.json").read_text(encoding="utf-8"))
        state = storage.get("windowsState", {})
        uris.append(state.get("lastActiveWindow", {}).get("folder"))
        uris += [w.get("folder") for w in state.get("openedWindows", [])]
        uris += [f.get("folderUri") for f in storage.get("backupWorkspaces", {}).get("folders", [])]
    except (OSError, json.JSONDecodeError):
        pass
    try:
        # mode=ro so we never lock or change VS Code's own database
        db = sqlite3.connect(f"file:{(storage_dir / 'state.vscdb').as_posix()}?mode=ro", uri=True)
        row = db.execute(
            "SELECT value FROM ItemTable WHERE key = 'history.recentlyOpenedPathsList'"
        ).fetchone()
        db.close()
        if row:
            uris += [e.get("folderUri") for e in json.loads(row[0]).get("entries", [])]
    except sqlite3.Error:
        pass

    paths = [uri_to_path(u) for u in uris if u]
    return list(dict.fromkeys(p for p in paths if p))  # drop duplicates, keep order


def vscode_folder(title, known):
    """Pick the known folder whose name appears in the window title."""
    parts = [p.strip().lower() for p in title.split(" - ")[:-1]]  # drop "Visual Studio Code"
    for part in reversed(parts):  # the folder name sits near the end
        for path in known:
            if Path(path).name.lower() == part:
                return path
    return None


def explorer_folders():
    """{window id: [folder per tab]} for every open File Explorer window."""
    folders = {}
    try:
        pythoncom.CoInitialize()  # COM must be switched on in each thread that uses it
        for shell_win in win32com.client.Dispatch("Shell.Application").Windows():
            path = uri_to_path(shell_win.LocationURL) if shell_win.LocationURL else None
            if path:  # "This PC", "Home" etc. have no path
                folders.setdefault(shell_win.HWND, []).append(path)
    except Exception:  # COM errors shouldn't stop a park
        pass
    return folders


def list_windows():
    """Every real top-level window, top of the stack first."""
    handles = []
    win32gui.EnumWindows(lambda hwnd, _: handles.append(hwnd), None)
    known_folders = {}  # editor -> its remembered folders, read only if that editor is open
    explorer = limits.within(limits.OFFICE_SECONDS, explorer_folders, default={}, what="Explorer folders")

    windows = []
    for hwnd in handles:
        if not is_real_window(hwnd):
            continue
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        if pid == os.getpid():
            continue  # Shiori's own popup isn't part of your work
        app, exe = process_of(hwnd)
        if app in ("python.exe", "pythonw.exe", "shiori.exe", "stage.exe") and win32gui.GetWindowText(hwnd) in ("Shiori", "Shiori note", "Stage"):
            continue  # another copy of Shiori, e.g. its "already running" message
        win = Window(
            hwnd=hwnd,
            title=win32gui.GetWindowText(hwnd),
            app=app,
            exe=exe,
            class_name=win32gui.GetClassName(hwnd),
            rect=win32gui.GetWindowRect(hwnd),
            minimized=bool(win32gui.IsIconic(hwnd)),
            monitor=monitor_of(hwnd),
            maximized=bool(ctypes.windll.user32.IsZoomed(hwnd)),
        )
        win.group = group_of(win)
        if "\\windowsapps\\" in exe.lower():
            win.app_id = app_id_of(pid)
        if win.app in EDITORS:
            if win.app not in known_folders:
                known_folders[win.app] = vscode_known_folders(win.app)
            folder = vscode_folder(win.title, known_folders[win.app])
            win.targets = [folder] if folder else []
        elif win.group == "FULL" and win.app == "explorer.exe":
            win.targets = explorer.get(hwnd, [])
        windows.append(win)
    return windows


LABELS = {
    "FULL": "🟢 Full restore",
    "TITLE": "🟡 File from title",
    "SHOT": "🔴 App + screenshot",
    "SKIP": "⚫ Skipped",
}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # so emoji print in any console
    windows = list_windows()
    for group, label in LABELS.items():
        members = [w for w in windows if w.group == group]
        print(f"\n{label} ({len(members)})")
        for w in members:
            state = " [minimized]" if w.minimized else ""
            print(f"   {w.app:<22} {w.title[:60]}{state}")
            for target in w.targets:
                print(f"   {'':<22} -> {target}")
    print(f"\n{len(windows)} windows found.")
