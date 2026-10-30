"""Finding a desk by anything in it: "find the TCP notes", "which desk has the lecture on CNNs".

Every word you said has to be somewhere in the desk. Notes and steps count most, then what
was open, and older versions of a desk count too, for what you've since moved on from.
"""
import re

FILLER = {"a", "an", "the", "my", "me", "of", "for", "in", "on", "at", "to", "with", "and", "or", "that", "this",
          "it", "i", "was", "is", "desk", "desks", "one", "about", "some", "had", "has", "have", "stuff", "thing", "things"}
NOTE, OPEN = 3, 1       # how much a match counts, by where it is
OLDER = 0.5             # the same, in an older version of the desk
SNIPPET = 70            # letters of context shown with a result


def words_of(query):
    return [w for w in re.findall(r"[\w+#.-]+", query.lower()) if w not in FILLER]


def places_in(snapshot):
    """(weight, text) for everything in one version of a desk."""
    for text in [snapshot.get("brain_dump", ""), *snapshot.get("next_steps", [])]:
        yield NOTE, text
    for cue in snapshot.get("cues", []):
        yield OPEN, f"{cue.get('repo', '')} {cue.get('branch', '')}"
    for item in snapshot.get("windows", []):
        if item.get("keep", True):
            yield OPEN, item.get("title", "")
            for key in ("url", "folder", "path", "command"):
                yield OPEN, item.get(key, "")
            yield from ((OPEN, target) for target in item.get("targets", []))


def snippet(text, word):
    """The part of the text around a word, on one line."""
    text = " ".join(text.split())
    if len(text) <= SNIPPET:
        return text
    start = max(0, text.lower().find(word) - SNIPPET // 3)
    end = start + SNIPPET
    return f"{'…' if start else ''}{text[start:end].strip()}{'…' if end < len(text) else ''}"


def find(query, stages):
    """Desks with every word of the query, best first: [{"name", "found"}]."""
    words = words_of(query)
    if not words:
        return []
    results = []
    for stage in stages:  # newest desk first, and sorted() below keeps that order between equals
        snapshots = stage["snapshots"][::-1]
        places = [(weight if n == 0 else weight * OLDER, text) for n, snap in enumerate(snapshots)
                  for weight, text in places_in(snap) if text]
        name = stage["name"]
        seen = {w: [p for p in places if w in p[1].lower()] for w in words}
        if not all(seen[w] or w in name.lower() for w in words):
            continue
        points = sum(max((weight for weight, _ in seen[w]), default=NOTE) for w in words)
        shown = next((seen[w] for w in words if seen[w]), None)
        best = max(shown, key=lambda p: p[0]) if shown else (0, "")
        first = next(w for w in words if seen[w]) if shown else ""
        results.append({"name": name, "found": snippet(best[1], first), "points": points})
    return [{"name": r["name"], "found": r["found"]} for r in sorted(results, key=lambda r: -r["points"])]
