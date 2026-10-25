# Stage — Plan v2

*Working notes from building Shiori, written while it was still called Stage.*

> **Park your work by voice. Resume exactly where your head was.**

For: **No Hands: The Wispr Challenge** (WeMakeDevs × Wispr Flow).
**Deadline: Sat 31 Oct 2026, 11:59 pm IST** (from wemakedevs.org/wispr). Internal target: **Sat 31 Oct, 6 pm.**
Platform: Windows 11, Python 3.11. Input by voice through Wispr Flow. No API keys, everything local.

---

## 0. Where we are (v1, done 24–25 Oct)

| Done | What works |
|---|---|
| `capture.py` | Lists every window, sorts into 🟢🟡🔴⚫, finds VS Code / Explorer folder paths |
| `store.py` | One JSON per Stage, every park kept, fuzzy name matching |
| `restore.py` | Reopens VS Code + Explorer folders and closed apps, skips what's open or dropped |
| `notes.py` | Offline split of a ramble into brain dump + next steps |
| `ui.py` + `main.py` | Ctrl+Alt+S popup, auto-run after Wispr pastes, park / resume / list, drop windows by voice or click |

**What feels crude (your feedback, 25 Oct):**
1. You can't see your history: only the latest park of each Stage shows, not every park with its time.
2. It's a script in a terminal. It should be an app that always runs in the background (like Wispr Flow) and pops up on the shortcut.
3. The UI/UX is basic.
4. One park takes everything. You want to split open windows into separate parks (acads vs coding).
5. You want presets: a DSA / Acads / Game setup you can start any time.

---

## 1. The model, renamed so it's clear

| Word | Means | Example |
|---|---|---|
| **Stage** | A named area of your life/work | `coding`, `acads`, `dsa`, `game` |
| **Park** | One saved moment of a Stage: windows + note + steps + time | "coding · Sun 25 Oct 10:41 · fixing kernel.h" |
| **Preset** | A Stage with **pinned items** that always open, plus **rules** that say which windows belong to it | `dsa` = leetcode.com + VS Code `dsa` folder; anything with "leetcode" belongs here |

A Stage has many parks (its history). A preset is just a Stage with pins + rules, so every Stage can become one.

### Data (v2)
```json
{
  "name": "coding",
  "color": "#7aa2f7",
  "pinned": [
    {"type": "folder", "app": "code", "value": "C:/Users/Kavyan/Desktop/ka-OS"},
    {"type": "url", "value": "https://github.com/kavyan256/ka-OS"}
  ],
  "rules": {"apps": ["code"], "keywords": ["github", "ka-os", "stackoverflow"]},
  "parks": [
    {
      "id": "2026-10-25T10:41:05",
      "note": "I was working on kernel.h",
      "steps": [{"text": "Finish the header", "done": false}, {"text": "Build", "done": false}],
      "windows": [{"app": "code.exe", "title": "...", "targets": ["..."], "keep": true}]
    }
  ]
}
```
A one-time migration turns v1 files (`snapshots`, plain-string steps) into this shape.

---

## 2. The app shell: always running, pops up on the shortcut

| Piece | How | Notes |
|---|---|---|
| **Runs in the background** | Started once, lives in the **system tray** (icon near the clock) | Tray menu: Open dashboard · Pause shortcut · Settings · Quit |
| **No terminal** | Run with `pythonw` now; ship as `Stage.exe` (PyInstaller, no console) | |
| **Starts with Windows** | Shortcut in the Startup folder, toggle in Settings | Off by default |
| **Only one copy** | A named Windows mutex; a second launch just opens the bar | Fixes "hotkey already taken" by your own old copy |
| **Two windows** | **Command bar** (Ctrl+Alt+S): quick voice actions · **Dashboard** (Ctrl+Alt+D or from the bar/tray): browse history, presets, settings | |

### UI tech: **pywebview** (HTML/CSS/JS drawn by Windows' built-in Edge WebView2, Python stays the backend)
- Why: real modern UI (rounded, blur, icons, animation) without rewriting the Python. tkinter can't look good.
- Tray: `pystray`. Hotkey: keep the current `RegisterHotKey` thread.
- **Biggest risk:** does Wispr's paste land in a webview window as reliably as in tkinter? → **First task is a spike to test exactly that.** If it fails, fall back to `customtkinter` (better-looking tkinter).

---

## 3. Features

### 3.1 History: every park, with time
- Dashboard: Stages in a sidebar; picking one shows a **timeline of its parks**: date/time, note, steps (✓ done ones), window chips with app icons.
- **Resume any park**, not only the latest ("resume coding from yesterday" or click).
- Delete a park; tick steps done (saved).
- Command bar "list" becomes a short recent-parks list with arrow-key navigation.

### 3.2 Split parking: many parks from one desktop
Two ways, both voice-first:

