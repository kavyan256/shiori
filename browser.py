"""Bridge between Shiori and the browser extension. This PC only (127.0.0.1), never the network.

Live link (WebSocket, port 47322), used whenever the browser is open:
  extension -> Shiori   hello / report (every open tab, on every change) / log line
  Shiori -> extension   "report now" (when you say park) / "restore these tabs as a group"
  While connected, the extension stays awake, so Shiori never waits on a sleeping extension.

Plain web server (port 47321), the fallback when the live link isn't up yet:
  POST /tabs, /debug         same reports and log lines over plain HTTP
  GET  /restore/<token>      opened in a browser that was closed; the extension spots it
  GET  /restore/<token>.json and fetches the park's tabs to open as a tab group

Without the extension, tabs can't be seen, and resume opens saved URLs in a new window.
"""
import html
import json
import logging
import os
import secrets
import subprocess
import threading
import time
import winreg
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from websockets.sync.server import serve as serve_websocket

PORT, WS_PORT = 47321, 47322
BASE = f"http://127.0.0.1:{PORT}"
FRESH_FOR = 180  # seconds: the extension reports on every change and every minute
# Chromium browsers the extension runs in (it says which one it's in). Firefox isn't one:
# its extensions work differently, so Firefox shows only its front tab, as a window.
EXE = {"chrome": "chrome.exe", "edge": "msedge.exe", "brave": "brave.exe", "opera": "opera.exe"}
BROWSER_OF_APP = {exe: name for name, exe in EXE.items()}
# Extra browser flags, for testing against a separate browser profile
EXTRA_ARGS = os.environ.get("STAGE_BROWSER_ARGS", "").split()

log = logging.getLogger("shiori")
_lock = threading.Lock()
_new_report = threading.Condition(_lock)
_tabs = {}      # browser -> {"at": time, "count": reports so far, "windows": [...]}
_sockets = {}   # browser -> its live connection
_restores = {}  # one-time token -> {"name", "color", "urls"}
on_report = None  # main.py sets this: called with the browser name after every report


def _save_report(data):
    browser = data.get("browser") if data.get("browser") in EXE else "chrome"
    windows = data["windows"]
    with _new_report:
        count = _tabs.get(browser, {}).get("count", 0) + 1
        _tabs[browser] = {"at": time.time(), "count": count, "windows": windows}
        _new_report.notify_all()
    if on_report:
        on_report(browser)


def _send(browser, message):
    with _lock:
        socket = _sockets.get(browser)
    if not socket:
        return False
    try:
        socket.send(json.dumps(message))
        return True
    except Exception:
        return False


# --- what Shiori asks -----------------------------------------------------------------
def fresh_tabs(open_apps):
    """{browser: windows} for browsers whose extension reported recently AND that have
    a window open right now (open_apps: exe names of open windows, e.g. {"chrome.exe"}).
    A closed browser can't send a last report, so without the second check its old
    tabs would look open for a few minutes. (Checking processes isn't enough:
    Chrome and Edge keep running in the background after you close them.)"""
    now = time.time()
    with _lock:
        for b in [b for b in _tabs if EXE[b] not in open_apps]:
            del _tabs[b]["windows"][:]  # it closed: its last report is history, not what's open
        return {b: r["windows"] for b, r in _tabs.items()
                if now - r["at"] < FRESH_FOR and EXE[b] in open_apps and r["windows"]}


def request_reports(timeout=1.5):
    """Ask every connected browser for its tabs right now and wait (briefly) for the answers.
    Called when you say "park", so the list is exact, not a few seconds old."""
    with _lock:
        connected = list(_sockets)
        before = {b: _tabs.get(b, {}).get("count", 0) for b in connected}
    asked = [b for b in connected if _send(b, {"type": "report"})]
    with _new_report:
        _new_report.wait_for(lambda: all(_tabs.get(b, {}).get("count", 0) > before[b] for b in asked), timeout)


def close_tabs(browser, urls):
    """Ask a connected browser to close these tabs (park and clear). False if not connected."""
    return _send(browser, {"type": "close", "urls": urls})


def close_group(browser, name):
    """Ask a connected browser to close the tab group a resume opened (undo)."""
    return _send(browser, {"type": "close_group", "name": name})


def has_extension(browser):
    with _lock:
        return browser in _tabs or browser in _sockets


def browser_exe(browser):
    """Full path from Windows' App Paths registry, or just the name (Windows may still find it)."""
    name = EXE.get(browser, "chrome.exe")
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}") as key:
                return winreg.QueryValue(key, None)
        except OSError:
            continue
    return name


