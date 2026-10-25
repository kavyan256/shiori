"""Excel, Word and PowerPoint files: which are open, and where you were in them.

  {"kind": "file", "app": "excel.exe", "path": "C:\\…\\Q3 margins.xlsx",
   "title": "Q3 margins.xlsx", "where": {"sheet": "Summary", "cell": "B14"}, ...}

Office answers through COM (the same channel Office's own add-ins use) while it's
running. On resume Shiori asks Office to open each file and go back to the same
sheet and cell (Excel) or slide (PowerPoint).

Note: an Office app you started yourself only answers COM after it has lost focus
once. Pressing Ctrl+Alt+S does exactly that, so parking sees your files.

Limits: files never saved ("Book1") have no path, so they can't be reopened; a file
with unsaved changes reopens as last saved (the draft warns you).
"""
import logging
import os
import subprocess
import threading
import winreg

import pythoncom
import win32com.client
import win32con
import win32gui

log = logging.getLogger("shiori")

APPS = {  # exe -> (COM name, list of open files)
    "excel.exe": ("Excel.Application", "Workbooks"),
    "winword.exe": ("Word.Application", "Documents"),
    "powerpnt.exe": ("PowerPoint.Application", "Presentations"),
}


def _where(exe, doc):
    """The sheet + cell, or slide, you were on. Best effort: Office can refuse while busy."""
    try:
        if exe == "excel.exe":
            cell = doc.Windows(1).ActiveCell.Address  # "$B$14" (COM hands back the text)
            return {"sheet": doc.ActiveSheet.Name, "cell": cell.replace("$", "")}
        if exe == "powerpnt.exe":
            return {"slide": doc.Windows(1).View.Slide.SlideIndex}
    except Exception:
        pass
    return {}


def _describe_where(where):
    if "sheet" in where:
        return f"{where['sheet']}!{where['cell']}"
    if "slide" in where:
        return f"slide {where['slide']}"
    return ""


def current():
    """Every file open in Excel, Word and PowerPoint right now (only apps that are running)."""
    pythoncom.CoInitialize()
    out = []
    for exe, (com_name, collection) in APPS.items():
        try:
            app = win32com.client.GetActiveObject(com_name)
            docs = list(getattr(app, collection))
        except Exception:
            continue  # not running, or busy (e.g. you're typing in a cell)
        for doc in docs:
            try:
                path = doc.FullName
                if "\\" not in path and "://" not in path:
                    continue  # never saved: nothing to reopen
                where = _where(exe, doc)
                out.append({
                    "kind": "file", "app": exe, "path": path, "title": doc.Name, "where": where,
                    "where_text": _describe_where(where), "unsaved": not bool(doc.Saved),
                    "group": "FULL", "keep": True,
                })
            except Exception:
                continue
    return out


def close(path):
    """Close an open Office file if it has no unsaved changes. True if closed."""
    pythoncom.CoInitialize()
    for exe, (com_name, collection) in APPS.items():
        try:
            app = win32com.client.GetActiveObject(com_name)
            for doc in list(getattr(app, collection)):
                if doc.FullName.lower() == path.lower():
                    if not doc.Saved:
                        return False  # never throw away your edits
                    if exe == "powerpnt.exe":
                        doc.Close()  # PowerPoint's Close takes no arguments
                    else:
                        doc.Close(False)  # False: don't save (there's nothing to save)
                    return True
        except Exception:
            continue
    return False


def exe_path(exe):
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as key:
                return winreg.QueryValue(key, None)
        except OSError:
            continue
    return None


def reopen(f):
    """Reopen the file at the same sheet and cell / slide. Runs in the background:
    Office can take several seconds to open a file and the bar shouldn't wait."""
    threading.Thread(target=_open_in_office, args=(f,), daemon=True).start()


def _open_in_office(f):
    """Ask Office itself to open the file, then go to the same place.

    Why not just run EXCEL.EXE <file>: an Office app started that way only becomes
    reachable over COM after it first loses focus, so Shiori couldn't select the
    sheet/cell. Opening through COM avoids that. Launching the .exe stays as a fallback.
    """
    pythoncom.CoInitialize()
    com_name, collection = APPS[f["app"]]
    try:
        try:
            app = win32com.client.GetActiveObject(com_name)  # already running
        except Exception:
            app = win32com.client.Dispatch(com_name)  # start it
        app.Visible = True
        doc = getattr(app, collection).Open(f["path"])
        where = f.get("where") or {}
        if "sheet" in where:
            doc.Worksheets(where["sheet"]).Activate()
            app.Range(where["cell"]).Select()
        elif "slide" in where:
            doc.Windows(1).View.GotoSlide(where["slide"])
        _bring_forward(app)
    except Exception as e:
        log.info("office: opening %s through COM failed (%s), launching the app instead", f["title"], e)
        exe = exe_path(f["app"])
        if exe:
            subprocess.Popen([exe, f["path"]])
        elif os.path.exists(f["path"]):
            os.startfile(f["path"])


def _bring_forward(app):
    """Office opened it, maybe behind other windows: ask for the front (Windows may refuse)."""
    try:
        hwnd = getattr(app, "Hwnd", None) or getattr(app, "HWND", None) or app.ActiveWindow.Hwnd
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
