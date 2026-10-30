"""Shiori: lives in the system tray, pops up on its hotkey (Ctrl+Alt+S unless you changed it), and you talk to it.

  "Save my desk"                  start with every window and tab open
  "drop 3" / "drop youtube"       leave things out (or click them)
  "I was fixing X, next do Y"     your note for when you come back
  "Save as coding"                name it and save
  "Show my desks" · "View coding" · "Resume coding" · "Delete coding"

Run without a console:  .venv\\Scripts\\pythonw.exe main.py
Run with logs visible:  .venv\\Scripts\\python.exe main.py
"""
import ctypes
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

import psutil
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

import autosave
import browser
import desk
import onboarding
import paths
import psprofile
import settings
import store
import terminals
import updates
from controller import Controller
from version import VERSION

APP_DIR = paths.APP_DIR
TITLE = "Shiori"
MODIFIERS = {"Ctrl": win32con.MOD_CONTROL, "Alt": win32con.MOD_ALT, "Shift": win32con.MOD_SHIFT}
MOD_NOREPEAT = 0x4000  # holding the keys down doesn't fire it again and again
WM_CHANGE_HOTKEY = win32con.WM_APP + 1  # sent to the hotkey thread when you pick another hotkey
WIDTH, MIN_HEIGHT, MAX_HEIGHT = 680, 150, 640
STARTUP_LINK = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup\Shiori.lnk"
OLD_STARTUP_LINK = STARTUP_LINK.with_name("Stage.lnk")  # from before the app was called Shiori

log = logging.getLogger("shiori")
window = None
note_window = None  # the full-screen note shown after a resume
NOTE_TITLE = "Shiori note"
NOTE_DELAY = 2.5    # seconds after a resume: windows have started opening behind it
icon = None
controller = Controller()
hotkey_thread = 0   # the thread that owns the hotkey (Windows sends it WM_HOTKEY)
hotkey_label = ""   # the hotkey actually registered right now, e.g. "Ctrl+Alt+S"


# --- What the page can call: pywebview.api.<name>(...) ----------------------------
class Api:
    def _safe(self, fn, *args):
        """Never let an error leave the bar stuck: log it and show it."""
        try:
            return fn(*args)
        except Exception:
            log.error("Error in %s%r\n%s", fn.__name__, args, traceback.format_exc())
            return {"view": "message", "title": "Sorry, that didn't work",
                    "lines": ["Shiori ran into a problem and stopped there. Your saved desks are safe.",
                              {"text": "Try again, or show my desks", "say": "show my desks"},
                              f"The details are in the log, for a bug report: {log_path()}"]}

    def submit(self, text):
        log.info("said: %r", text)
        view = self._safe(controller.handle, text)
        if view.get("view") == "resume" and view.get("verb") == "Resumed":
            threading.Thread(target=show_note, args=(view,), daemon=True).start()
        return view

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

    def tick_step(self, name, index):
        return self._safe(controller.toggle_step, name, index)

    def blurred(self):
        """You clicked somewhere else: get out of the way. Not if focus is coming
        straight back (our own retries) or went to Wispr Flow while you speak."""
        threading.Thread(target=hide_if_left, daemon=True).start()


class NoteApi:  # what the note page can call
    def dismiss(self):
        note_window.hide()


# --- Showing the bar ---------------------------------------------------------------
def bar_hwnd(title=TITLE):
    """Our own window: titled "Shiori" AND owned by this process. (Title alone isn't
    enough: any app can have a window called "Shiori", e.g. a browser tab.)"""
    found = []

    def check(hwnd, _):
        if win32gui.GetWindowText(hwnd) == title and win32process.GetWindowThreadProcessId(hwnd)[1] == os.getpid():
            found.append(hwnd)

    win32gui.EnumWindows(check, None)
    return found[0] if found else 0


def bring_to_front(hwnd=None):
    """Make the bar (or another of our windows) the active window, so Wispr's paste goes into it.

    SetForegroundWindow can fail silently (Windows only lets the active app hand
    over focus), so check and retry: plain, then borrowing the active window's
    input thread, then tapping Alt. Returns the number of retries, -1 if it failed.
    """
    hwnd = hwnd or bar_hwnd()
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


