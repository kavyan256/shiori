"""The draft's Name and Note boxes are plain text: words in them never act."""
import store


def test_fields_are_saved_as_typed(shiori):
    shiori.say("save my desk")
    shiori.c.set_fields("save and clear", "remember to clear the cache and clear it")
    shiori.say("save")
    assert store.latest("save and clear")["brain_dump"] == "remember to clear the cache and clear it"


def test_empty_name_uses_the_suggestion(shiori):
    shiori.say("save my desk")
    shiori.c.set_fields("", "a note")
    assert shiori.say("save")["view"] == "park"


def test_a_note_in_the_box_is_not_a_command(shiori):
    shiori.say("save my desk")
    view = shiori.say("remember to clear the cache")
    assert view["view"] == "draft" and "clear the cache" in (view["note"] + " ".join(view["steps"])).lower()


def test_fields_without_a_draft_do_nothing(shiori):
    shiori.c.set_fields("x", "y")
    assert shiori.c.draft is None
