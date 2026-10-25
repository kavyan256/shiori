"""Doing what you said. Knows nothing about windows or HTML: every method returns
a plain dict (a "view") that the command bar draws.

Views:
  home     your parks                          {"view", "parks": [...], "draft": bool}
  draft    a park being built                  {"view", "name", "note", "steps", "groups", "message"}
  ask      waiting for a name                  {"view", "prompt"}
  park     one saved park, read-only           {"view", "name", "ago", "note", "steps", "groups", "versions",
                                                "pinned", "message"}
  resume   just resumed or started             {"view", "verb", "name", "ago", "note", "steps", "opened", "skipped"}
  confirm  are you sure you want to delete     {"view", "name", "title", "lines"}
  message  help / not found                    {"view", "title", "lines"}
"""
import difflib
import time

import browser
import cues
import restore
import store
import clear
import naming
import office
import onboarding
from capture import list_windows
from commands import NO, YES, app_name, clean_name, parse, parse_draft, pick_windows
from items import current_items, kind, tab_items
from notes import split_note
from presets import preselect, profile, signatures

DRAFT_EXPIRES = 2 * 3600  # an untouched draft older than this is thrown away
UNDO_FOR = 60             # seconds an action can still be undone
LONG_NAME = (4, 40)       # a new name with more words or letters than this is checked before saving


