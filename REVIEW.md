# Stage — Review from three users (25 Oct 2026)

*Working notes from building Shiori, written while it was still called Stage.*

What Stage is today: a tray app. Ctrl+Alt+S opens a command bar; you speak (Wispr) or type.
"Park" captures every window and browser tab as a draft → drop what you don't want → say a
note → "save as coding". Later "resume coding" reopens folders, apps and tabs (as a named tab
group). Presets: "pin this", "start dsa", and "park dsa" pre-ticks dsa's things.

---

## 1. Arjun — developer (VS Code, Windows Terminal, GitHub, localhost, Docker)

**A normal day:** 2–3 VS Code windows, 4 terminal tabs (dev server, git, a REPL, logs),
GitHub PRs + docs + localhost in Chrome. Switches between a work repo and a side project.

| # | Problem | Why it hurts | Severity |
|---|---|---|---|
| D1 | **Terminals come back empty.** Stage opens a fresh terminal, not the folder or the command that was running (`npm run dev`, `docker compose up`). | The dev server is the first thing he restarts every time; Stage skips the most annoying part. | High |
| D2 | **No git context.** The note doesn't say which branch or what's uncommitted. | "Where was I" for a developer *is* the branch + the diff. | High |
| D3 | **Window layout is lost.** Everything reopens wherever Windows puts it. | Devs live in a fixed layout (editor left, browser right, terminal on monitor 2). | Medium |
| D4 | **Cursor / Windsurf / JetBrains / WSL folders aren't restored.** Only VS Code + local folders. | Many devs moved to Cursor; WSL folders are common. | Medium |
| D5 | **Keyboard flow is second class.** No ↑↓/Space in the park list, no Tab completion of park names, no CLI (`stage park coding`). | In an open office, or at 1 am, he types. He'd also script it. | Medium |
| D6 | **Parking doesn't clear the desk.** Everything stays open after "save". | Switching task still means closing 15 windows by hand. | Medium |
| D7 | **The draft is long.** With 40 tabs the list is a wall; the panel caps at ~10 rows and scrolls. | Choosing takes longer than the switch it saves. | Medium |

**Fits his workflow if:** park takes <5 s, resume brings back terminals in the right folders
with the right commands, and he never has to touch the mouse.

---

## 2. Priya — student (Chrome, PDFs, YouTube lectures, Notion, WhatsApp Web)

**A normal day:** a lecture on YouTube, 2 PDFs (slides + textbook), Notion notes, the
college portal, ChatGPT/Claude, and WhatsApp Web + Spotify always open.

| # | Problem | Why it hurts | Severity |
|---|---|---|---|
| S1 | **Install is impossible for her.** Python, a venv, a terminal command, Chrome "Developer mode → Load unpacked". | She stops at step 1. Today only a developer can install Stage. | Blocker |
| S2 | **Chat and music get parked every time.** WhatsApp, Spotify, Discord, YouTube Music start ticked. | She drops the same 4 things on every park; it feels like chores. | High |
| S3 | **PDFs don't come back.** Edge/Acrobat PDFs are only "noted", not reopened. | Half her study session *is* the PDF (and the page she was on). | High |
| S4 | **Lecture position is lost.** The YouTube tab reopens at 0:00. | "Resume" that loses her place in a 90-min lecture isn't resume. | Medium (great demo) |
| S5 | **Words she doesn't know.** "Park", "preset", "pin", "draft". No first-run guide; commands are guessed from the placeholder. | Undiscoverable → she uses 2 of 10 features. | High |
| S6 | **Naming is friction.** She must invent a name every time ("test parking 1"). | A suggested name ("DBMS · YouTube + 2 PDFs") would be one word: "save". | Medium |
| S7 | **Voice-only hints.** If she doesn't have Wispr, nothing tells her typing works the same. | Wispr is optional, but the UI implies it isn't. | Low |

**Fits her workflow if:** a one-click installer, sensible defaults (never park chat/music),
PDFs and lecture time come back, and the bar teaches her the 3 commands she needs.

---

## 3. Meera — business analyst (Excel, PowerPoint, Outlook, Teams, SharePoint)

