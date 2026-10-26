"""What Shiori does with what you say: the save → note → name flow, resume, delete, undo,
and the messy input speech gives you (half words, filler, scraps, repeats)."""
import pytest

import store
from conftest import kept, line_texts


# --- the main flow --------------------------------------------------------------------------
def test_save_takes_three_steps(shiori):
    v = shiori.say("save my desk")
    assert v["view"] == "draft" and len(kept(v)) == 3
    v = shiori.say("drop 3")
    assert kept(v) == [True, True, False]
    v = shiori.say("I was fixing the login loop, next write the test")
    assert v["note"] == "I was fixing the login loop" and v["steps"] == ["Write the test"]
    v = shiori.say("save as login")
    assert v["view"] == "park" and v["name"] == "login"
    snap = store.latest("login")
    assert snap["brain_dump"] == "I was fixing the login loop"
    assert [i["keep"] for i in snap["windows"]] == [True, True, False]


def test_resume_brings_back_the_note(shiori):
    v = shiori.say("resume dsa")
    assert v["view"] == "resume" and v["name"] == "dsa" and shiori.opened == ["dsa"]


def test_resume_alone_takes_the_newest(shiori):
    v = shiori.say("resume")
    assert v["view"] == "resume" and shiori.opened == [store.list_stages()[0]["name"]]


def test_saving_again_adds_a_version(shiori):
    shiori.say("save my desk")
    v = shiori.say("save as dsa")
    assert "version 2" in v["message"] and len(store.load("dsa")["snapshots"]) == 2


# --- 1. a scrap of a name never opens a desk -----------------------------------------------
@pytest.mark.parametrize("said, verb", [("resume s", "Resume"), ("start d", "Start"), ("resume sh", "Resume"),
                                        ("view d", "View"), ("delete s", "Delete")])
def test_scrap_of_a_name_asks_which(shiori, said, verb):
    v = shiori.say(said)
    assert v["view"] == "message" and not shiori.opened and shiori.c.confirm_delete is None
    assert line_texts(v) and all(t.startswith(verb) for t in line_texts(v))


def test_a_real_two_letter_name_still_resumes(shiori):
    assert shiori.say("resume Q3")["view"] == "resume" and shiori.opened == ["Q3"]


# --- 2-3. bare verbs, noise and cut-off scraps never change the note --------------------------
@pytest.mark.parametrize("said", ["drop", "keep", "remove"])
def test_bare_drop_asks_which(shiori, said):
    shiori.say("save my desk")
    shiori.say("I was fixing the login loop")
    v = shiori.say(said)
    assert "which" in v["message"].lower() and v["note"] == "I was fixing the login loop"


@pytest.mark.parametrize("said", ["Thank you.", "Thanks for watching!", "um", "uh huh", "...", "dr", "I was",
                                  "fixing the", "next", "so"])
def test_noise_never_replaces_the_note(shiori, said):
    shiori.say("save my desk")
    shiori.say("I was fixing the login loop, next write the test")
    v = shiori.say(said)
    assert v["note"] == "I was fixing the login loop" and v["steps"] == ["Write the test"]


def test_a_short_note_said_on_purpose_is_kept(shiori):
    shiori.say("save my desk")
    assert shiori.say("note: graphs")["note"] == "graphs"


def test_noise_at_home_is_quiet(shiori):
    v = shiori.say("Thank you.")
    assert v["view"] == "home" and "catch" in v["message"]


# --- 4-5. "save as" with nothing after, undo while saving ---------------------------------------
def test_save_as_alone_asks_for_the_name(shiori):
    shiori.say("save my desk")
    v = shiori.say("save as")
    assert v["view"] == "ask" and v.get("suggested")


def test_undo_while_saving_steps_back(shiori):
    shiori.say("save my desk")
    shiori.say("drop 3")
    shiori.say("I was fixing the login loop")
    assert shiori.say("undo")["note"] == ""
    assert kept(shiori.say("undo")) == [True, True, True]
    assert "Nothing to undo" in shiori.say("undo")["message"]