def active_screen(work_area=False):
    """(left, top, right, bottom) of the screen the mouse is on: with two monitors, Shiori
    opens where you're working, not always on the main one. work_area leaves out the taskbar."""
    monitor = win32api.MonitorFromPoint(win32api.GetCursorPos(), win32con.MONITOR_DEFAULTTONEAREST)
    return win32api.GetMonitorInfo(monitor)["Work" if work_area else "Monitor"]


def show_bar():
    hide_note()
    if not bar_visible():  # the desk before the bar covers it, kept if you save (unless pictures are off)
        controller.desk_shot = desk.grab(bbox=active_screen()) if settings.get("desk_pictures") else None
    hwnd = bar_hwnd()
    if hwnd:  # placed in real screen pixels: right on any monitor, at any display scale
        left, top, right, bottom = active_screen(work_area=True)
        rect = win32gui.GetWindowRect(hwnd)
        x, y = left + (right - left - (rect[2] - rect[0])) // 2, top + int((bottom - top) * 0.18)
        win32gui.SetWindowPos(hwnd, 0, x, y, 0, 0, win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
    window.show()
    retries = bring_to_front()
    focused = window.evaluate_js("Shiori.open()")
    log.info("bar shown: front after %s retries, input focused: %s", retries, focused)


def hide_if_left():
    time.sleep(0.3)
    front = win32gui.GetForegroundWindow()
    if not bar_visible() or front == bar_hwnd():
        return
    try:
        front_app = psutil.Process(win32process.GetWindowThreadProcessId(front)[1]).name().lower()
    except psutil.Error:
        front_app = ""
    if "wispr" in front_app or "flow" in front_app:
        return  # Wispr's own window while you hold your Wispr key: it pastes back into the bar
    log.info("hidden: you clicked into %s", front_app or "another window")
    window.hide()


# --- The note after a resume: your desk dimmed, your words in big type -----------------
def show_note(view):
    """A moment after a resume: hide the bar, picture the screen (everything is reopening
    behind it), and show that picture dimmed with your note on top."""
    time.sleep(NOTE_DELAY)
    window.hide()
    time.sleep(0.3)  # let the bar disappear from the picture
    left, top, right, bottom = screen = active_screen()
    state = {k: view.get(k) for k in ("name", "ago", "note", "steps", "done", "cues")}
    state["backdrop"] = desk.data_url(desk.grab(1600, bbox=screen))
    state["shot"] = desk.data_url(file=view.get("shot", ""))
    note_window.evaluate_js(f"ShioriNote.show({json.dumps(state)})")
    note_window.show()
    hwnd = bar_hwnd(NOTE_TITLE)
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, left, top, right - left, bottom - top, win32con.SWP_SHOWWINDOW)
    bring_to_front(hwnd)  # so a key press reaches it and closes it
    log.info("note shown for %s", view.get("name"))


def hide_note():
    hwnd = bar_hwnd(NOTE_TITLE)
    if hwnd and win32gui.IsWindowVisible(hwnd):
        note_window.hide()


def toggle_bar():
    if bar_visible():
        window.hide()
    else:
        show_bar()


# --- Global hotkey --------------------------------------------------------------------
def hotkey_keys(label):
    """'Ctrl+Alt+S' -> (modifier flags, virtual key) for RegisterHotKey."""
    *mods, key = label.split("+")
    flags = MOD_NOREPEAT
    for m in mods:
        flags |= MODIFIERS[m]
    return flags, win32con.VK_SPACE if key == "Space" else ord(key.upper())


def register_hotkey(label):
    """Take this hotkey; False if another program already has it."""
    global hotkey_label
    try:
        win32gui.RegisterHotKey(None, 1, *hotkey_keys(label))  # returns None, raises if taken
    except pywintypes.error:
        return False
    hotkey_label = label
    return True


def change_hotkey(label):
    """From the tray: save the choice and ask the hotkey thread to swap (only that thread can)."""
    settings.change("hotkey", label)
    win32api.PostThreadMessage(hotkey_thread, WM_CHANGE_HOTKEY, 0, 0)