**A. One at a time (build first)**
> "Park coding" → window list opens **pre-ticked** with the windows that match `coding` (its rules, or what was in its last park). Everything else unticked.
> Fix with "drop 3" / "add 5" / click → note → saved.
> "Park acads" → the windows already parked in `coding` are greyed "in coding"; acads ones pre-ticked.

**B. Sort everything at once (if time)**
> "Park all" → every window shows a Stage chip guessed from the rules. Say "1, 2 and 4 to coding, 3 and 5 to acads" or click chips. Then one short note per Stage.

Optional "**park and clear**": closes the parked windows afterwards so your desk is clean for the next thing.

### 3.3 Presets
- **Make one:** after a park, say **"pin this"** → its windows become the Stage's pinned items. Edit pins/rules in the Dashboard (add a URL, a folder, an app).
- **Start one:** "start dsa" → opens the pinned items (+ your last dsa park's windows and note, if any).
- **Starter presets** offered on first run: DSA (LeetCode + VS Code folder), Acads (college portal + notes folder + PDF), Game (Steam/Discord). You fill in the folders.
- Rules power the pre-ticking in 3.2.

### 3.4 UI/UX
**Command bar** (Raycast/Spotlight style)
- 680 px, rounded, dark with blur, appears at 20 % from the top with a short fade.
- Input with hint: "Hold Ctrl+Win and speak · park / resume / start / list".
- **Live intent chip** while text lands: `Park → coding`, `Resume → acads` (you see what will happen before it runs).
- Empty input shows recent Stages: name, color dot, last park time, next step. ↑↓ + Enter resumes.

**Park screen**
- Note at the top (brain dump + steps, editable).
- Windows as rows: **app icon**, title, checkbox, number, Stage chip. Dropped rows fade.
- Footer: "Saved 4 · dropped 2 · say drop/add or Esc".

**Resume card**
- Note big, steps as real checkboxes (click or "done 1").
- What opened, with icons, and an **Undo** (closes what Stage just opened).

**Dashboard**
- Sidebar: Stages + presets (color, count of parks). Main: timeline. Tabs: Stages · Presets · Settings.
- Settings: hotkeys, auto-run delay, start with Windows, never-save list (e.g. Spotify, YouTube Music).

**Polish:** app icons extracted from each `.exe`, toasts, keyboard navigation everywhere, light/dark follows Windows.

---

## 4. Still to do from v1 (re-prioritised)

| Item | Priority | Why |
|---|---|---|
| Chrome extension (tabs) | **High** | Acads vs coding is mostly *tabs*; without it splits are weak |
| Screenshots for 🔴 apps | Medium | Good cue on resume, shows well in the demo |
| Terminals (saved commands, git cues) | Medium | Dev server restart is a nice demo moment |
| Title → recent file, Office files | Low | |
| Window layout restore | Low | |

---

## 5. Timeline (25–31 Oct)

| Day | Build | Done when |
|---|---|---|
| **Sun 25** | **Spike:** pywebview command bar + tray + hotkey; test Wispr paste + focus in it | Decide UI tech by tonight |
| **Mon 26** | App shell: tray, single instance, no console, start with Windows; port park/resume/list to the new bar | Runs all day without a terminal |
| **Tue 27** | Data v2 + migration · history timeline · resume any park · Dashboard v1 | You can browse every park |
| **Wed 28** | Split parking (A) · presets: pin this, start, rules pre-tick | Two parks from one desktop; "start dsa" works |
| **Thu 29** | Chrome extension (tabs) · resume Undo · app icons · settings | Tabs split between Stages |
| **Fri 30** | `Stage.exe` + GitHub release · landing page · README · record demo | Someone else can install it |
| **Sat 31** | Buffer, fixes only · **submit by 6 pm** | Submitted |

**If late, cut in this order:** "park all" (3.2 B) → window layout → screenshots → starter presets → dashboard settings tab. Never cut: background app, history, split parking A, presets start, Chrome tabs.

---

## 6. Submission

- The challenge asks for **a public link judges can use without asking you**. A desktop app can't run in a browser, so ship:
  - GitHub repo + **Release with `Stage.exe`** (zip, no install), README with 3 steps and a GIF,
  - landing page (GitHub Pages) with the demo video and download button.
  - ⚠️ Ask in the WeMakeDevs Discord early (Mon) whether a downloadable Windows app counts as a working link.
- Build by voice: dictate prompts, notes and commit messages with Wispr. Upload the usage card.
- Demo (90 s): messy desk → "park coding… drop chrome" → "park acads" → clear → "start dsa" → "resume coding" with note + Undo → dashboard timeline.

## 7. Risks

| Risk | Plan |
|---|---|
| Wispr paste/focus fails in webview | Spike first (Sun); fallback customtkinter |
| Chrome tabs need an extension in the store? | Load unpacked for you; for judges, explain in README (or ship without tabs) |
| Packaging pywebview + pywin32 with PyInstaller | Try on Fri morning, not Fri night |
| Scope (6 days) | Cut order above; daily "done when" checks |
| Judges can't run a Windows app | Video + GIFs carry the demo; ask organisers Monday |
