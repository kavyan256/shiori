"""Step 4: turn a dictated ramble into a brain dump + next steps.

You talk naturally into Wispr; this splits what you said into:
  brain_dump  - where your head is: status, hunches, file names
  next_steps  - a short checklist for when you come back

Rule-based and offline: no API key, instant, nothing leaves your PC.
It works best when you say "next…", "then…" or "when I come back…".

Run:  python notes.py "was fixing the login redirect... next check auth.py, then test on mobile"
"""
import json
import re
import sys

# Words that usually start the "for later" part of a spoken note
NEXT_MARKERS = re.compile(
    r"\b(next(?: step)?|when i come back|when i'm back|tomorrow|to ?do|"
    r"i (?:still )?need to|remember to|after that|then)\b",
    re.IGNORECASE,
)
FILLER = re.compile(r"^(?:um+|uh+|so|okay|ok|basically|yeah)[\s,]+", re.IGNORECASE)
STEP_PREFIX = re.compile(
    r"^(?:and|first|is to|is|to|i (?:still )?(?:should|will|need to|have to|want to))\s+", re.IGNORECASE
)
# Split on commas, 'then', and sentence ends - but a dot only when a space or the
# end follows, so 'auth.py' stays in one piece
STEP_SPLIT = re.compile(r",|[.;!?](?=\s|$)|\b(?:and then|then|after that|and also|also)\b", re.IGNORECASE)


def strip_repeated(pattern, text):
    while (cleaned := pattern.sub("", text)) != text:
        text = cleaned
    return text


def split_note(text):
    """Everything after the first 'next'/'then'/'I need to' becomes steps,
    split on commas, 'then' and sentence ends. Returns {'brain_dump', 'next_steps'}."""
    text = strip_repeated(FILLER, " ".join(text.split()))
    match = NEXT_MARKERS.search(text)
    if not match:
        return {"brain_dump": text, "next_steps": []}

    brain_dump = text[: match.start()].strip(" ,.;")
    steps = []
    for piece in STEP_SPLIT.split(text[match.end():]):
        piece = strip_repeated(STEP_PREFIX, piece.strip(" :-"))
        if len(piece) > 2:
            steps.append(piece[0].upper() + piece[1:])
    return {"brain_dump": brain_dump, "next_steps": steps}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(json.dumps(split_note(" ".join(sys.argv[1:])), indent=2, ensure_ascii=False))
