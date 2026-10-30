"""Recap, adding to a note, switching desks, and the weekly view."""
import store
from commands import parse


def test_words():
    assert parse("what was I doing")[0] == "recap"
    assert parse("switch to dsa") == ("switch", "dsa")
    assert parse("add to my note check labels") == ("add_note", "check labels")
    assert parse("my week")[0] == "week"


def test_recap_reopens_nothing(shiori):
    shiori.say("recap")
    assert shiori.opened == []


def test_add_to_note(shiori):
    shiori.say("view dsa")
    shiori.say("add to my note check the labels")
    assert "check the labels" in store.latest("dsa")["brain_dump"]


def test_switch_saves_this_desk_then_resumes(shiori):
    shiori.say("resume dsa")
    versions = len(store.load("dsa")["snapshots"])
    shiori.opened.clear()
    shiori.say("switch to shop-api")
    assert shiori.opened == ["shop-api"] and len(store.load("dsa")["snapshots"]) == versions + 1


def test_week_lists_recent_desks(shiori):
    assert len(shiori.say("my week")["lines"]) == 4
