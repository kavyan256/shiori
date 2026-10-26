# Changelog

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
