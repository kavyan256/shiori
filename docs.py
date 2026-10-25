"""Files shown in a window title: PDFs, text files, images…

Many apps only tell the outside world a file *name*, in their title:
  "DBMS unit 3.pdf - Microsoft Edge"   "*todo.txt - Notepad"   "diagram.png - Paint"
Windows keeps a shortcut to every file you open in your Recent items folder, so the
name leads to the full path. The window then becomes a file item that reopens the
file in the same app:

  {"kind": "file", "app": "msedge.exe", "exe": "C:\\…\\msedge.exe", "path": "C:\\…\\DBMS unit 3.pdf", ...}

Limits: a file opened in a way that skips Recent items (some apps' own file
lists) isn't found and stays a plain window; two files with the same name: the
most recently opened one wins.
"""
import os
import re
import subprocess
from pathlib import Path

import pythoncom
import win32com.client

RECENT = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Recent"
TITLE_APPS = {"notepad.exe", "notepad++.exe", "mspaint.exe", "acrobat.exe", "acrord32.exe",
              "sumatrapdf.exe", "photos.exe", "wordpad.exe"}
BROWSERS = {"msedge.exe", "chrome.exe"}  # a PDF open in the browser's own viewer
MORE_PAGES = re.compile(r" and \d+ more pages?$")  # Edge: "notes.pdf and 2 more pages"


def name_from_title(title, app):
    """'*todo.txt - Notepad' -> 'todo.txt'. Browsers: only PDFs (other tab titles aren't files)."""
    name = MORE_PAGES.sub("", title.split(" - ")[0].lstrip("*").strip())
    if "." not in name or len(name) > 200:
        return None
    if app in BROWSERS and not name.lower().endswith(".pdf"):
        return None
    return name


def recent_files():
    """{file name (lower case): full path} from Recent items, newest first wins."""
    pythoncom.CoInitialize()
    shell = win32com.client.Dispatch("WScript.Shell")
    found = {}
    for link in sorted(RECENT.glob("*.lnk"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            target = shell.CreateShortcut(str(link)).TargetPath
        except Exception:
            continue
        if target and os.path.isfile(target):
            found.setdefault(os.path.basename(target).lower(), target)
    return found


def file_item(window, recent):
    """A plain window -> a file item, if its title names a file we can find; else None."""
    app = window["app"]
    if app not in TITLE_APPS and app not in BROWSERS:
        return None
    name = name_from_title(window["title"], app)
    path = recent.get(name.lower()) if name else None
    if not path:
        return None
    return {"kind": "file", "app": app, "exe": window.get("exe", ""), "path": path, "title": name,
            "where": {}, "where_text": "", "unsaved": window["title"].startswith("*"),
            "group": "FULL", "keep": window.get("keep", True)}


def reopen(f):
    """Open the file in the app it was in (a PDF stays in Edge), or the default app."""
    exe = f.get("exe")
    if exe and os.path.exists(exe) and "\\windowsapps\\" not in exe.lower():
        subprocess.Popen([exe, f["path"]])
    else:
        os.startfile(f["path"])
