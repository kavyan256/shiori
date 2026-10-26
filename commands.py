"""Understanding what you said: turns dictated text into a command.

Saving your desk is a draft you build up, then save:
  "Save my desk" (or "desk", "park")      start a draft with everything open
  "drop 3" / "drop youtube" / "keep 3"     choose what goes in
  "I was fixing X, next do Y"              anything else is the note
  "Save as coding"                         name it and save
  "Cancel"                                 throw the draft away

Any time:
  "Show my desks" · "View coding" · "Resume coding" · "Delete coding" (then "yes")

Presets:
  "Pin this" (while viewing a desk) / "Pin dsa"   its items become the preset
  "Start dsa"                                     open the preset's pinned items
  "Unpin dsa"                                     back to a plain desk
  "Save my desk as dsa"                           starts with dsa's things ticked, the rest unticked

Inside, a saved desk is still called a "park" (store.park, the "park" view): that was its first name.
"""
import difflib
import re

import store

# --- any time ---
# "save my desk", "new desk", "desk"; "park" was the first name and still works; Wispr sometimes hears "disk"
PARK = re.compile(r"^(?:park|new park|desk|disk|(?:save|new|park)(?:\s+(?:my|this|the|a))?\s+(?:desk|disk))(?:\s+(?:this|everything|it all|all(?: of)?(?: this| these| it)?|these|now))?"
                  r"(?:\s+(?:as|called|named))?(?:[\s.,:;!?]+(?P<rest>.+))?$", re.I | re.S)
# "resume" alone, "resume the last one", "pick up where I left off": the newest park
RESUME_LAST = re.compile(r"^(?:resume|continue|go back|back to work|pick up where i left off)"
                         r"(?:\s+(?:it|that|this|last|latest|the (?:last|latest)(?: one| park| desk)?|my (?:last|latest)(?: one| park| desk)?"
                         r"|where i left off))?$", re.I)
RESUME = re.compile(r"^(?:resume|retrieve|restore|back to|go back to|continue|switch to|open)\s+(?P<name>.+)$", re.I | re.S)
# "parts": Wispr often hears "parks" as "parts"
LIST = re.compile(r"^(?:list|desks|disks|parks|parts|stages|(?:show|see|view)(?:ing)?(?: me)?(?: all)? (?:of )?(?:my |the )?"
                  r"(?:desks|disks|parks|parts|stages)|my (?:desks|disks|parks|parts|stages))\b", re.I)
# Polite lead-ins people say before a command: "let's resume coding", "can you show my desks"
LEAD_IN = re.compile(r"^(?:(?:ok(?:ay)?|so|hey|please|now|and|alright|um+|uh+|erm?|hmm+|mm+|well|oh|"
                     r"let'?s|let us|can you|could you|would you|i want to|i'd like to)[\s,]+)+", re.I)
# Nothing meant: fillers, and the phrases speech-to-text invents from silence ("Thank you.", "Thanks for watching!")
NOISE = re.compile(r"^(?:(?:um+|uh+|huh|uh-?huh|mhm+|mm-?hmm|erm?|hmm+|mm+|ah+|oh|okay|ok|so|yeah|and|like|you|bye|thanks|thank you|"
                   r"thank you (?:so|very) much|thanks for watching|you're welcome|subtitles by[^.]*)[\s,.!?…]*)+$"
                   r"|^[\s,.!?…\-]*$", re.I)
VIEW = re.compile(r"^(?:view|show|see|look at|details (?:of|for))\s+(?:me\s+)?(?:the\s+)?(?:(?:park|desk)\s+)?(?P<name>.+)$", re.I)
DELETE = re.compile(r"^(?:delete|trash|forget|remove)\s+(?:the\s+)?(?:(?:park|desk)\s+)?(?P<name>.+)$", re.I)
PIN = re.compile(r"^pin(?:\s+(?:this|it|the park|the desk|that))?(?:\s+(?:park|desk|preset))?(?:\s+(?P<name>.+))?$", re.I)
UNPIN = re.compile(r"^unpin\s+(?:the\s+)?(?:(?:park|desk)\s+)?(?P<name>.+)$", re.I)
START = re.compile(r"^(?:start|launch|set ?up|fire up|open (?:the )?preset)\s+(?:my\s+|the\s+)?(?P<name>.+?)"
                   r"(?:\s+(?:preset|park|desk|setup|stage))?$", re.I)
HIDE_GUIDE = re.compile(r"^(?:hide|skip|close|dismiss)(?: the)? (?:guide|tips|getting started|tutorial)$|^got it$", re.I)
# Ticking off a next step while a desk is on screen: "tick 1", "done with step 2", "untick 1"
TICK_STEP = re.compile(r"^(?P<un>un)?(?:tick|check)(?: off)?(?: step| number)?\s+(?P<n>\w+)$"
                       r"|^(?:done|finished)(?: with)? (?:step|number) (?P<n2>\w+)$", re.I)
