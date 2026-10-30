"""Terminals: every shell tab, its folder, and the command running in it.

  {"kind": "terminal", "shell": "powershell.exe", "folder": "C:\\…\\ka-OS",
   "command": "npm run dev", "rerun": True, "venv": "C:\\…\\.venv", "conda": "", ...}

On resume, all terminals reopen as tabs of one new Windows Terminal window, each in
its folder. Commands are only re-run when they look like a dev server or watcher
(npm run dev, vite, uvicorn, docker compose up…): rerunning anything else, like
`git push` or a script that deletes files, could do damage. An activated Python
environment (venv or conda) is activated again, in PowerShell and cmd.

Limits, honestly:
  - An idle PowerShell tab reports the folder it *started* in: PowerShell's `cd`
    doesn't update what Windows sees. A running command reports the right folder, and so
    does every tab once "Remember PowerShell folders" is on in the tray (see psprofile.py).
  - Only shells inside Windows Terminal are found (the Windows 11 default).
  - An environment activated in bash can't be seen from outside it.
"""
import os
import re
import shutil
import subprocess

import psutil
import win32gui
import win32process

import limits
from psprofile import SHELLS_DIR

SHELLS = {"powershell.exe", "pwsh.exe", "cmd.exe", "bash.exe", "nu.exe"}
HELPERS = {"conhost.exe", "openconsole.exe"}
TERMINAL_WINDOW_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"  # Windows Terminal's main window
# Long-running dev commands that are safe to start again on resume
RERUN_OK = re.compile(
    r"^(?:(?:npm|pnpm|yarn|bun)(?: run)? (?:dev|start|serve|watch|preview)\b"
    r"|npx (?:vite|next dev|nodemon|serve|http-server)\b|(?:next dev|vite|nodemon|astro dev|ng serve)\b"
    r"|python3? -m (?:http\.server|flask run|uvicorn|streamlit run|jupyter)\b"
    r"|(?:uvicorn|flask run|streamlit run|jupyter (?:lab|notebook))\b"
    r"|docker[ -]compose up\b|docker compose up\b|cargo (?:run|watch)\b|go run\b|dotnet (?:run|watch)\b"
    r"|hugo server\b|php artisan serve\b|rails s(?:erver)?\b)", re.I)


def _quote(arg):
    return f'"{arg}"' if " " in arg else arg


def describe(proc):
    """A running process as the command you'd have typed: node …npm-cli.js run dev -> 'npm run dev'."""
    args = proc.cmdline()
    if not args:
        return ""
    exe = os.path.basename(args[0]).lower().removesuffix(".exe")
    if exe == "node" and len(args) > 1:
        script = args[1].replace("\\", "/").lower()
        for tool in ("npm", "npx", "pnpm", "yarn"):
            if f"/{tool}-cli.js" in script or f"/{tool}.js" in script or f"/{tool}/bin" in script:
                return " ".join([tool] + [_quote(a) for a in args[2:]])
    if exe in ("python", "python3", "py"):
        exe = "python"
    return " ".join([exe] + [_quote(a) for a in args[1:]])


def _stage_family():
    """Shiori's own process and the ones that started it, so Shiori never parks itself."""
    me = psutil.Process()
    return {me.pid} | {p.pid for p in me.parents()}


def environment(shell):
    """The Python environment active in a shell. Activating one sets a variable Windows can see."""
    try:
        found = shell.environ()
    except psutil.Error:
        return {}
    conda = found.get("CONDA_DEFAULT_ENV", "")
    return {"venv": found.get("VIRTUAL_ENV", ""), "conda": "" if conda == "base" else conda}


def reported_folder(shell):
    """The folder this PowerShell tab reported, if it's on (see psprofile.py). A file older than
    the process came from a closed tab that had the same process id."""
    path = SHELLS_DIR / f"{shell.pid}.txt"
    try:
        if path.stat().st_mtime < shell.create_time():
            return ""
        folder = path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError, psutil.Error):
        return ""
    return folder if limits.exist([folder], limits.FILE_SECONDS)[folder] else ""


