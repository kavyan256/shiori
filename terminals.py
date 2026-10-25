"""Terminals: every shell tab, its folder, and the command running in it.

  {"kind": "terminal", "shell": "powershell.exe", "folder": "C:\\…\\ka-OS",
   "command": "npm run dev", "rerun": True, ...}

On resume, all terminals reopen as tabs of one new Windows Terminal window, each in
its folder. Commands are only re-run when they look like a dev server or watcher
(npm run dev, vite, uvicorn, docker compose up…): rerunning anything else, like
`git push` or a script that deletes files, could do damage.

Limits, honestly:
  - An idle PowerShell tab reports the folder it *started* in: PowerShell's `cd`
    doesn't update what Windows sees. A running command reports the right folder.
  - Only shells inside Windows Terminal are found (the Windows 11 default).
"""
import os
import re
import shutil
import subprocess

import psutil
import win32gui
import win32process

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
    """Stage's own process and the ones that started it, so Stage never parks itself."""
    me = psutil.Process()
    return {me.pid} | {p.pid for p in me.parents()}


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
                if name not in SHELLS or shell.parent().name().lower() in SHELLS:
                    continue  # not a shell, or a shell started inside another shell
                folder, command = shell.cwd(), ""
                for child in shell.children():
                    if child.name().lower() in HELPERS or child.pid in skip:
                        continue
                    command = describe(child)
                    folder = child.cwd() or folder  # more accurate than the shell's own
                    break
                out.append(item(name, folder, command))
            except psutil.Error:
                continue  # it closed while we looked, or it's an admin shell
    return out


def item(shell, folder, command):
    place = os.path.basename(folder.rstrip("\\")) or folder
    return {"kind": "terminal", "app": "windowsterminal.exe", "shell": shell, "folder": folder,
            "command": command, "rerun": bool(command and RERUN_OK.match(command)),
            "title": f"{place} · {command}" if command else place, "group": "FULL", "keep": True}


def _shell_args(t):
    """What runs inside the tab: the shell, plus the command if it's one we re-run."""
    shell = t.get("shell", "powershell.exe")
    command = t["command"].replace(";", r"\;") if t.get("rerun") else ""  # wt splits tabs on ';'
    if not command:
        return [shell]
    if shell == "cmd.exe":
        return [shell, "/k", command]
    if shell in ("powershell.exe", "pwsh.exe"):
        return [shell, "-NoExit", "-Command", command]
    return [shell]  # bash etc.: folder only


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
