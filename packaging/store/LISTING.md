# Publishing the Shiori extension

The extension only works with the Shiori desktop app, so say that up front: reviewers reject
extensions that look broken on their own.

Build the zips first:

    .venv\Scripts\python packaging\pack_extension.py

## Chrome Web Store (also covers Brave and Opera users)

1. Register at https://chrome.google.com/webstore/devconsole (one-time developer fee).
2. New item: upload `dist/shiori-chrome.zip`.
3. Paste the text below. Screenshots are in this folder.
4. After approval, put the store link in `CHROME_STORE` in `main.py`, so "Set up browser tabs…"
   opens the store instead of the Developer mode steps. Then update the README's known limits.

Edge has its own free store, https://partner.microsoft.com/dashboard/microsoftedge, which takes the same zip.

## Firefox Add-ons

1. Sign in at https://addons.mozilla.org/developers/ (free).
2. Submit `dist/shiori-firefox.zip`, listed on the site or "on your own".
3. Mozilla asks for source only if code is minified, and this isn't.

Test it in a real Firefox before submitting: until then this package has never been run.
Open `about:debugging`, "This Firefox", "Load Temporary Add-on", and pick `manifest.json` from
the unzipped package. Needs Firefox 139 or later for tab groups.

## Listing text

**Name:** Shiori

**Category:** Productivity (Workflow & Planning)

**Short description (132 characters at most):**

Companion to the Shiori desktop app: save your browser tabs with your whole desk, and reopen them as a named tab group.

**Description:**

Shiori is a free Windows app that bookmarks your whole desk by voice. Say "save my desk" and it keeps every
window, tab, terminal and file you have open, with a spoken note on where you were. Say "resume" days later,
and it all comes back.

This extension is its link to your browser. It needs the Shiori app to be running on your PC:
https://kavyan256.github.io/shiori

With it:
- Every tab in every window is saved, not just the one in front
- Tabs reopen together as a tab group named after your desk
- YouTube videos come back at the minute you left them

Everything stays on your PC. The extension only talks to the Shiori app at 127.0.0.1. No account, no tracking.
Open source: https://github.com/kavyan256/shiori

**Privacy policy:** https://kavyan256.github.io/shiori/privacy.html

## Answers for the review form

**Single purpose:** Lets the Shiori desktop app save the user's open tabs and reopen them as a named tab group.

**Why each permission is needed:**

| Permission | Why |
|---|---|
| `tabs` | Read the title and address of open tabs so the app can save them, and open them again on resume. |
| `tabGroups` | Reopen saved tabs as one group named after the desk, and close that group on undo. |
| `alarms` | Reconnect to the desktop app every 30 seconds if it started after the browser. |
| `scripting` | Read the current time of a YouTube video, so it can reopen at the same minute. |
| Host `127.0.0.1:47321` | Talk to the Shiori desktop app on the same computer. No other computer is contacted. |
| Host `youtube.com` | Needed by `scripting` to read the video's time. Nothing else on the page is read. |

**Remote code:** No. All code is in the package.

**Data use:** The extension handles website content (tab titles and addresses) and sends it only to the desktop
app on the same computer. It is not sold, not transferred to third parties, and not used for anything else.
