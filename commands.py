"""Understanding what you said: turns dictated text into a command.

The park flow is a draft you build up, then save:
  "Park"                                   start a draft with everything open
  "drop 3" / "drop youtube" / "keep 3"     choose what goes in
  "I was fixing X, next do Y"              anything else is the note
  "Save as coding"                         name it and save
  "Cancel"                                 throw the draft away

Any time:
  "Show my parks" · "View coding" · "Resume coding" · "Delete coding" (then "yes")

Presets:
  "Pin this" (while viewing a park) / "Pin dsa"   its items become the preset
  "Start dsa"                                     open the preset's pinned items
  "Unpin dsa"                                     back to a plain park
  "Park dsa"                                      starts with dsa's things ticked, the rest unticked
"""
import re

import store

# --- any time ---
PARK = re.compile(r"^(?:park|new park)(?:\s+(?:this|everything|all|now))?(?:[\s.,:;!?]+(?P<rest>.+))?$", re.I | re.S)
RESUME = re.compile(r"^(?:resume|retrieve|restore|back to|go back to|continue|switch to|open)\s+(?P<name>.+)$", re.I | re.S)
# "parts": Wispr often hears "parks" as "parts"
LIST = re.compile(r"^(?:list|parks|parts|stages|(?:show|see|view)(?:ing)?(?: me)?(?: all)? (?:of )?(?:my |the )?"
                  r"(?:parks|parts|stages)|my (?:parks|parts|stages))\b", re.I)
# Polite lead-ins people say before a command: "let's resume coding", "can you show my parks"
LEAD_IN = re.compile(r"^(?:(?:ok(?:ay)?|so|hey|please|now|and|alright|let'?s|let us|can you|could you|"
                     r"would you|i want to|i'd like to)[\s,]+)+", re.I)
VIEW = re.compile(r"^(?:view|show|see|look at|details (?:of|for))\s+(?:me\s+)?(?:the\s+)?(?:park\s+)?(?P<name>.+)$", re.I)
DELETE = re.compile(r"^(?:delete|trash|forget|remove)\s+(?:the\s+)?(?:park\s+)?(?P<name>.+)$", re.I)
PIN = re.compile(r"^pin(?:\s+(?:this|it|the park|that))?(?:\s+(?:park|preset))?(?:\s+(?P<name>.+))?$", re.I)
UNPIN = re.compile(r"^unpin\s+(?:the\s+)?(?:park\s+)?(?P<name>.+)$", re.I)
START = re.compile(r"^(?:start|launch|set ?up|fire up|open (?:the )?preset)\s+(?:my\s+|the\s+)?(?P<name>.+?)"
                   r"(?:\s+(?:preset|park|setup|stage))?$", re.I)
YES = re.compile(r"^(?:yes|yeah|yep|yup|confirm|do it|delete it|sure|ok(?:ay)?)\b", re.I)
# --- while a draft park is open ---
# longer phrases first, so "add back chrome" isn't read as add "back chrome"
DROP = re.compile(r"^(?:leave out|don'?t save|drop|remove|skip|exclude|untick)\s+(?P<what>.+)$", re.I)
KEEP = re.compile(r"^(?:add back|bring back|keep|add|include|tick)\s+(?P<what>.+)$", re.I)
SAVE = re.compile(r"^(?:(?:done|finished)[\s,.]+)?(?:save|name it|call it)(?:\s+(?:it|this|the park|park))?"
                  r"(?:\s+(?:as|called|named))?\s*(?P<name>.*)$", re.I | re.S)
