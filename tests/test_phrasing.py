"""How people really say things, and sentences that must stay notes."""
import pytest

import store
from commands import parse, parse_draft


@pytest.mark.parametrize("said, command", [
    ("save everything", "park"), ("save my stuff", "park"), ("save and clear", "park"), ("clear my desk", "park"),
    ("hey shiori save my desk", "park"), ("bring back dsa", "resume"), ("pick up dsa", "resume"),
    ("retrieve", "list"), ("Retrieve.", "list"), ("retrieve my desks", "list"), ("retrieve desk", "list"), ("retrieve dsa", "resume"),
    ("list dsa", "view"), ("list", "list"), ("list my desks", "list"), ("list all desks", "list"),
    ("save", "park"), ("Save.", "park"), ("swap to dsa", "switch"), ("what have i saved", "list"), ("get rid of dsa", "delete"),
    ("remind me what i was doing", "recap"), ("where is the tcp lecture", "search"), ("go back", "undo"),
    ("restore my session", "last_session"),
])
def test_home_phrases(said, command):
    assert parse(said)[0] == command


@pytest.mark.parametrize("said, command", [
    ("save this", "save"), ("looks good save it", "save"), ("name this dsa", "save"), ("uncheck 3", "drop"),
    ("Steve as Gadit", "save"), ("forget it", "cancel"), ("don't save", "cancel"), ("save my desk", "park"),
    ("cancel the subscription next week", "note"), ("save the database backup before you leave", "note"),
    ("resume writing chapter two next", "note"), ("keep working on the parser next time", "note"),
    ("drop the table was the mistake i made", "note"),
])
def test_draft_phrases(said, command):
    assert parse_draft(said)[0] == command


def test_saying_save_my_desk_twice_saves_nothing(shiori):
    shiori.say("save my desk")
    assert shiori.say("save my desk")["view"] == "draft"


def test_opening_a_desk_in_few_words(shiori):
    assert parse("open")[0] == parse("load")[0] == "list"
    assert parse("open dsa") == ("resume", "dsa")
    shiori.say("dsa.")
    assert shiori.opened == ["dsa"]


def test_recap_after_deleting_the_desk_you_resumed(shiori):
    shiori.say("resume dsa")
    shiori.say("delete dsa")
    shiori.say("yes")
    assert shiori.say("recap")["view"] == "message"


def test_a_hindi_name_works(shiori):
    shiori.say("save my desk")
    shiori.say("save as गणित")
    assert store.load("गणित")
