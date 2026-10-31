"""Clearing or switching asks first when a window may hold unsaved work."""
import clear


def risky(shiori, monkeypatch):
    closes = []
    monkeypatch.setattr(clear, "unsaved", lambda items: ["● app.py - shop"])
    monkeypatch.setattr(clear, "close_items", lambda items: closes.append(items) or (["x"], []))
    return closes


def test_unsaved_marks_in_titles():
    for title in ("● app.py - shop - Visual Studio Code", "*notes.txt - Notepad", "notes.txt*"):
        assert clear.looks_unsaved(title)
    for title in ("app.py - shop", "5 * 3 - Calculator"):
        assert not clear.looks_unsaved(title)


def test_save_and_clear_asks_then_closes(shiori, monkeypatch):
    closes = risky(shiori, monkeypatch)
    shiori.say("save my desk")
    view = shiori.say("save as dsa and clear")
    assert "unsaved work" in view["title"] and not closes
    shiori.say("close anyway")
    assert len(closes) == 1


def test_saying_no_closes_nothing_but_the_desk_is_saved(shiori, monkeypatch):
    closes = risky(shiori, monkeypatch)
    shiori.say("save my desk")
    shiori.say("save as newdesk and clear")
    view = shiori.say("keep them open")
    assert not closes and "Nothing was closed" in view["message"]


def test_moving_on_closes_nothing(shiori, monkeypatch):
    closes = risky(shiori, monkeypatch)
    shiori.say("save my desk")
    shiori.say("save as newdesk and clear")
    shiori.say("show my desks")
    assert not closes and shiori.c.confirm_close is None


def test_switch_waits_too(shiori, monkeypatch):
    closes = risky(shiori, monkeypatch)
    view = shiori.say("switch to dsa")
    assert "unsaved work" in view["title"] and not closes and not shiori.opened
    shiori.say("yes")
    assert len(closes) == 1 and shiori.opened == ["dsa"]