DONE = re.compile(r"^(?:done|finish|finished|complete|that's it)$", re.I)  # alone only: "done with X" is a note
CANCEL = re.compile(r"^(?:cancel|discard|never ?mind|throw (?:it|this) away)\b", re.I)
NOTE = re.compile(r"^(?:note|add (?:a )?note|my note is)\s*[:,-]?\s*(?P<note>.+)$", re.I | re.S)
NUMBER_WORDS = {w: str(n) for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
NOT_A_MATCH = {"the", "and", "window", "windows", "tab", "tabs", "number", "app", "one", "all"}
FRIENDLY = {"code": "VS Code", "windowsterminal": "Terminal", "explorer": "Explorer",
            "chrome": "Chrome", "msedge": "Edge", "claude": "Claude",
            "excel": "Excel", "winword": "Word", "powerpnt": "PowerPoint"}


def app_name(w):
    app = w["app"].removesuffix(".exe")
    return FRIENDLY.get(app, app)


def window_label(w):
    return f"{app_name(w)} — {w['title'][:55]}"


def searchable(w):
    """Everything a spoken word can match: app, title, label, and a tab's web address."""
    extra = [w.get(k, "") for k in ("url", "folder", "command", "path")]
    return " ".join([w["app"], w["title"], window_label(w), *extra]).lower()


def pick_windows(what, windows):
    """'3', 'two and four', 'chrome', 'the music one' -> indexes of matching windows."""
    words = re.findall(r"[a-z0-9+#.]+", what.lower())

    def numbers(tokens):
        return {int(t) - 1 for t in tokens if t.isdigit() and 0 < int(t) <= len(windows)}

    by_name = set()
    for word in words:
        if word.isdigit() or len(word) < 3 or word in NOT_A_MATCH or word in NUMBER_WORDS:
            continue
        by_name |= {i for i, w in enumerate(windows) if word in searchable(w)}
    # "three" counts as 3 only when no name matched, so "the music one" isn't window 1
    spelled = numbers(NUMBER_WORDS.get(w, "") for w in words) if not by_name else set()
    return sorted(numbers(words) | by_name | spelled)


def cut_at_punctuation(rest):
    """'hackathon. I was…' -> ('hackathon', '.', ' I was…'); no punctuation -> (rest, '', '')."""
    match = re.search(r"[.,:;!?\n]", rest)
    if not match:
        return rest, "", ""
    return rest[: match.start()], match.group(), rest[match.end():]


def split_park(rest):
    """'coding. I was fixing…' -> ('coding', 'I was fixing…').

    The name ends at the first punctuation Wispr adds. Without punctuation,
    a saved park name at the start wins, else the first word is the name.
    """
    head, sep, tail = cut_at_punctuation(rest)
    if sep and len(head.split()) <= 4:
        return head.strip(), tail.strip()
    spoken = store.slug(rest)
    for s in sorted(store.list_stages(), key=lambda s: -len(s["name"])):
        if spoken.startswith(store.slug(s["name"])):
            words = len(s["name"].split())
            parts = rest.split()
            return " ".join(parts[:words]), " ".join(parts[words:])
    first, _, after = rest.strip().partition(" ")
    return first, after


def clean_name(name):
    return name.strip(" .,:;!?\"'“”")


def saved_name(said):
    """'all these as test parking 1' -> 'test parking 1': the name comes after the last 'as'/'called'."""
    parts = re.split(r"\s(?:as|called|named)\s", f" {said} ", flags=re.I)
    return clean_name(parts[-1])


def parse(text):
    """Commands that work any time.
    -> ('park', name or '', note) | ('resume', name) | ('view', name) | ('delete', name)
       | ('pin', name or '') | ('unpin', name) | ('start', name) | ('list',) | ('help',)"""
    text = LEAD_IN.sub("", text.strip()).rstrip(".!?")
    if LIST.match(text):
        return ("list",)
    if m := UNPIN.match(text):
        return ("unpin", clean_name(m["name"]))
    if m := PIN.match(text):
        return ("pin", saved_name(m["name"] or ""))
    if m := START.match(text):
        return ("start", clean_name(m["name"]))
    if m := PARK.match(text):
        name, note = split_park(m["rest"]) if m["rest"] else ("", "")
        return ("park", clean_name(name), note)
    if m := RESUME.match(text) or VIEW.match(text):
        name = clean_name(m["name"])
        if LIST.match(re.sub(r"^(?:showing|show|all)\s+", "show ", name)):
            return ("list",)  # "resume showing my parts": they want the list
        return ("resume" if RESUME.match(text) else "view", name)
    if m := DELETE.match(text):
        return ("delete", clean_name(m["name"]))
    return ("help",)


def parse_draft(text):
    """Commands while a draft park is open; anything unrecognised is the note.
    -> ('drop'|'keep', what) | ('save', name or '') | ('cancel',) | ('note', text) | any parse() command"""
    said = LEAD_IN.sub("", text.strip()).rstrip(".!?")
    if m := DROP.match(said):
        return ("drop", m["what"])
    if m := KEEP.match(said):
        return ("keep", m["what"])
    if m := SAVE.match(said):
        return ("save", saved_name(m["name"]))
    if DONE.match(said):
        return ("save", "")
    if CANCEL.match(said):
        return ("cancel",)
    if m := NOTE.match(text.strip()):
        return ("note", m["note"])
    command = parse(text)
    if command[0] in ("list", "resume", "view", "start"):
        return command
    if command[0] == "pin":
        return ("pin_draft",)  # can't pin what isn't saved yet
    if command[0] == "park" and not command[2]:
        return ("park", command[1])  # "park" again: back to the draft; "park dsa": it's for dsa
    return ("note", text.strip())