class Controller:
    def __init__(self):
        self.draft = None           # the park being built: {"items", "note", "steps", "name", "at"}
        self.asking_name = False    # waiting for "what should I call it?"
        self.confirm_delete = None  # park name waiting for "yes"
        self.checking_name = None   # a long name waiting for "yes": {"name", "clear"}
        self.viewing = None         # the park on screen, for "pin this"
        self.last_action = None     # what "undo" would take back: {"kind", "name", "at", ...}

    def opened(self):
        """The bar just opened: carry on with a draft if there is one, else show your parks."""
        self.asking_name = False
        self.confirm_delete = None
        self.checking_name = None
        if self.draft and time.time() - self.draft["at"] > DRAFT_EXPIRES:
            self.draft = None
        return self.draft_view() if self.draft else self.home()

    # --- one entry point for everything you say -------------------------------
    def handle(self, text):
        text = text.strip()
        if self.confirm_delete:
            name, self.confirm_delete = self.confirm_delete, None
            if YES.match(text):
                trashed = store.delete(name)
                self.remember("delete", name, trashed=str(trashed))
                return self.with_undo(self.home(f"Deleted “{name}”."))
            return self.home(f"Kept “{name}”.")
        if self.checking_name:
            return self.answer_name_check(text)
        if self.asking_name:
            self.asking_name = False
            if text or self.draft:
                return self.save(text)  # nothing said: save() falls back to the suggested name
            return self.ask_name()
        if not text:
            return self.draft_view() if self.draft else self.home()

        if self.draft:
            command = parse_draft(text)
            self.draft["at"] = time.time()
            if command[0] in ("drop", "keep"):
                return self.choose(command[1], keep=command[0] == "keep")
            if command[0] == "save":
                return self.save(command[1], clear_after=command[2])
            if command[0] == "cancel":
                self.draft = None
                return self.home("Park cancelled. Nothing was saved.")
            if command[0] == "note":
                return self.set_note(command[1])
            if command[0] == "park":
                return self.rename_draft(command[1]) if command[1] else self.draft_view("Back to your unsaved park.")
            if command[0] == "pin_draft":
                return self.draft_view("Save it first (“save as dsa”), then say “pin this”.")
        else:
            command = parse(text)
            if command[0] == "park":
                return self.start_draft(command[1], command[2], clear_after=command[3])
            if command[0] == "save_first":
                return self.home("Say “park” first: it gathers what's open. Then your note, then “save as …”.")
            if command[0] == "delete":
                return self.ask_delete(command[1])
            if command[0] == "pin":
                return self.pin(command[1])
            if command[0] == "unpin":
                return self.unpin(command[1])

        if command[0] == "undo":
            return self.undo()
        if command[0] == "hide_guide":
            onboarding.hide()
            return self.home("Guide hidden. Say “help” any time for the commands.")
        if command[0] == "list":
            return self.home()
        if command[0] == "resume":
            return self.resume(command[1])
        if command[0] == "start":
            return self.start(command[1])
        if command[0] == "step":
            return self.tick_step(command[1], command[2])
        if command[0] == "view":
            return self.view(command[1])
        return self.help()

    # --- building a park ------------------------------------------------------------
    def start_draft(self, name="", note="", clear_after=False):
        browser.request_reports()  # exact tabs right now, not the last report
        self.draft = {"items": current_items(), "note": "", "steps": [], "name": name, "at": time.time(),
                      "clear": clear_after}
        # git cues for every repo on screen, worked out once; the view shows only the ticked ones
        all_folders = cues.folders_of([{**i, "keep": True} for i in self.draft["items"]])
        self.draft["cues"] = cues.for_folders(all_folders)
        left_out = sum(1 for i in self.draft["items"] if not i["keep"])
        message = "Untick what you don't want, say a note, then “save as <name>”."
        if left_out:
            message = f"Left out {left_out} chat/music item{'s' if left_out > 1 else ''} · tick them if they belong."
        existing = store.load(name) if name else None
        if existing:  # "park coding": tick what belongs to coding, untick the rest
            name = self.draft["name"] = existing["name"]
            ticked = preselect(self.draft["items"], existing)
            message = (f"Ticked the {ticked} that belong to {name}. “keep 5” to add more, then “save”."
                       if ticked else f"Nothing open looks like {name}'s things. Tick what belongs, then “save”.")
        if note:
            self.set_note(note)
        return self.draft_view(message)

    def rename_draft(self, name):
        """'park dsa' while a draft is open: it's for dsa now; tick dsa's things if dsa exists."""
        existing = store.load(name)
        self.draft["name"] = existing["name"] if existing else name
        if not existing:
            return self.draft_view(f"This park will be saved as {name}.")
        ticked = preselect(self.draft["items"], existing)
        return self.draft_view(f"Now parking {existing['name']}: ticked the {ticked} that belong to it.")

    def tabs_arrived(self, browser_name):
        """A browser reported after the draft was made (its extension woke up late):
        swap its single window row for one row per tab. Returns the new view, or None."""
        exe = browser.EXE[browser_name]
        if not self.draft or not any(i["app"] == exe and kind(i) == "window" for i in self.draft["items"]):
            return None
        reports = browser.fresh_tabs({w.app for w in list_windows()})  # all open apps: see fresh_tabs
        if browser_name not in reports:
            return None
        others = [i for i in self.draft["items"] if i["app"] != exe]
        new_tabs = tab_items(browser_name, reports[browser_name])
        existing = store.load(self.draft["name"]) if self.draft["name"] else None
        if existing:  # same pre-ticking as start_draft, for the tabs that came late
            sigs = profile(existing)
            for tab in new_tabs:
                tab["keep"] = bool(signatures(tab) & sigs)
        self.draft["items"] = others + new_tabs
        return self.draft_view(f"{browser_name.title()} tabs added.")

    def set_note(self, text):
        split = split_note(text)
        self.draft["note"], self.draft["steps"] = split["brain_dump"], split["next_steps"]
        return self.draft_view("Note added. Say a new one to replace it.")

    def toggle(self, index):
        if not self.draft:
            return self.home()
        item = self.draft["items"][index]
        item["keep"] = not item["keep"]
        return self.draft_view()

    def set_many(self, indexes, keep):
        """A group's checkbox: tick or untick all its rows at once."""
        if not self.draft:
            return self.home()
        for i in indexes:
            self.draft["items"][i]["keep"] = keep
        return self.draft_view()

    def names(self):
        """Park names, most recent first: the bar uses them for Tab-completion."""
        return [s["name"] for s in store.list_stages()]

    def choose(self, what, keep):
        """'drop 3' / 'drop youtube' / 'keep 3'."""
        picked = pick_windows(what, self.draft["items"])
        if not picked:
            return self.draft_view(f"Didn't find “{what}”. Say a number from the list.")
        for i in picked:
            self.draft["items"][i]["keep"] = keep
        return self.draft_view(f"{'Kept' if keep else 'Dropped'} {', '.join(str(i + 1) for i in picked)}")

    def ask_name(self):
        self.asking_name = True
        return {"view": "ask", "prompt": "What should this park be called?",
                "suggested": self.suggested_name() if self.draft else ""}

    # --- long names: "save it as I was fixing the login bug" shouldn't quietly become a name ---
    def check_name(self, name, clear_after):
        self.checking_name = {"name": name, "clear": clear_after}
        return {"view": "namecheck", "name": name, "suggested": self.suggested_name()}

    def answer_name_check(self, text):
        """'yes' keeps the long name; 'no' goes back to the park; anything else is the new name."""
        pending, self.checking_name = self.checking_name, None
        if not self.draft:
            return self.home()
        if YES.match(text):
            return self.save(pending["name"], pending["clear"], checked=True)
        if not text or NO.match(text):
            return self.draft_view("Not saved yet. Say “save as” and a short name.")
        command = parse_draft(text)  # "save as dsa" or just "dsa"
        name = (command[1] or self.suggested_name()) if command[0] == "save" else clean_name(text)
        return self.save(name, pending["clear"])

    def suggested_name(self):
        return naming.suggest(self.draft["items"], ticked_cues(self.draft))

    def save(self, name, clear_after=False, checked=False):
        """Save the draft under a name: the one said, the one from "park dsa", else the suggestion."""
        if not any(i["keep"] for i in self.draft["items"]):
            return self.draft_view("Nothing is ticked, so there's nothing to save. Tick what belongs, or say “cancel”.")
        name = name or self.draft["name"] or self.suggested_name()
        if not store.slug(name):
            return self.ask_name()
        existing = store.load(name)  # exact name only: never fold "acads" into "coding"
        if not existing and not checked and too_long(name):
            return self.check_name(name, clear_after)
        name = existing["name"] if existing else name
        draft, self.draft = self.draft, None
        store.park(name, draft["items"], draft["note"], draft["steps"], ticked_cues(draft))
        onboarding.mark("saved")
        kept = sum(1 for i in draft["items"] if i["keep"])
        versions = len(store.load(name)["snapshots"])
        extra = f" · version {versions}" if versions > 1 else ""
        view = self.view(name, f"Saved ✓  {kept} of {len(draft['items'])} items{extra}")
        if clear_after or draft.get("clear"):
            closed, left = clear.close_items(draft["items"])
            view.update(cleared=closed, left_open=left)
            self.remember("clear", name)
            return self.with_undo(view)
        return view

    # --- undo -----------------------------------------------------------------------------
    def remember(self, kind_of_action, name, **details):
        self.last_action = {"kind": kind_of_action, "name": name, "at": time.time(), **details}

    def undo_seconds(self):
        if not self.last_action:
            return 0
        return max(0, int(UNDO_FOR - (time.time() - self.last_action["at"])))

    def with_undo(self, view):
        """Show an Undo button (with its time left) on the view right after an action."""
        view["undo"] = self.undo_seconds()
        return view

    def undo(self):
        """Take back the last resume, clear or delete, within a minute."""
        action, self.last_action = self.last_action, None
        if not action or time.time() - action["at"] > UNDO_FOR:
            return {"view": "message", "title": "Nothing to undo",
                    "lines": ["Undo works for a minute after a resume, a park-and-clear, or a delete."]}
        name = action["name"]
        if action["kind"] == "resume":
            closed = clear.undo_resume(set(action["before"]), set(action["apps"]), name, action["files"])
            return self.home(f"Undone: closed {closed} window{'s' if closed != 1 else ''} and the “{name}” tabs.")
        if action["kind"] == "clear":
            view = self.resume(name)
            view["verb"] = "Reopened"
            return view
        if action["kind"] == "delete":
            if store.undelete(action["trashed"], name):
                return self.view(name, "Back from the trash.")
            return {"view": "message", "title": "Couldn't undo", "lines": [f"A park called “{name}” exists again."]}
        return self.help()

    def draft_view(self, message=""):
        d = self.draft
        return {"view": "draft", "name": d["name"], "note": d["note"], "steps": d["steps"],
                "suggested": "" if d["name"] else self.suggested_name(), "clear": d.get("clear", False),
                "groups": groups(d["items"]), "message": message, "cues": cue_rows(ticked_cues(d)),
                "no_tabs": sorted({app_name(i) for i in d["items"]
                                   if i["app"] in ("chrome.exe", "msedge.exe") and kind(i) == "window"})}

    # --- your parks -------------------------------------------------------------------
    def home(self, message=""):
        parks = []
        for s in store.list_stages():
            last = s["snapshots"][-1]
            kept = [i for i in last["windows"] if i.get("keep", True)]
            todo = [step for n, step in enumerate(last["next_steps"]) if n not in last.get("done", [])]
            parks.append({
                "name": s["name"], "ago": store.ago(last["parked_at"]),
                "next": todo[0] if todo else "",
                "items": len(kept), "versions": len(s["snapshots"]), "preset": bool(s.get("pinned")),
            })
        return {"view": "home", "parks": parks, "draft": bool(self.draft), "message": message,
                "guide": onboarding.guide()}

    def view(self, spoken, message=""):
        name = store.find(spoken)
        if not name:
            return self.not_found(spoken)
        self.viewing = name
        stage = store.load(name)
        last = stage["snapshots"][-1]
        return {
            "view": "park", "name": name, "ago": store.ago(last["parked_at"]),
            "note": last["brain_dump"], "steps": last["next_steps"], "done": last.get("done", []),
            "groups": groups([i for i in last["windows"] if i.get("keep", True)], numbered=False),
            "versions": [{"ago": store.ago(s["parked_at"]), "note": s["brain_dump"]}
                         for s in reversed(stage["snapshots"][:-1])][:5],
            "pinned": groups(stage.get("pinned", []), numbered=False),
            "cues": cue_rows(last.get("cues", [])),
            "message": message,
        }

    def resume(self, spoken):
        if not spoken:  # "resume" alone: the newest park
            parks = store.list_stages()
            if not parks:
                return self.home("Nothing parked yet. Say “park” to save what's open.")
            spoken = parks[0]["name"]
        name = store.find(spoken)
        if not name:
            return self.not_found(spoken)
        snap = store.latest(name)
        self.viewing = name  # so "tick 1" works on the note you're reading
        self.remember_resume(name, snap["windows"])
        opened, skipped = restore.reopen(snap, name)
        return self.with_undo({"view": "resume", "verb": "Resumed", "name": name, "ago": store.ago(snap["parked_at"]),
                "note": snap["brain_dump"], "steps": snap["next_steps"], "done": snap.get("done", []),
                "opened": opened, "skipped": skipped,
                "cues": cue_rows(cues.compare(snap.get("cues", [])))})

    # --- next steps: tick them off as you get through them -------------------------------
    def tick_step(self, index, done):
        """Voice: "tick 1" / "untick 1" on the park on screen."""
        name = self.viewing
        if not name or not store.load(name):
            return self.home("Open a park first (“view coding”), then “tick 1”.")
        steps = store.latest(name)["next_steps"]
        if not 0 <= index < len(steps):
            return self.view(name, f"There's no step {index + 1}." if steps else "This park has no next steps.")
        store.set_step(name, index, done)
        return self.view(name, f"{'Ticked' if done else 'Unticked'} “{steps[index]}”.")

    def toggle_step(self, name, index):
        """Click on a step: flip it. Returns the ticked step numbers, so the page updates in place."""
        done = set(store.latest(name).get("done", []))
        return store.set_step(name, index, index not in done)

    def remember_resume(self, name, items):
        """Before reopening: note which windows and Office files are already open, so undo
        closes only what this resume added. (Also ticks guide step 3.)"""
        onboarding.mark("resumed")
        open_files = {f["path"].lower() for f in office.current()}
        files = [i["path"] for i in items if i.get("keep", True) and kind(i) == "file"
                 and i["app"] in office.APPS and i["path"].lower() not in open_files]
        kept = [i for i in items if i.get("keep", True)]
        # apps whose new windows undo may close; browsers aren't here: their tabs close as a group
        apps = {i["app"] for i in kept if kind(i) != "tab" and i["app"] not in browser.BROWSER_OF_APP}
        if any(kind(i) == "terminal" for i in kept):
            apps.add("windowsterminal.exe")
        self.remember("resume", name, before=[w.hwnd for w in list_windows()], files=files, apps=sorted(apps))

    # --- presets ------------------------------------------------------------------------
    def pin(self, spoken):
        """'pin this' (the park on screen) or 'pin dsa': its newest kept items become the preset."""
        name = store.find(spoken) if spoken else self.viewing
        if not name:
            return self.not_found(spoken) if spoken else {
                "view": "message", "title": "Which park?", "lines": ["Open one first (“view dsa”), or say “pin dsa”."]}
        items = [i for i in store.latest(name)["windows"] if i.get("keep", True)]
        store.set_pins(name, items)
        return self.view(name, f"📌 Pinned {len(items)} items. Say “start {name}” any time to open them.")

    def unpin(self, spoken):
        name = store.find(spoken)
        if not name:
            return self.not_found(spoken)
        store.set_pins(name, None)
        return self.view(name, "Unpinned. It's a plain park again; its versions are untouched.")

    def start(self, spoken):
        """Open a preset's pinned items, with the newest park's note on top."""
        name = store.find(spoken)
        if not name:
            return self.not_found(spoken)
        stage = store.load(name)
        if not stage.get("pinned"):  # not a preset: do the closest useful thing
            view = self.resume(name)
            view["skipped"] = [f"{name} isn't pinned yet, so its last park was resumed. "
                               f"Say “pin {name}” to make it a preset."] + view["skipped"]
            return view
        last = stage["snapshots"][-1]
        self.remember_resume(name, stage["pinned"])
        opened, skipped = restore.reopen({"windows": stage["pinned"]}, name)
        return self.with_undo({"view": "resume", "verb": "Started", "name": name, "ago": store.ago(last["parked_at"]),
                "note": last["brain_dump"], "steps": last["next_steps"], "opened": opened, "skipped": skipped,
                "cues": cue_rows(cues.compare(last.get("cues", [])))})

    def ask_delete(self, spoken):
        name = store.find(spoken)
        if not name:
            return self.not_found(spoken)
        versions = len(store.load(name)["snapshots"])
        self.confirm_delete = name
        return {"view": "confirm", "name": name, "title": f"Delete “{name}”?",
                "lines": [f"{versions} saved version{'s' if versions > 1 else ''} will move to the trash folder.",
                          "Say “yes” to delete, anything else to keep it."]}

    def not_found(self, spoken):
        """Not a dead end: the closest name as a question, and every park one click away."""
        names = [s["name"] for s in store.list_stages()]
        if not names:
            return {"view": "message", "title": f"No park called “{spoken}”",
                    "lines": [{"text": "Nothing is parked yet. Park what's open", "say": "park"}]}
        close = difflib.get_close_matches(spoken.lower(), [n.lower() for n in names], n=1, cutoff=0.4)
        guess = next((n for n in names if close and n.lower() == close[0]), None)
        lines = [{"text": f"Did you mean “{guess}”? View it", "say": f"view {guess}"}] if guess else []
        lines += [{"text": n, "say": f"view {n}", "park": True} for n in names if n != guess][:6]
        return {"view": "message", "title": f"No park called “{spoken}”", "lines": lines}

    def help(self):
        """Every command as something you can click; examples use your own park names."""
        names = [s["name"] for s in store.list_stages()]
        example = names[0] if names else "coding"
        known = bool(names)
        return {"view": "message", "title": "Try one of these · click or say it",
                "lines": [{"text": "Park → your note → save as coding", "say": "park"},
                          {"text": "Resume (the last one)", "say": "resume"} if known else "Resume (the last one)",
                          {"text": f"Resume {example}", "say": f"resume {example}"} if known else f"Resume {example}",
                          {"text": "Show my parks", "say": "show my parks"},
                          {"text": f"View {example}", "say": f"view {example}"} if known else f"View {example}",
                          "Pin this · Start dsa",
                          "Park dsa  (ticks dsa's things for you)",
                          f"Delete {example}"]}


