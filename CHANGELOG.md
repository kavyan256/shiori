# Changelog

## 1.2.0 · 30 Oct 2026

- **Windows come back where they were:** position, size and maximized, on the same monitor. Only windows the resume opened are moved, and if that monitor isn't connected, Windows places the window.
- **Saves itself:** every few minutes Shiori quietly keeps what's open. After a restart or a crash, say *restore last session*. Tray menu → *Save automatically* to turn it off.
- **Search your desks:** *find the TCP notes* or *which desk has the lecture* looks through notes, steps, tabs, folders and files, older versions included.
- **Better terminals:** an activated Python environment (venv or conda) is activated again in PowerShell and cmd, and safe commands re-run in bash tabs too. Tray menu → *Remember PowerShell folders* (off by default, it asks first) brings idle tabs back in the folder you'd moved to.
- **Update notice:** once a day Shiori asks GitHub for the latest version number and tells you if there's a newer one. It never installs anything by itself. Tray menu → *Check for updates daily* to turn it off.
- **Firefox:** the extension has a Firefox package (0.7.0), for store submission. Not tested in Firefox yet.
- Ready for the stores and signing: extension zips (`packaging/pack_extension.py`), listing text, a privacy page, and an optional signing step in the build.

## 1.1.0 · 26 Oct 2026

- **Can't freeze:** Office with a dialog open, or a file on a network drive that's offline, is given up on after a few seconds instead of hanging the bar.
- **Desk pictures setting:** tray menu → *Keep desk pictures*. Turning it off offers to delete the ones kept.
- **Tidies itself:** 10 versions per desk, 30 days of trash, unused pictures removed.
- **Pick your hotkey:** tray menu → *Hotkey* (Ctrl+Alt+S, Ctrl+Alt+D, Ctrl+Alt+K, Ctrl+Shift+Space, Alt+Shift+S).
- **Two monitors:** the bar and your note open on the screen you're working on.
- **More apps:** Brave and Opera tabs (extension 0.6.0); Cursor, Windsurf and VS Code Insiders folders.
- **Real app icons** in the lists.
- **Easier to read:** text contrast passes WCAG AA, nothing smaller than 12px, screen-reader labels, visible keyboard focus.
- **Plain errors:** "Sorry, that didn't work" with a way back, details in the log.
- Messy and half-finished input handled (half words, filler, scraps, repeats).
- Tests in the repo (`pytest`), run on every push. MIT license.

## 1.0.0 · 25 Oct 2026

First release: save your desk by voice (apps, folders, tabs, terminals, Office files, git context) with a note, and resume it later.
