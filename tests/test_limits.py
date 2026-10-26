"""Nothing that can hang (Office with a dialog open, an offline network drive) can freeze Shiori."""
import os
import time

import cues
import limits
import office
import restore
import settings


def test_within_gives_up_on_a_hang():
    started = time.monotonic()
    assert limits.within(0.5, time.sleep, 30, default="gave up") == "gave up"
    assert time.monotonic() - started < 2


def test_within_returns_the_default_on_an_error():
    assert limits.within(1, lambda: 1 / 0, default=[]) == []


def test_exist_gives_up_on_hanging_paths_together(monkeypatch):
    real = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda p: time.sleep(30) if p.startswith("\\\\") else real(p))
    started = time.monotonic()
    found = limits.exist([r"\\nas\a.xlsx", r"\\nas\b.xlsx", os.getcwd()])
    assert found == {r"\\nas\a.xlsx": False, r"\\nas\b.xlsx": False, os.getcwd(): True}
    assert time.monotonic() - started < limits.FILE_SECONDS + 1  # not 1.5 s per path


def test_office_not_answering_means_no_files(monkeypatch):
    monkeypatch.setattr(office, "_current", lambda: time.sleep(30))
    monkeypatch.setattr(limits, "OFFICE_SECONDS", 0.5)
    assert office.current() == []
    monkeypatch.setattr(office, "_close", lambda path: time.sleep(30))
    assert office.close(r"C:\x.xlsx") is False


def test_resume_skips_a_file_on_a_missing_drive(monkeypatch):
    monkeypatch.setattr(office, "current", lambda: [])
    monkeypatch.setattr(restore, "list_windows", lambda: [])
    monkeypatch.setattr(restore.browser, "fresh_tabs", lambda apps: {})
    snap = {"windows": [{"kind": "file", "app": "notepad.exe", "path": r"Z:\gone\todo.txt", "title": "todo.txt",
                         "keep": True}]}
    actions, skipped = restore.plan(snap)
    assert actions == [] and "isn't there" in skipped[0]


def test_git_cues_survive_a_missing_folder():
    out = cues.compare([{"repo": "x", "path": r"Z:\gone\repo", "branch": "main", "changed": 0}])
    assert out[0]["now_branch"] == ""


def test_settings_defaults_and_bad_values():
    assert settings.load() == settings.DEFAULTS
    settings.change("hotkey", "Ctrl+Alt+D")
    settings.change("desk_pictures", False)
    assert settings.get("hotkey") == "Ctrl+Alt+D" and settings.get("desk_pictures") is False
    settings.change("hotkey", "Win+Q")  # not one of the choices: back to the default
    assert settings.get("hotkey") == "Ctrl+Alt+S"
    settings.FILE.write_text("{broken", encoding="utf-8")
    assert settings.load() == settings.DEFAULTS


def test_real_icons_for_files_and_folders():
    import icons
    assert icons.for_item({"kind": "file", "path": r"\offline-nas\share\Q3 budget.xlsx"}).startswith("data:image/png")
    assert icons.for_item({"app": "explorer.exe"}).startswith("data:image/png")
    assert icons.for_item({"app": "gone.exe", "exe": r"C:\nowhere\gone.exe"}) == ""  # the bar shows a letter