# --- 6-7. the long-name and delete questions -------------------------------------------------
@pytest.mark.parametrize("said, want", [("yes", "saved"), ("keep it", "saved"), ("no", "draft"),
                                        ("Thank you.", "asks again"), ("shop", "renamed")])
def test_long_name_question(shiori, said, want):
    shiori.say("save my desk")
    shiori.say("save as fixing the login bug in the auth page next")
    v = shiori.say(said)
    got = ("saved" if v["view"] == "park" and v["name"].startswith("fixing") else
           "renamed" if v["view"] == "park" and v["name"] == "shop" else
           "draft" if v["view"] == "draft" else "asks again" if v["view"] == "namecheck" else v["view"])
    assert got == want


@pytest.mark.parametrize("said, want", [("y", "deleted"), ("delete it", "deleted"), ("sure", "deleted"),
                                        ("no wait", "kept"), ("", "kept"), ("hmm", "asks again"),
                                        ("show my desks", "moved on")])
def test_delete_question(shiori, said, want):
    shiori.say("delete dsa")
    v = shiori.say(said)
    exists = bool(store.load("dsa"))
    got = ("deleted" if not exists else "asks again" if v["view"] == "confirm" else
           "moved on" if v["view"] == "home" and "Kept" not in v.get("message", "") else "kept")
    assert got == want


def test_undo_puts_a_deleted_desk_back(shiori):
    shiori.say("delete dsa")
    shiori.say("yes")
    assert store.load("dsa") is None
    shiori.say("undo")
    assert store.load("dsa")


# --- 8. repeats ------------------------------------------------------------------------------------
def test_a_phrase_said_twice_counts_once(shiori):
    v = shiori.say("save my desk save my desk")
    assert v["view"] == "draft" and not v["name"] and not v["note"]
    assert shiori.say("drop 3 drop 3")["message"].startswith("Dropped 3")
    assert shiori.say("I was fixing it. I was fixing it.")["note"] == "I was fixing it"


# --- 9-17. half words, filler, misheard words ---------------------------------------------------
@pytest.mark.parametrize("said, starts", [("res", "Resume"), ("resu", "Resume"), ("del", "Delete"), ("u", "Undo")])
def test_half_words_offer_commands(shiori, said, starts):
    v = shiori.say(said)
    assert v.get("title") == "Did you mean…?" and not shiori.opened
    assert all(t.startswith(starts) for t in line_texts(v))


@pytest.mark.parametrize("said, view", [("um, show my desks", "home"), ("hmm resume dsa", "resume"),
                                        ("well, save my desk", "draft")])
def test_filler_before_a_command(shiori, said, view):
    assert shiori.say(said)["view"] == view


def test_drop_all_and_keep_everything(shiori):
    shiori.say("save my desk")
    assert kept(shiori.say("drop all")) == [False] * 3
    assert kept(shiori.say("keep everything")) == [True] * 3


def test_pin_with_no_desk_on_screen_asks_which(shiori):
    shiori.say("show my desks")
    v = shiori.say("pin")
    assert v.get("title") == "Pin which desk?"


def test_two_desks_at_once_resumes_one(shiori):
    v = shiori.say("resume shop api and dsa")
    assert shiori.opened == ["shop-api"] and "resume dsa" in v["message"]


@pytest.mark.parametrize("said, desk", [("rezoom shop api", "shop-api"), ("resum dsa", "dsa")])
def test_misheard_command_words(shiori, said, desk):
    shiori.say(said)
    assert shiori.opened == [desk]


def test_inside_a_note_nothing_is_corrected(shiori):
    shiori.say("save my desk")
    v = shiori.say("Restart the server first, next fix the login")
    assert v["view"] == "draft" and v["note"].startswith("Restart")


@pytest.mark.parametrize("said", ["drop 3", "keep spotify", "cancel"])
def test_saving_commands_at_home_explain(shiori, said):
    v = shiori.say(said)
    assert v["view"] == "home" and "Nothing is being saved" in v["message"]


def test_resume_while_saving_keeps_the_draft(shiori):
    shiori.say("save my desk")
    v = shiori.say("resume dsa")
    assert "unsaved desk is kept" in v["message"] and shiori.c.draft