UNDO = re.compile(r"^(?:undo|undo (?:that|it|this)|take (?:that|it) back)$", re.I)
# "…and clear": close what was parked afterwards. Only looked for at the end of a park/save command.
AND_CLEAR = re.compile(r"(?:^|[\s,.]+)(?:and\s+)?(?:clear|close)(?:\s+(?:it all|everything|them|up|the desk|my desk))?$", re.I)
PARK_NAME_WORDS = re.compile(r"^(?:and\s+)?(?:save\s+(?:it\s+|this\s+)?)?(?:as|called|named)\s+", re.I)
AND_SAVE = re.compile(r"[\s,.]+and\s+save(?:\s+it)?$", re.I)
NO = re.compile(r"^(?:n|no+|nope|nah|back|go back|not that|cancel|keep(?: it)?|wait|stop|don'?t)\b", re.I)
YES = re.compile(r"^(?:y|ya|yah|yea|yeah|yes+|yep|yup|yas|confirm|do it|delete it|sure|ok(?:ay)?|go ahead|please do)\b", re.I)
# "delete it" / "delete" again, answering "Delete dsa?"
DELETE_AGAIN = re.compile(r"^(?:delete|remove|trash)(?:\s+(?:it|that|this))?\b", re.I)
# --- while a draft park is open ---
# longer phrases first, so "add back chrome" isn't read as add "back chrome"
DROP = re.compile(r"^(?:leave out|don'?t save|drop|remove|skip|exclude|untick)\s+(?P<what>.+)$", re.I)
KEEP = re.compile(r"^(?:add back|bring back|keep|add|include|tick)\s+(?P<what>.+)$", re.I)
BARE_PICK = re.compile(r"^(?P<verb>leave out|don'?t save|drop|remove|skip|exclude|untick|add back|bring back|keep|add|include|tick)$", re.I)
# words a sentence doesn't end on: "I was" or "fixing the" was cut off mid-thought
UNFINISHED = {"was", "were", "is", "am", "are", "the", "a", "an", "to", "and", "or", "but", "of", "for", "with",
              "my", "on", "in", "at", "as", "i", "we", "because"}
SAVE = re.compile(r"^(?:(?:done|finished)[\s,.]+)?(?:save|name it|call it)"
                  r"(?:\s+(?:it|this|the park|park|(?:my |this |the )?(?:desk|disk)))?"
                  r"(?:\s+(?:as|called|named))?\s*(?P<name>.*)$", re.I | re.S)
