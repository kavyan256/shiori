"""Reading what you said: commands, notes, names, which windows you meant."""
import pytest

from commands import cut_off, fix_command_word, parse, parse_draft, pick_windows, without_repeat


@pytest.mark.parametrize("said, kind", [("Save my desk", "park"), ("save my desk.", "park"), ("Show my desks", "list"),
                                        ("View coding", "view"), ("Resume coding.", "resume"),
                                        ("Delete coding", "delete"), ("Thank you.", "noise")])
def test_parse(said, kind):
    assert parse(said)[0] == kind


def test_parse_keeps_the_name():
    assert parse("resume shop api")[1].lower() == "shop api"


@pytest.mark.parametrize("said, kind", [("drop 3", "drop"), ("Drop YouTube.", "drop"), ("keep 3", "keep"),
                                        ("Save it as acads.", "save"), ("cancel", "cancel"),
                                        ("I was fixing kernel.h, next build it.", "note")])
def test_parse_draft(said, kind):
    assert parse_draft(said)[0] == kind


def test_save_as_names_it():
    assert parse_draft("save as coding")[:2] == ("save", "coding")


@pytest.mark.parametrize("said, fixed", [("rezoom shop api", "resume shop api"), ("delte dsa", "delete dsa"),
                                         ("resu", "resu"), ("hello there", "hello there")])
def test_fix_command_word(said, fixed):
    assert fix_command_word(said) == fixed


@pytest.mark.parametrize("said, scrap", [("I was", True), ("fixing the", True), ("I was fixing it", False),
                                         ("reading chapter 3", False)])
def test_cut_off(said, scrap):
    assert bool(cut_off(said)) == scrap


def test_without_repeat():
    assert without_repeat("save my desk save my desk") == "save my desk"
    assert without_repeat("save my desk") == "save my desk"


WINDOWS = [{"app": "code.exe", "title": "auth.js - shop-api"}, {"app": "chrome.exe", "title": "PR #42"},
           {"app": "spotify.exe", "title": "lofi beats"}]


@pytest.mark.parametrize("said, picked", [("3", [2]), ("two and three", [1, 2]), ("spotify", [2]), ("all", [0, 1, 2])])
def test_pick_windows(said, picked):
    assert sorted(pick_windows(said, WINDOWS)) == picked