def open_tabs(browser, urls, park_name):
    """Reopen a park's tabs: as a named tab group via the extension, else a plain new window."""
    if not urls:
        return
    color = sum(map(ord, park_name))  # same color each time
    if _send(browser, {"type": "restore", "name": park_name, "urls": urls, "color": color}):
        return  # browser is open and connected: the extension opens the group directly
    exe = browser_exe(browser)
    if has_extension(browser):
        token = secrets.token_urlsafe(12)
        with _lock:
            _restores[token] = {"name": park_name, "urls": urls, "color": color}
        subprocess.Popen([exe, *EXTRA_ARGS, f"{BASE}/restore/{token}"])
    else:
        subprocess.Popen([exe, *EXTRA_ARGS, "--new-window", *urls])


# --- the server the extension talks to ------------------------------------------------
RESTORE_PAGE = """<!doctype html><meta charset="utf-8"><title>Shiori · reopening tabs</title>
<body style="font:15px Segoe UI,sans-serif;padding:40px;color:#444">
<h2>Shiori is reopening “{name}”…</h2>
<p>If this page stays open, the Shiori extension isn't installed in this browser.
Here are the tabs to open yourself:</p><ul>{links}</ul></body>"""


class Handler(BaseHTTPRequestHandler):
    def allowed(self):
        """Only the extension (or a program on this PC) may talk to us, never a website:
        browsers stamp requests from web pages with an http(s) Origin they can't fake."""
        origin = self.headers.get("Origin", "")
        return not origin.startswith(("http://", "https://"))

    def reply(self, code, body=b"", kind="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in ("/tabs", "/debug") or not self.allowed():
            return self.reply(403)
        length = int(self.headers.get("Content-Length", 0))
        if length > 5_000_000:
            return self.reply(413)
        if self.path == "/debug":  # the extension's own log lines, into shiori.log
            log.info("extension: %s", self.rfile.read(min(length, 2000)).decode("utf-8", "replace"))
            return self.reply(204)
        try:
            data = json.loads(self.rfile.read(length))
            data["windows"]  # must be there
        except (ValueError, KeyError, TypeError):
            return self.reply(400)
        self.reply(204)
        _save_report(data)

    def do_GET(self):
        if not self.path.startswith("/restore/") or not self.allowed():
            return self.reply(404)
        token = self.path[len("/restore/"):].split("?")[0]
        if token.endswith(".json"):  # the extension asking for the tabs: hand them over once
            with _lock:
                park = _restores.pop(token[:-5], None)
            return self.reply(200, json.dumps(park).encode(), "application/json") if park else self.reply(404)
        with _lock:  # the trigger page itself, also a fallback list if the extension is missing
            park = _restores.get(token)
        if not park:
            return self.reply(404, b"This restore link has already been used.")
        links = "".join(f'<li><a href="{html.escape(u)}">{html.escape(u)}</a></li>' for u in park["urls"])
        page = RESTORE_PAGE.format(name=html.escape(park["name"]), links=links)
        self.reply(200, page.encode(), "text/html; charset=utf-8")

    def log_message(self, *args):
        pass  # keep the log quiet; every tab change would be a line


def _only_extensions(connection, request):
    """Refuse websites, same rule as the web server: browsers stamp a page's own
    http(s) address in Origin and a page can't fake it."""
    if request.headers.get("Origin", "").startswith(("http://", "https://")):
        return connection.respond(HTTPStatus.FORBIDDEN, "Only the Shiori extension may connect.\n")
    return None


def _live_link(socket):
    """One browser's live connection: runs for as long as that browser is open."""
    browser = None
    try:
        for message in socket:
            data = json.loads(message)
            kind = data.get("type")
            if kind == "hello":
                browser = data.get("browser") if data.get("browser") in EXE else "chrome"
                with _lock:
                    _sockets[browser] = socket
                log.info("extension connected: %s", browser)
            elif kind == "report":
                _save_report(data)
            elif kind == "log":
                log.info("extension: %s", str(data.get("text"))[:2000])
            # "ping" needs no answer: it only keeps the browser's extension awake
    except Exception as e:
        log.info("extension link closed (%s): %s", browser, type(e).__name__)
    finally:
        with _lock:
            if browser and _sockets.get(browser) is socket:
                del _sockets[browser]


def start():
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        live = serve_websocket(_live_link, "127.0.0.1", WS_PORT, process_request=_only_extensions)
    except OSError:
        log.error("port %s or %s is busy: browser tabs won't be visible", PORT, WS_PORT)
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=live.serve_forever, daemon=True).start()
    log.info("browser bridge on %s (live link on port %s)", BASE, WS_PORT)
