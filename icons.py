"""Real icons for the lists: Chrome's logo for Chrome, a folder for Explorer, the Excel
icon for a .xlsx. Windows hands them over; they're turned into small PNGs the bar can show.

  for_item(item)  -> "data:image/png;base64,…", or "" (the bar then shows a letter instead)

Files and folders get the icon of their *type* (what Explorer shows for .xlsx), worked
out from the name alone: the file itself is never opened, so a file on an offline
network drive can't slow this down. Every icon is made once and remembered.
"""
import base64
import ctypes
import io
import os
import shutil
from ctypes import wintypes
from functools import lru_cache

from PIL import Image

SIZE = 32  # drawn at 32 px, shown at 20: sharp at 125-175% display scaling too

shell32, user32, gdi32 = ctypes.windll.shell32, ctypes.windll.user32, ctypes.windll.gdi32
SHGFI_ICON, SHGFI_LARGEICON, SHGFI_USEFILEATTRIBUTES = 0x100, 0x0, 0x10
FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_NORMAL = 0x10, 0x80
DI_NORMAL = 0x3


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", wintypes.HICON), ("iIcon", ctypes.c_int), ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260), ("szTypeName", wintypes.WCHAR * 80)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


shell32.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(SHFILEINFOW), wintypes.UINT,
                                   wintypes.UINT]
shell32.SHGetFileInfoW.restype = ctypes.c_void_p
shell32.ExtractIconExW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.HICON),
                                   ctypes.POINTER(wintypes.HICON), wintypes.UINT]
user32.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON, ctypes.c_int, ctypes.c_int,
                              wintypes.UINT, wintypes.HBRUSH, wintypes.UINT]
user32.DestroyIcon.argtypes = [wintypes.HICON]
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC


def _png(hicon):
    """An icon handle -> PNG data URL (keeping its transparency). Frees the handle."""
    if not hicon:
        return ""
    header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), SIZE, -SIZE, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down
    bits = ctypes.c_void_p()
    dc = gdi32.CreateCompatibleDC(None)
    bitmap = gdi32.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    try:
        old = gdi32.SelectObject(dc, bitmap)
        ctypes.memset(bits, 0, SIZE * SIZE * 4)  # start fully transparent
        user32.DrawIconEx(dc, 0, 0, hicon, SIZE, SIZE, 0, None, DI_NORMAL)
        gdi32.SelectObject(dc, old)
        raw = ctypes.string_at(bits, SIZE * SIZE * 4)
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(dc)
        user32.DestroyIcon(hicon)
    image = Image.frombuffer("RGBA", (SIZE, SIZE), raw, "raw", "BGRA", 0, 1)
    if not image.getchannel("A").getbbox():  # an old-style icon with no transparency drawn: all opaque
        image.putalpha(255)
    out = io.BytesIO()
    image.save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


@lru_cache(maxsize=256)
def of_exe(exe):
    """The app's own icon, from its .exe."""
    if not exe or not os.path.isfile(exe):
        return ""
    large = wintypes.HICON()
    if shell32.ExtractIconExW(exe, 0, ctypes.byref(large), None, 1) < 1:
        return ""
    return _png(large.value)


@lru_cache(maxsize=256)
def of_type(name, folder=False):
    """The icon Explorer shows for this kind of file (by its extension) or for a folder.
    Only the name is used: the file isn't touched."""
    info = SHFILEINFOW()
    attributes = FILE_ATTRIBUTE_DIRECTORY if folder else FILE_ATTRIBUTE_NORMAL
    if not shell32.SHGetFileInfoW(name, attributes, ctypes.byref(info), ctypes.sizeof(info),
                                  SHGFI_ICON | SHGFI_LARGEICON | SHGFI_USEFILEATTRIBUTES):
        return ""
    return _png(info.hIcon)


def for_item(item, browser_exe=None):
    """The icon for one row of a desk. browser_exe: browser name -> its .exe (for tabs)."""
    try:
        kind, app = item.get("kind", "window"), item.get("app", "")
        if kind == "file":
            return of_type("x" + os.path.splitext(item.get("path", ""))[1].lower())  # by extension only
        if app == "explorer.exe":
            return of_type("folder", folder=True)
        if kind == "terminal":
            return of_exe(shutil.which(item.get("shell", "powershell.exe")) or "")
        if kind == "tab" and browser_exe:
            return of_exe(browser_exe(item["browser"]))
        return of_exe(item.get("exe", ""))  # Store apps too (Claude): "" if Windows won't share it
    except (OSError, ValueError, KeyError):
        return ""
