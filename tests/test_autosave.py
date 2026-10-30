"""The quiet save: what a restart or a crash leaves behind, and bringing it back."""
import json
from datetime import datetime, timedelta

import autosave
from commands import parse

ITEMS = [{"app": "code.exe", "title": "a", "keep": True}, {"app": "x.exe", "title": "b", "keep": False}]


def crash():
    """Shiori stopped without quitting, then started again."""
    autosave.at_start()


def recovered(**changes):
    session = json.loads(autosave.RECOVERED.read_text(encoding="utf-8")) | changes
    autosave.RECOVERED.write_text(json.dumps(session), encoding="utf-8")


def test_nothing_open_never_replaces_a_saved_session():
    autosave.write(ITEMS, [])
    assert not autosave.write([], [])
    assert not autosave.write([ITEMS[1]], [])  # only unticked things open
    assert json.loads(autosave.FILE.read_text(encoding="utf-8"))["windows"] == ITEMS


def test_same_things_open_keeps_the_first_time_but_updates_the_layout():
    autosave.write(ITEMS, [])
    first = json.loads(autosave.FILE.read_text(encoding="utf-8")) | {"parked_at": "2020-01-01T00:00:00"}
    autosave.FILE.write_text(json.dumps(first), encoding="utf-8")
    autosave.write(list(reversed(ITEMS)), [{"app": "code.exe"}])
    now = json.loads(autosave.FILE.read_text(encoding="utf-8"))
    assert now["parked_at"] == "2020-01-01T00:00:00" and now["layout"] == [{"app": "code.exe"}]


def test_a_normal_quit_leaves_nothing_to_recover():
    autosave.write(ITEMS, [])
    autosave.finished()
    crash()
    assert autosave.offer() is None


def test_a_crash_is_offered_once_started_again():
    autosave.write(ITEMS, [])
    crash()
    assert autosave.offer()["windows"] == ITEMS


def test_a_second_restart_keeps_the_offer():
    autosave.write(ITEMS, [])
    crash()
    crash()
    assert autosave.offer()


def test_an_old_session_is_dropped():
    autosave.write(ITEMS, [])
    crash()
    recovered(checked_at=(datetime.now() - timedelta(days=4)).isoformat(timespec="seconds"))
    assert autosave.offer() is None and not autosave.RECOVERED.exists()


def test_saving_a_desk_afterwards_drops_the_offer(shiori):
    autosave.write(ITEMS, [])
    crash()
    recovered(checked_at="2020-01-01T00:00:00")
    assert autosave.offer() is None


def fresh_offer():
    autosave.write(ITEMS, [])
    crash()
    recovered(checked_at="2999-01-01T00:00:00")  # newer than the test desks


def test_home_offers_it_and_restoring_uses_it_up(shiori):
    fresh_offer()
    assert "restore last session" in shiori.say("show my desks")["message"]
    view = shiori.say("restore last session")
    assert view["view"] == "resume" and view["verb"] == "Restored"
    assert shiori.opened == ["Last session"]
    assert autosave.offer() is None
    assert "No earlier session" in shiori.say("restore last session")["message"]


def test_forget_last_session(shiori):
    fresh_offer()
    shiori.say("forget last session")
    assert autosave.offer() is None


def test_session_words_reach_the_right_command():
    assert parse("restore last session")[0] == "last_session"
    assert parse("Restore my last session.")[0] == "last_session"
    assert parse("previous session")[0] == "last_session"
    assert parse("forget the last session")[0] == "forget_session"
    assert parse("resume")[0] == "resume"
    assert parse("resume dsa") == ("resume", "dsa")