**A normal day:** 3 Excel workbooks for 2 clients, a PowerPoint deck, Outlook, Teams, a
SharePoint folder, a CRM in Edge. Clients = her "parks".

| # | Problem | Why it hurts | Severity |
|---|---|---|---|
| B1 | **Excel / PowerPoint files don't reopen.** Office apps are skipped ("not reopened yet"). | Excel is her whole job; Stage restores nothing that matters to her. | Blocker |
| B2 | **IT won't allow it.** Unsigned exe, a developer-mode extension, a local web server on 47321/47322. | Corporate laptops block all three; she can't even try it. | Blocker (for this user) |
| B3 | **Privacy.** Window titles (email subjects, client file names) are stored in plain JSON; a log file mentions them too. | Client data on disk without her knowing = a compliance question. | High |
| B4 | **Teams / Outlook get parked.** Calls and the inbox aren't "a task". | Resuming a client shouldn't open a Teams call window. | Medium |
| B5 | **Voice at the desk.** In an open-plan office she won't talk to her PC. | Keyboard must do everything, comfortably. | Medium |
| B6 | **No search.** "Which client park had the Q3 margin note?" | Notes become a diary; a diary needs search. | Low |
| B7 | **Multi-monitor.** Workbook on screen 2, deck on screen 1 — layout lost. | Same as D3, higher stakes. | Medium |

**Fits her workflow if:** Office files (even the sheet she was on) reopen, nothing leaves or
logs sensitive titles, and it installs like any other app.

---

## 4. Problems all three hit (design and usability)

| # | Problem | Fix |
|---|---|---|
| U1 | One text box does everything; you must know the words. | Visible action chips per screen (Park · Show parks · Start…), and **Tab-to-complete** park names. |
| U2 | Auto-run after a paste is invisible: you can't tell it will run in 1.2 s. | A **countdown line** under the input; any key cancels it. |
| U3 | The UI jumps: the window resizes and content pops in. | Grow the window first, then animate content in; shrink after animating out. |
| U4 | Rows show a coloured letter, not the app. | Real app icons (from each .exe) and site favicons. |
| U5 | Long lists, no structure. | **Collapsible groups** (Apps / Chrome window 1…), a group checkbox, counts. |
| U6 | Resume shows a finished card instantly; you don't see things opening. | Pills appear one by one with a small spinner → ✓. |
| U7 | No undo. | "Undo" on resume (close what just opened) and on delete (from trash). |
| U8 | Steps on the resume card are decorative. | Tick them ("done 1"), saved for next time. |
| U9 | Motion everywhere would be tiring. | Short, purposeful motion; respect **reduce motion** in Windows. |

---

## 5. Improvement plan (deadline Sat 31 Oct)

**Now (today): design + quick wins**
1. Redesigned bar with an animation system (open, view change, paste countdown, row toggles, save, resume progress, list selection). Reduced-motion aware. → U2 U3 U6 U9
2. Collapsible groups with a group checkbox, ↑↓ + Space in lists, Tab-complete names. → U1 U5 D5
3. **Never-park defaults**: chat, music and calls start unticked (WhatsApp, Discord, Spotify, Teams, Zoom, YouTube Music, Netflix…). → S2 B4

**Next (Mon–Wed): what each user is missing most**
4. Terminals: save each terminal's folder (+ optionally a command) and reopen it there. → D1
5. Git line in the note: branch + "3 files changed". → D2
6. Excel / Word / PowerPoint files via Office COM (+ active sheet). → B1
7. PDFs: reopen the file (title → Recent files). → S3
8. YouTube: save `t=` seconds, reopen at that time. → S4
9. Suggested park name from what's ticked. → S6
10. "Park and clear" + Undo on resume. → D6 U7

**Before submitting (Thu–Fri)**
11. `Stage.exe` (no Python needed) + README install in 3 steps. → S1
12. First-run card: hotkey, 3 commands, "typing works too". → S5 S7
13. Privacy: option to store titles hashed/hidden, log without titles. → B3

**Later (after the challenge)**
Window layout (D3 B7), Cursor/JetBrains/WSL (D4), CLI (D5), search across notes (B6),
Chrome Web Store listing + signed installer (S1 B2).
