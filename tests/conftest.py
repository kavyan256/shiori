"""Shared setup: every test runs on a scratch data folder, with fake open windows, and
nothing ever opens, closes or reads your real desks.

    pip install -r requirements.txt pytest
    pytest
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Before any Shiori module is imported: paths.py reads STAGE_DATA once, at import
DATA = Path(tempfile.mkdtemp(prefix="shiori-tests-"))
os.environ["STAGE_DATA"] = str(DATA)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import clear  # noqa: E402
import controller  # noqa: E402
import office  # noqa: E402
import restore  # noqa: E402
import store  # noqa: E402

# What "save my desk" finds: three items, the third one (Spotify) easy to drop
FAKE_ITEMS = [
    {"kind": "window", "app": "code.exe", "title": "auth.js - shop-api - Visual Studio Code", "group": "FULL",
     "targets": [], "exe": "", "keep": True},
    {"kind": "tab", "browser": "chrome", "app": "chrome.exe", "window": 1, "title": "Fix login · PR #42",
     "url": "https://github.com/x/shop-api/pull/42", "keep": True},
    {"kind": "tab", "browser": "chrome", "app": "chrome.exe", "window": 1, "title": "lofi beats",
     "url": "https://open.spotify.com/x", "keep": True},
]
DESKS = ("shop-api", "dsa", "DBMS unit 3", "Q3")


class Shiori:
    """A controller with fake windows. `opened` lists the desks a resume would have reopened."""

    def __init__(self):
        self.c = controller.Controller()
        self.opened = []

    def say(self, text):
        return self.c.handle(text)

    def fresh(self):
        """Back to the home screen with nothing pending, as if the bar was just opened."""
        self.c.draft = self.c.confirm_delete = self.c.checking_name = self.c.confirm_close = None
        self.c.asking_name = False
        self.opened.clear()


@pytest.fixture(autouse=True)
def clean_data():
    shutil.rmtree(DATA, ignore_errors=True)
    DATA.mkdir(parents=True)
    yield
    shutil.rmtree(DATA, ignore_errors=True)


@pytest.fixture
def shiori(monkeypatch):
    """Four saved desks (shop-api, dsa, DBMS unit 3, Q3) and a controller on the home screen."""
    s = Shiori()
    monkeypatch.setattr(controller, "current_items", lambda: [dict(i) for i in FAKE_ITEMS])
    monkeypatch.setattr(controller, "list_windows", lambda: [])
    monkeypatch.setattr(office, "current", lambda: [])
    monkeypatch.setattr(restore, "reopen", lambda snap, name=None, **k: (s.opened.append(name) or ["(stub)"], []))
    monkeypatch.setattr(clear, "close_items", lambda items: (["(stub)"], []))
    monkeypatch.setattr(clear, "unsaved", lambda items: [])
    for name in DESKS:
        s.say("save my desk")
        s.say(f"save as {name}")
    s.fresh()
    return s


def kept(view):
    """The keep flags of every item in a draft view, in order."""
    return [i["keep"] for g in view["groups"] for i in g["items"]]


def line_texts(view):
    return [line["text"] for line in view.get("lines", []) if isinstance(line, dict)]
