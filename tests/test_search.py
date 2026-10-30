"""Finding a desk by what's in it."""
import search
from commands import parse


def desk(name, note="", items=(), steps=(), older=None):
    latest = {"brain_dump": note, "next_steps": list(steps), "windows": list(items), "cues": []}
    return {"name": name, "snapshots": ([older] if older else []) + [latest]}


TAB = {"title": "Union Find - LeetCode", "url": "https://leetcode.com/problems/graph-valid-tree/", "keep": True}
DESKS = [desk("cyber", "capturing the TCP handshake in Wireshark", steps=["Fix the display filter"]),
         desk("dsa", "union find works", [TAB]),
         desk("ai", "tuning the CNN", [{"title": "TCP in the wild", "keep": True}])]


def names(query, stages=DESKS):
    return [r["name"] for r in search.find(query, stages)]


def test_every_word_has_to_be_there():
    assert names("TCP handshake") == ["cyber"]
    assert names("TCP nothing") == []


def test_notes_count_more_than_what_was_open():
    assert names("tcp") == ["cyber", "ai"]


def test_finds_steps_addresses_and_filler_is_ignored():
    assert names("the display filter") == ["cyber"]
    assert names("leetcode.com") == ["dsa"]
    assert names("graph-valid-tree") == ["dsa"]


def test_unticked_things_are_not_in_the_desk():
    gone = [desk("x", items=[{"title": "Secret plans", "keep": False}])]
    assert names("secret", gone) == []


def test_older_versions_count():
    old = {"brain_dump": "kubernetes notes", "next_steps": [], "windows": [], "cues": []}
    assert names("kubernetes", [desk("infra", "moved on", older=old)]) == ["infra"]


def test_a_desks_own_name_counts():
    assert names("cyber") == ["cyber"]


def test_only_filler_finds_nothing():
    assert names("the my desk") == []


def test_long_text_is_cut_around_the_word():
    long = [desk("x", "word " * 40 + "kubernetes " + "word " * 40)]
    found = search.find("kubernetes", long)[0]["found"]
    assert "kubernetes" in found and len(found) <= search.SNIPPET + 2


def test_words_reach_the_search_command():
    assert parse("find the TCP notes") == ("search", "the TCP notes")
    assert parse("search for wireshark") == ("search", "wireshark")
    assert parse("which desk has the lecture") == ("search", "the lecture")
    assert parse("look for leetcode") == ("search", "leetcode")


def test_saying_it_shows_the_desks_to_open(shiori):
    view = shiori.say("find lofi")
    assert view["view"] == "message" and "Found" in view["title"]
    assert view["lines"][0]["say"].startswith("view ")


def test_nothing_found_says_so(shiori):
    view = shiori.say("find kubernetes")
    assert "kubernetes" in view["title"] and view["lines"]