def swap_hotkey():
    """In the hotkey thread: let go of the old hotkey and take the chosen one. If another
    program has it, keep the old one and say so."""
    global hotkey_label
    old, wanted = hotkey_label, settings.get("hotkey")
    if old == wanted:
        return
    if old:
        ctypes.windll.user32.UnregisterHotKey(None, 1)  # pywin32 has RegisterHotKey but no Unregister
        hotkey_label = ""
    if register_hotkey(wanted):
        log.info("hotkey changed: %s -> %s", old or "none", wanted)
    else:
        log.warning("hotkey %s is taken, keeping %s", wanted, old or "none")
        if old and register_hotkey(old):
            settings.change("hotkey", old)
        win32api.MessageBox(0, f"{wanted} is already used by another program, so Shiori kept "
                               f"{old or 'no hotkey'}. Pick another one in the tray menu, under Hotkey.", TITLE)
    icon.title = f"Shiori · {hotkey_label or 'no hotkey'}"
    icon.update_menu()
    window.evaluate_js(f"Shiori.setHotkey({json.dumps(hotkey_label)})")


def listen_for_hotkey():
    """Own thread: Windows sends WM_HOTKEY to the thread that registered it."""
    global hotkey_thread
    hotkey_thread = win32api.GetCurrentThreadId()
    wanted = settings.get("hotkey")
    if register_hotkey(wanted):
        log.info("ready: press %s", hotkey_label)
    else:
        log.error("%s is already used by another program", wanted)
        win32api.MessageBox(0, f"{wanted} is already used by another program.\n"
                               "Open Shiori from the tray icon, and pick another hotkey there, under Hotkey.", TITLE)
    while True:
        ok, msg = win32gui.GetMessage(None, 0, 0)
        if ok <= 0:
            break
        if msg[1] == WM_CHANGE_HOTKEY:
            try:
                swap_hotkey()
            except Exception:
                log.error("hotkey change failed\n%s", traceback.format_exc())
        elif msg[1] == win32con.WM_HOTKEY:
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
    """A shortcut in the Startup folder runs Shiori at login (pythonw = no console)."""
    if not on:
        STARTUP_LINK.unlink(missing_ok=True)
        return
    if paths.FROZEN:  # packaged Shiori.exe
        target, args = sys.executable, ""
    else:
        target, args = str(Path(sys.executable).with_name("pythonw.exe")), f'"{APP_DIR / "main.py"}"'
    link = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(STARTUP_LINK))
    link.TargetPath, link.Arguments, link.WorkingDirectory = target, args, str(APP_DIR)
    link.Description = "Shiori: save your desk and come back to it, by voice"
    link.Save()


# --- Tray icon ----------------------------------------------------------------------------
def tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill="#7aa2f7")
    draw.text((32, 33), "S", fill="#15171c", font_size=38, anchor="mm")
    return img


def set_desk_pictures(on):
    """Tray: keep a picture of the screen with each save, or not. Turning it off offers to
    delete the pictures already kept."""
    settings.change("desk_pictures", on)
    log.info("desk pictures %s", "on" if on else "off")
    if on or not any(store.SHOTS_DIR.glob("*.jpg")):
        return
    answer = win32api.MessageBox(0, "Desk pictures are off: no new ones will be taken.\n\n"
                                    "Also delete the pictures already kept with your desks?\n"
                                    "(Your desks themselves are not touched.)", TITLE,
                                 win32con.MB_YESNO | win32con.MB_ICONQUESTION)
    if answer == win32con.IDYES:
        log.info("deleted %d desk pictures", store.delete_pictures())


