"""Stage: lives in the system tray, pops up on Ctrl+Alt+S, and you talk to it.

  "Park"                          start a park with every window and tab open
  "drop 3" / "drop youtube"       leave things out (or click them)
  "I was fixing X, next do Y"     your note for when you come back
  "Save as coding"                name it and save
  "Show my parks" · "View coding" · "Resume coding" · "Delete coding"

Run without a console:  .venv\\Scripts\\pythonw.exe main.py
Run with logs visible:  .venv\\Scripts\\python.exe main.py
"""
import json
import logging
import os
import sys
import threading
import time
import traceback
from pathlib import Path

import pystray
import pywintypes
import webview
import win32api
import win32com.client
import win32con
import win32event
import win32gui
import win32process
import winerror
from PIL import Image, ImageDraw

import browser
import onboarding
import paths
import store
from controller import Controller

APP_DIR = paths.APP_DIR
TITLE = "Stage"
HOTKEY = (win32con.MOD_CONTROL | win32con.MOD_ALT | 0x4000, ord("S"))  # Ctrl+Alt+S, 0x4000 = no repeat
HOTKEY_LABEL = "Ctrl+Alt+S"
WIDTH, MIN_HEIGHT, MAX_HEIGHT = 680, 150, 640
STARTUP_LINK = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup\Stage.lnk"

log = logging.getLogger("stage")
window = None
icon = None
controller = Controller()


# --- What the page can call: pywebview.api.<name>(...) ----------------------------
class Api:
    def _safe(self, fn, *args):
        """Never let an error leave the bar stuck: log it and show it."""
        try:
            return fn(*args)
        except Exception as e:
            log.error("Error in %s%r\n%s", fn.__name__, args, traceback.format_exc())
            return {"view": "message", "title": "Something went wrong",
                    "lines": [f"{type(e).__name__}: {e}", f"Details in {log_path()}"]}

    def submit(self, text):
        log.info("said: %r", text)
        return self._safe(controller.handle, text)

    def opened(self):
        return self._safe(controller.opened)

    def toggle(self, index):
        return self._safe(controller.toggle, index)

    def set_many(self, indexes, keep):
        return self._safe(controller.set_many, indexes, keep)

    def names(self):
        return self._safe(controller.names)

    def resize(self, height):
        window.resize(WIDTH, max(MIN_HEIGHT, min(int(height) + 2, MAX_HEIGHT)))

    def hide(self):
        window.hide()


# --- Showing the bar ---------------------------------------------------------------
def bar_hwnd():
    """Our own window: titled "Stage" AND owned by this process. (Title alone isn't
    enough: any app can have a window called "Stage", e.g. a browser tab.)"""
    found = []

    def check(hwnd, _):
        if win32gui.GetWindowText(hwnd) == TITLE and win32process.GetWindowThreadProcessId(hwnd)[1] == os.getpid():
            found.append(hwnd)

    win32gui.EnumWindows(check, None)
    return found[0] if found else 0


def bring_to_front():
    """Make the bar the active window so Wispr's paste goes into it.

    SetForegroundWindow can fail silently (Windows only lets the active app hand
    over focus), so check and retry: plain, then borrowing the active window's
    input thread, then tapping Alt. Returns the number of retries, -1 if it failed.
    """
    hwnd = bar_hwnd()
    for attempt in range(5):
        if win32gui.GetForegroundWindow() == hwnd:
            return attempt
        front = win32gui.GetForegroundWindow()
        front_thread = win32process.GetWindowThreadProcessId(front)[0] if front else 0
        this_thread = win32api.GetCurrentThreadId()
        attach = attempt >= 1 and front_thread and front_thread != this_thread
        try:
            if attach:
                win32process.AttachThreadInput(this_thread, front_thread, True)
            if attempt >= 2:
                win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        except pywintypes.error:
            pass
        finally:
            if attach:
                win32process.AttachThreadInput(this_thread, front_thread, False)
        time.sleep(0.03)
    return -1


def bar_visible():
    hwnd = bar_hwnd()
    return bool(hwnd and win32gui.IsWindowVisible(hwnd))