def too_long(name):
    words, letters = LONG_NAME
    return len(name.split()) > words or len(name) > letters


def groups(items, numbered=True):
    """Items grouped for display: apps, files, terminals, then each browser window's tabs.
    Every row keeps its position in the full list (i), which is what 'drop 3' and clicks use."""
    labels = {"window": "Apps", "file": "Files", "terminal": "Terminals"}
    out = {label: [] for label in labels.values()}  # fixed order, empty ones dropped below
    for i, item in enumerate(items):
        k = kind(item)
        label = f"{item['browser'].title()} · window {item['window']}" if k == "tab" else labels[k]
        out.setdefault(label, []).append({
            "i": i, "n": i + 1 if numbered else None, "app": app_name(item), "title": item["title"],
            "keep": item.get("keep", True), "tab": k == "tab", "kind": k,
            "host": item.get("url", "").split("/")[2] if item.get("url", "").count("/") >= 2 else "",
            "meta": row_meta(item),
        })
    return [{"label": label, "items": rows} for label, rows in out.items() if rows]


def ticked_cues(draft):
    """The draft's git cues for repos that ticked items still work in."""
    roots = {str(r) for r in map(cues.repo_root, cues.folders_of(draft["items"])) if r}
    return [c for c in draft.get("cues", []) if c["path"] in roots]


def cue_rows(found):
    """Git cues ready to draw: repo, one line of text, and a warning if the branch changed since."""
    return [{"repo": c["repo"], "text": cues.describe(c),
             "drift": f"now on {c['now_branch']}" if c.get("now_branch") else ""} for c in found]


def row_meta(item):
    """The small grey text at the end of a row."""
    if kind(item) == "tab" and item.get("video_time", 0) > 5:
        host = item["url"].split("/")[2].removeprefix("www.")
        minutes, seconds = divmod(item["video_time"], 60)
        hours, minutes = divmod(minutes, 60)
        at = f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"
        return f"{host} · at {at}"
    if kind(item) == "terminal":
        if not item["command"]:
            return ""
        return "reruns on resume" if item.get("rerun") else "folder only (not re-run)"
    if kind(item) == "file":
        parts = [item.get("where_text", "")] + (["unsaved changes"] if item.get("unsaved") else [])
        return " · ".join(p for p in parts if p)
    return ""