def set_powershell_folders(on):
    """Tray: add or remove the block in your PowerShell profile (see psprofile.py). Asks first."""
    if not on:
        psprofile.turn_off()
        log.info("powershell folders off")
        return
    answer = win32api.MessageBox(0, "Idle PowerShell tabs can't tell Windows when you cd somewhere else, so they "
                                    "can come back in the folder they started in.\n\n"
                                    "To fix that, Shiori adds a small block to your PowerShell profile. At each "
                                    "prompt it notes the tab's folder in a file on this PC. It keeps a backup of "
                                    "your profile, and unticking this removes the block.\n\nAdd it?", TITLE,
                                 win32con.MB_YESNO | win32con.MB_ICONQUESTION)
    if answer != win32con.IDYES:
        return
    blocked = psprofile.turn_on()
    if blocked:
        win32api.MessageBox(0, f"PowerShell's execution policy is {blocked}, so it wouldn't run an edited profile. "
                               "Nothing was changed.\n\nShiori doesn't change this setting for you. To allow it "
                               "yourself, run in PowerShell:\n\n"
                               "Set-ExecutionPolicy -Scope CurrentUser RemoteSigned", TITLE)
    else:
        log.info("powershell folders on")
        win32api.MessageBox(0, "Done. Terminal tabs you open from now on will remember their folder.", TITLE)


def tell_about_update(version):
    log.info("new version out: %s", version)
    icon.notify(f"Shiori {version.lstrip('vV')} is out. Right-click the tray icon to get it.", "Shiori")
    icon.update_menu()


def quit_app():
    log.info("quit")
    autosave.finished()
    icon.stop()
    note_window.destroy()
    window.destroy()


CHROME_STORE = ""  # the extension's store page, once it's published (see packaging/store/LISTING.md)
EXTENSION_HELP = (
    "To let Shiori see your browser tabs, add its extension (one time):\n\n"
    "1. In Chrome or Edge, open chrome://extensions (edge://extensions in Edge)\n"
    "2. Turn on 'Developer mode' (top right)\n"
    "3. Click 'Load unpacked' and pick the folder that just opened:\n   {folder}\n\n"
    "Shiori works without it too: browsers then show only their front tab.")


def set_up_extension():
    """The store page once it's published; until then the extension folder and the 3 steps."""
    if CHROME_STORE:
        webbrowser.open(CHROME_STORE)
        return
    os.startfile(paths.EXTENSION)
    win32api.MessageBox(0, EXTENSION_HELP.format(folder=paths.EXTENSION), "Shiori: browser tabs")


def start_tray():
    global icon
    def hotkey_choice(label):
        return pystray.MenuItem(label, lambda: change_hotkey(label), radio=True,
                                checked=lambda item: hotkey_label == label)

    icon = pystray.Icon("shiori", tray_image(), f"Shiori · {settings.get('hotkey')}", menu=pystray.Menu(
        pystray.MenuItem(lambda item: f"Open  ({hotkey_label or 'no hotkey'})", lambda: show_bar(), default=True),
        pystray.MenuItem("Set up browser tabs…", lambda: threading.Thread(target=set_up_extension, daemon=True).start()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Hotkey", pystray.Menu(*map(hotkey_choice, settings.HOTKEYS))),
        pystray.MenuItem("Keep desk pictures", lambda item: threading.Thread(
            target=set_desk_pictures, args=(not settings.get("desk_pictures"),), daemon=True).start(),
            checked=lambda item: settings.get("desk_pictures")),
        pystray.MenuItem("Remember PowerShell folders", lambda item: threading.Thread(
            target=set_powershell_folders, args=(not psprofile.is_on(),), daemon=True).start(),
            checked=lambda item: psprofile.is_on()),
        pystray.MenuItem("Save automatically", lambda item: settings.change("autosave", not settings.get("autosave")),
                         checked=lambda item: settings.get("autosave")),
        pystray.MenuItem("Start with Windows", lambda item: set_start_with_windows(not starts_with_windows()),
                         checked=lambda item: starts_with_windows()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda item: f"Update Shiori to {updates.available().lstrip('vV')}…",
                         lambda: webbrowser.open(updates.RELEASES), visible=lambda item: bool(updates.available())),
        pystray.MenuItem("Check for updates daily", lambda item: settings.change("check_updates", not settings.get("check_updates")),
                         checked=lambda item: settings.get("check_updates")),
        pystray.MenuItem(f"Shiori {VERSION}", None, enabled=False),
        pystray.MenuItem("Quit Shiori", lambda: quit_app()),
    ))
    icon.run_detached()


# --- Startup --------------------------------------------------------------------------------
def log_path():
    return store.DATA_DIR.parent / "shiori.log"


def setup_logging():
    log_path().parent.mkdir(parents=True, exist_ok=True)
    # at most ~2 MB on disk: the log rolls over at 1 MB and keeps one old copy
    handlers = [logging.handlers.RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=1, encoding="utf-8")]
    if sys.stdout:  # pythonw has no console
        sys.stdout.reconfigure(encoding="utf-8")
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)


