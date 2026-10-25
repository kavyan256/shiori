"""Presets: what belongs to a park.

A park becomes a preset when you pin it ("pin this"): its items are saved as the
park's *pinned* set, which "start dsa" opens any time.

Every park also has a *profile*: what kinds of things belong to it, taken from its
pins plus its newest version. When you say "park coding", items that match coding's
profile start ticked and everything else starts unticked.

Matching is by kind, not exact title (titles change all the time):
  a tab        -> its website       ("github.com")
  VS Code etc. -> app + folder      ("code.exe", "c:\\users\\…\\ka-os")
  other apps   -> the app           ("claude.exe")
"""
from urllib.parse import urlparse

from items import kind


def signatures(item):
    """The ways an item can match a profile."""
    if kind(item) == "tab":
        host = (urlparse(item.get("url", "")).hostname or "").removeprefix("www.")
        return {("site", host)} if host else set()
    if item.get("targets"):
        return {("folder", item["app"], t.lower()) for t in item["targets"]}
    return {("app", item["app"])}


def profile(stage):
    """Everything that belongs to this park: its pins plus its newest version's kept items."""
    newest = stage["snapshots"][-1]["windows"] if stage.get("snapshots") else []
    sigs = set()
    for item in stage.get("pinned", []) + [i for i in newest if i.get("keep", True)]:
        sigs |= signatures(item)
    return sigs


def preselect(items, stage):
    """Tick the items that belong to this park, untick the rest. Returns how many are ticked."""
    sigs = profile(stage)
    for item in items:
        item["keep"] = bool(signatures(item) & sigs)
    return sum(1 for i in items if i["keep"])