def show_bar():
    screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
    screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
    window.move((screen_w - WIDTH) // 2, int(screen_h * 0.18))
    window.show()
    retries = bring_to_front()
    focused = window.evaluate_js("Stage.open()")
    log.info("bar shown: front after %s retries, input focused: %s", retries, focused)


def toggle_bar():
    if bar_visible():
        window.hide()
    else:
        show_bar()


# --- Global hotkey --------------------------------------------------------------------
def listen_for_hotkey():
    """Own thread: Windows sends WM_HOTKEY to the thread that registered it."""
    try:
        win32gui.RegisterHotKey(None, 1, *HOTKEY)  # returns None, raises if taken
    except pywintypes.error:
        log.error("%s is already used by another program", HOTKEY_LABEL)
        win32api.MessageBox(0, f"{HOTKEY_LABEL} is already used by another program.\n"
                               "Stage is running in the tray; open it from the tray icon.", TITLE)
        return
    log.info("ready: press %s", HOTKEY_LABEL)
    while True:
        ok, msg = win32gui.GetMessage(None, 0, 0)
        if ok <= 0:
            break
        if msg[1] == win32con.WM_HOTKEY:
            log.info("hotkey pressed (bar %s)", "open" if bar_visible() else "hidden")
            onboarding.mark("hotkey")  # guide step 1: you found the hotkey
            try:
                toggle_bar()
            except Exception:
                log.error("toggle failed\n%s", traceback.format_exc())


# --- Start with Windows -----------------------------------------------------------------
def starts_with_windows():
    return STARTUP_LINK.exists()


def set_start_with_windows(on):
    """A shortcut in the Startup folder runs Stage at login (pythonw = no console)."""
    if not on:
        STARTUP_LINK.unlink(missing_ok=True)
        return
    if paths.FROZEN:  # packaged Stage.exe
        target, args = sys.executable, ""
    else:
        target, args = str(Path(sys.executable).with_name("pythonw.exe")), f'"{APP_DIR / "main.py"}"'
    link = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(STARTUP_LINK))
    link.TargetPath, link.Arguments, link.WorkingDirectory = target, args, str(APP_DIR)
    link.Description = "Stage: park and resume your work by voice"
    link.Save()


# --- Tray icon ----------------------------------------------------------------------------
def tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill="#7aa2f7")
    draw.text((32, 33), "S", fill="#15171c", font_size=38, anchor="mm")
    return img


def quit_app():
    log.info("quit")
    icon.stop()
    window.destroy()


EXTENSION_HELP = (
    "To let Stage see your browser tabs, add its extension (one time):\n\n"
    "1. In Chrome or Edge, open chrome://extensions (edge://extensions in Edge)\n"
    "2. Turn on 'Developer mode' (top right)\n"
    "3. Click 'Load unpacked' and pick the folder that just opened:\n   {folder}\n\n"
    "Stage works without it too: browsers then show only their front tab.")


def set_up_extension():
    """Open the extension folder and show the 3 steps (the Web Store needs a review first)."""
    os.startfile(paths.EXTENSION)
    win32api.MessageBox(0, EXTENSION_HELP.format(folder=paths.EXTENSION), "Stage: browser tabs")


def start_tray():
    global icon
    icon = pystray.Icon("stage", tray_image(), f"Stage · {HOTKEY_LABEL}", menu=pystray.Menu(
        pystray.MenuItem(f"Open  ({HOTKEY_LABEL})", lambda: show_bar(), default=True),
        pystray.MenuItem("Set up browser tabs…", lambda: threading.Thread(target=set_up_extension, daemon=True).start()),
        pystray.MenuItem("Start with Windows", lambda item: set_start_with_windows(not starts_with_windows()),
                         checked=lambda item: starts_with_windows()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Stage", lambda: quit_app()),
    ))
    icon.run_detached()


# --- Startup --------------------------------------------------------------------------------
def log_path():
    return store.DATA_DIR.parent / "stage.log"


def setup_logging():
    log_path().parent.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(log_path(), encoding="utf-8")]
    if sys.stdout:  # pythonw has no console
        sys.stdout.reconfigure(encoding="utf-8")
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)


def only_one_copy():
    """A named lock: if another Stage holds it, this copy steps aside."""
    global _lock
    _lock = win32event.CreateMutex(None, False, "Local\\Stage-park-and-resume")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        win32api.MessageBox(0, f"Stage is already running.\nPress {HOTKEY_LABEL}, or use the tray icon.", TITLE)
        sys.exit(0)


def tabs_arrived(browser_name):
    """Called by the bridge after every tab report: if a draft on screen is still
    missing that browser's tabs, fill them in."""
    if not bar_visible():
        return
    view = controller.tabs_arrived(browser_name)
    if view:
        window.evaluate_js(f"Stage.show({json.dumps(view)})")


def on_started():
    first = onboarding.first_run()
    onboarding.start(has_parks=bool(store.list_stages()))
    browser.on_report = tabs_arrived
    browser.start()
    threading.Thread(target=listen_for_hotkey, daemon=True).start()
    start_tray()
    if first:  # say hello: a Windows notification, and the bar opens once with the guide
        log.info("first run: showing the guide")
        try:
            icon.notify(f"Stage is running in the tray. Press {HOTKEY_LABEL} any time.", "Stage")
        except Exception:
            pass
        threading.Timer(1.5, show_bar).start()


if __name__ == "__main__":
    setup_logging()
    only_one_copy()
    log.info("starting")
    window = webview.create_window(
        TITLE, url=str(paths.BUNDLE / "web" / "bar.html"), js_api=Api(),
        width=WIDTH, height=MIN_HEIGHT, frameless=True, on_top=True, hidden=True,
        resizable=False, easy_drag=False, background_color="#15171c",
    )
    webview.start(on_started)