def only_one_copy():
    """A named lock: if another Shiori holds it, this copy steps aside."""
    global _lock
    _lock = win32event.CreateMutex(None, False, "Local\\Shiori-park-and-resume")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        win32api.MessageBox(0, f"Shiori is already running.\nPress {settings.get('hotkey')}, or use the tray icon.", TITLE)
        sys.exit(0)


def tabs_arrived(browser_name):
    """Called by the bridge after every tab report: if a draft on screen is still
    missing that browser's tabs, fill them in."""
    if not bar_visible():
        return
    view = controller.tabs_arrived(browser_name)
    if view:
        window.evaluate_js(f"Shiori.show({json.dumps(view)})")


def tidy_up():
    """At start: empty old trash, remove desk pictures no desk uses (see store.tidy)."""
    try:
        trash, pictures = store.tidy()
        terminals.tidy()
        if trash or pictures:
            log.info("tidied: %d old deleted desks, %d unused desk pictures", trash, pictures)
    except OSError as e:
        log.info("tidy skipped: %s", e)


def health_log(every=3600):
    """One line an hour: memory and handles, so a slow leak over days shows in the log."""
    me = psutil.Process()
    while True:
        time.sleep(every)
        family = [me, *me.children(recursive=True)]  # WebView2 runs as child processes
        total = 0
        for p in family:
            try:
                total += p.memory_full_info().uss  # memory only Shiori uses (shared DLLs not counted twice)
            except psutil.Error:
                pass
        log.info("health: %.0f MB across %d processes, %d handles, up %.1f h", total / 2**20, len(family),
                 me.num_handles(), (time.time() - me.create_time()) / 3600)


def on_started():
    if OLD_STARTUP_LINK.exists():  # started with Windows as "Stage": keep that, under the new name
        OLD_STARTUP_LINK.unlink()
        set_start_with_windows(True)
    first = onboarding.first_run()
    onboarding.start(has_parks=bool(store.list_stages()))
    browser.on_report = tabs_arrived
    browser.start()
    threading.Thread(target=listen_for_hotkey, daemon=True).start()
    threading.Thread(target=tidy_up, daemon=True).start()
    autosave.at_start()
    threading.Thread(target=autosave.keep_saving, daemon=True).start()
    threading.Thread(target=health_log, args=(float(os.environ.get("SHIORI_HEALTH_EVERY", 3600)),), daemon=True).start()
    start_tray()
    threading.Thread(target=updates.keep_checking, args=(tell_about_update,), daemon=True).start()
    if first:  # say hello: a Windows notification, and the bar opens once with the guide
        log.info("first run: showing the guide")
        try:
            icon.notify(f"Shiori is running in the tray. Press {settings.get('hotkey')} any time.", "Shiori")
        except Exception:
            pass
        threading.Timer(1.5, show_bar).start()


if __name__ == "__main__":
    setup_logging()
    only_one_copy()
    log.info("starting Shiori %s", VERSION)
    window = webview.create_window(
        TITLE, url=str(paths.BUNDLE / "web" / "bar.html"), js_api=Api(),
        width=WIDTH, height=MIN_HEIGHT, frameless=True, on_top=True, hidden=True,
        resizable=False, easy_drag=False, background_color="#15171c",
    )
    note_window = webview.create_window(
        NOTE_TITLE, url=str(paths.BUNDLE / "web" / "overlay.html"), js_api=NoteApi(),
        frameless=True, on_top=True, hidden=True, resizable=False, background_color="#0b0c10")
    webview.start(on_started)