DONE = re.compile(r"^(?:done|finish|finished|complete|that's it)$", re.I)  # alone only: "done with X" is a note
CANCEL = re.compile(r"^(?:cancel|discard|never ?mind|throw (?:it|this) away)\b", re.I)
NOTE = re.compile(r"^(?:note|add (?:a )?note|my note is)\s*[:,-]?\s*(?P<note>.+)$", re.I | re.S)
NUMBER_WORDS = {w: str(n) for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
# A park that starts with one of these is a note, not a name: "park I was fixing…" is not a park called "I"
STARTS_A_NOTE = {"i", "i'm", "im", "i've", "i'll", "we", "we're", "the", "a", "an", "my", "was", "just", "so",
                 "working", "fixing", "doing", "reading", "writing", "studying", "next", "then", "and", "it",
                 "it's", "this", "that", "currently", "still", "now", "today", "tomorrow", "need", "have", "to"}
NOT_A_MATCH = {"the", "and", "window", "windows", "tab", "tabs", "number", "app", "one", "all"}
FRIENDLY = {"code": "VS Code", "code - insiders": "VS Code Insiders", "cursor": "Cursor", "windsurf": "Windsurf",
            "windowsterminal": "Terminal", "explorer": "Explorer",
            "chrome": "Chrome", "msedge": "Edge", "brave": "Brave", "opera": "Opera", "claude": "Claude",
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
    if {"all", "everything"} & set(words) and set(words) <= {"all", "everything", "them", "of", "it", "the", "whole", "lot"}:
        return list(range(len(windows)))  # "drop all", "keep everything", "drop all of them"

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
    if sep and len(head.split()) <= 4 and head.split()[0].lower() not in STARTS_A_NOTE:
        return head.strip(), tail.strip()
    spoken = store.slug(rest)
    for s in sorted(store.list_stages(), key=lambda s: -len(s["name"])):
        if spoken.startswith(store.slug(s["name"])):
            words = len(s["name"].split())
            parts = rest.split()
            return " ".join(parts[:words]), " ".join(parts[words:])
    first, _, after = rest.strip().partition(" ")
    if first.lower().strip(".,") in STARTS_A_NOTE or (sep and len(head.split()) > 4):
        return "", rest.strip()  # "park I was fixing the login bug": all note, the name comes later
    return first, after


def clean_name(name):
    return name.strip(" .,:;!?\"'“”")


def saved_name(said):
    """'all these as test parking 1' -> 'test parking 1': the name comes after the last 'as'/'called'."""
    parts = re.split(r"\s(?:as|called|named)\s", f" {said} ", flags=re.I)
    return clean_name(parts[-1])


# Words speech-to-text puts in place of a command ("rezoom shop api"). Fixed on the home screen only,
# never inside a note: "Restart the server" in a note must stay a note.
MISHEARD = {"rezoom": "resume", "resum": "resume", "rezume": "resume", "resoom": "resume", "re-zoom": "resume",
            "résumé": "resume", "resumé": "resume", "safe": "save", "shoe": "show"}
COMMAND_WORDS = ["resume", "view", "delete", "start", "save", "show", "unpin", "undo", "help"]


def fix_command_word(text):
    """'rezoom shop api' -> 'resume shop api', 'delte dsa' -> 'delete dsa'; unchanged if nothing is close."""
    first, _, rest = text.strip().partition(" ")
    word = first.lower()
    close = difflib.get_close_matches(word, COMMAND_WORDS, n=1, cutoff=0.8)
    fixed = MISHEARD.get(word) or (close[0] if close else None)
    if not fixed or fixed == word or (not rest and fixed.startswith(word)):
        return text  # "resu" alone is a half word, not a typo: offer choices, never run "resume"
    return f"{fixed} {rest}".strip()


def without_repeat(text):
    """'save my desk save my desk' -> 'save my desk': a phrase pasted or said twice in a row counts once."""
    words = text.split()
    half = len(words) // 2
    plain = [w.strip(".,!?;:").lower() for w in words]
    if half and len(words) % 2 == 0 and plain[:half] == plain[half:]:
        return " ".join(words[:half]).rstrip(".,!?;:")
    return text


def cut_off(note):
    """A note that stops mid-thought ('I was', 'drop', 'fixing the'): probably Enter, or Wispr, came too early."""
    words = note.rstrip(" .,!?…").split()
    return not words or len(words) < 2 or (len(words) < 6 and words[-1].lower() in UNFINISHED)


def split_clear(text):
    """'save as coding and clear' -> ('save as coding', True)."""
    stripped = AND_CLEAR.sub("", text)
    return stripped.strip(), stripped != text


def parse(text):
    """Commands that work any time.
    -> ('park', name or '', note, clear) | ('resume', name or '') | ('view', name) | ('delete', name)
       | ('pin', name or '') | ('unpin', name) | ('start', name) | ('undo',) | ('list',) | ('help',)"""
    text = without_repeat(LEAD_IN.sub("", text.strip()).rstrip(".!?"))
    if NOISE.match(text):
        return ("noise",)
    if UNDO.match(text):
        return ("undo",)
    if HIDE_GUIDE.match(text):
        return ("hide_guide",)
    if LIST.match(text):
        return ("list",)
    if m := TICK_STEP.match(text):
        said = (m["n"] or m["n2"]).lower()
        number = NUMBER_WORDS.get(said, said)  # "tick two" -> 2
        if number.isdigit():
            return ("step", int(number) - 1, not m["un"])
    if RESUME_LAST.match(text):
        return ("resume", "")  # the newest park
    short, clear = split_clear(text)
    if m := PARK.match(short):
        # "park and save as coding" / "park coding and save": the name is coding; saving stays its own step
        rest = PARK_NAME_WORDS.sub("", AND_SAVE.sub("", (m["rest"] or "").strip()))
        name, note = split_park(rest) if rest else ("", "")
        return ("park", clean_name(name), note, clear)
    if SAVE.match(short) or DONE.match(short):
        return ("save_first",)  # saving is the last step: "park" comes first
    if m := UNPIN.match(text):
        return ("unpin", clean_name(m["name"]))
    if m := PIN.match(text):
        return ("pin", saved_name(m["name"] or ""))
    if m := START.match(text):
        return ("start", clean_name(m["name"]))
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
    said = without_repeat(LEAD_IN.sub("", text.strip()).rstrip(".!?"))
    if NOISE.match(said):
        return ("noise",)
    if UNDO.match(said):
        return ("undo",)
    if m := BARE_PICK.match(said):
        return ("which", m["verb"].lower())
    if m := DROP.match(said):
        return ("drop", m["what"])
    if m := KEEP.match(said):
        return ("keep", m["what"])
    short, clear = split_clear(said)
    if clear and not short:
        return ("save", "", True)  # just "clear"
    if m := SAVE.match(short):
        if not clean_name(m["name"]) and re.search(r"\b(?:as|called|named|name it|call it)$", short, re.I):
            return ("save_ask", clear)  # "save as" and then nothing: ask for the name, don't guess
        return ("save", saved_name(m["name"]), clear)
    if DONE.match(short):
        return ("save", "", clear)
    if CANCEL.match(said):
        return ("cancel",)
    if m := NOTE.match(text.strip()):
        return ("note", m["note"], True)  # "note: …" said on purpose: kept even if short
    command = parse(text)
    if command[0] in ("list", "resume", "view", "start"):
        return command
    if command[0] == "pin":
        return ("pin_draft",)  # can't pin what isn't saved yet
    if command[0] == "park" and not command[2]:
        return ("park", command[1])  # "park" again: back to the draft; "park dsa": it's for dsa
    return ("note", without_repeat(text.strip()), False)