def tidy():
    """Forget the reports of tabs that have closed."""
    if SHELLS_DIR.exists():
        for path in SHELLS_DIR.glob("*.txt"):
            if path.stem.isdigit() and not psutil.pid_exists(int(path.stem)):
                path.unlink(missing_ok=True)


def _terminal_pids():
    """Windows Terminal processes, found through their windows: far faster than
    asking every process on the PC for its name (~0.6 s), and free when none is open."""
    pids = set()
    win32gui.EnumWindows(lambda hwnd, _: pids.add(win32process.GetWindowThreadProcessId(hwnd)[1])
                         if win32gui.GetClassName(hwnd) == TERMINAL_WINDOW_CLASS else None, None)
    return pids


def current():
    """Every shell tab in Windows Terminal right now."""
    hosts = _terminal_pids()
    if not hosts:
        return []
    skip = _stage_family()
    out = []
    for pid in hosts:
        try:
            descendants = psutil.Process(pid).children(recursive=True)
        except psutil.Error:
            continue
        for shell in descendants:
            try:
                name = shell.name().lower()
                parent = shell.parent()
                if name not in SHELLS or not (parent.pid == pid or parent.name().lower() in HELPERS):
                    continue  # a tab's shell is started by the terminal itself; anything deeper isn't a tab
                              # (a shell inside a shell, or the hidden cmd that "npm run dev" starts)
                folder, command = reported_folder(shell) or shell.cwd(), ""
                for child in shell.children():
                    if child.name().lower() in HELPERS or child.pid in skip:
                        continue
                    command = describe(child)
                    folder = child.cwd() or folder  # more accurate than the shell's own
                    break
                out.append(item(name, folder, command, **environment(shell)))
            except psutil.Error:
                continue  # it closed while we looked, or it's an admin shell
    return out


def item(shell, folder, command, venv="", conda=""):
    place = os.path.basename(folder.rstrip("\\")) or folder
    return {"kind": "terminal", "app": "windowsterminal.exe", "shell": shell, "folder": folder,
            "command": command, "rerun": bool(command and RERUN_OK.match(command)), "venv": venv, "conda": conda,
            "title": f"{place} · {command}" if command else place, "group": "FULL", "keep": True}


def _activate(t, script):
    """The activate script of this tab's venv, if it's still there."""
    path = os.path.join(t["venv"], "Scripts", script) if t.get("venv") else ""
    return path if path and limits.exist([path], limits.FILE_SECONDS)[path] else ""


def _shell_args(t):
    """What runs inside the tab: the shell, its Python environment, and the command if it's one we re-run."""
    shell = t.get("shell", "powershell.exe")
    command = t["command"] if t.get("rerun") else ""
    conda = f"conda activate {t['conda']}" if t.get("conda") else ""
    if shell == "cmd.exe":
        script = _activate(t, "activate.bat")
        steps = [f'call "{script}"' if script else conda, command]
        joined = " & ".join(s for s in steps if s)
        return [shell, "/k", joined.replace(";", r"\;")] if joined else [shell]
    if shell in ("powershell.exe", "pwsh.exe"):
        script = _activate(t, "Activate.ps1").replace("'", "''")
        steps = [f"& '{script}'" if script else conda, command]
        joined = "; ".join(s for s in steps if s).replace(";", r"\;")  # wt splits tabs on ';'
        return [shell, "-NoExit", "-Command", joined] if joined else [shell]
    if shell == "bash.exe" and command:  # bash exits when -c ends: carry on as a normal shell
        return [shell, "-lc", f"{command}; exec bash".replace(";", r"\;")]
    return [shell]  # anything else: folder only


def open_all(terminals):
    """Reopen terminals as tabs of one new Windows Terminal window."""
    wt = shutil.which("wt")
    if not wt:  # no Windows Terminal: one console window each
        for t in terminals:
            subprocess.Popen(_shell_args(t), cwd=t["folder"], creationflags=subprocess.CREATE_NEW_CONSOLE)
        return
    args = [wt, "-w", "new"]
    for n, t in enumerate(terminals):
        if n:
            args.append(";")
        title = t["title"].replace(";", ",")  # a ';' would start a new tab
        args += ["new-tab", "-d", t["folder"].rstrip("\\") or "C:\\", "--title", title] + _shell_args(t)
    subprocess.Popen(args)
