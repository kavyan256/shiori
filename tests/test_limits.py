"""Nothing that can hang (Office with a dialog open, an offline network drive) can freeze Shiori."""
import os
import time

import cues
import layout
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


# --- window positions ----------------------------------------------------------------------
class Win:
    def __init__(self, hwnd, app, title="", targets=(), group="FULL", minimized=False):
        self.hwnd, self.app, self.title, self.targets = hwnd, app, title, list(targets)
        self.group, self.minimized, self.rect, self.maximized = group, minimized, (1, 2, 3, 4), False


def place(app, title="", targets=(), rect=(0, 0, 100, 100)):
    return {"app": app, "title": title, "targets": list(targets), "rect": list(rect), "maximized": False}


def test_layout_leaves_out_minimized_and_skipped_windows():
    found = layout.of([Win(1, "code.exe"), Win(2, "code.exe", minimized=True), Win(3, "x.exe", group="SKIP")])
    assert [p["app"] for p in found] == ["code.exe"]


def test_layout_only_restores_what_was_kept():
    snap = {"windows": [{"app": "code.exe", "targets": ["C:/a"]}, {"app": "code.exe", "targets": ["C:/b"], "keep": False},
                        {"app": "notepad.exe", "keep": False}],
            "layout": [place("code.exe", targets=["c:/A"]), place("code.exe", targets=["C:/b"]), place("notepad.exe")]}
    assert [p["targets"] for p in layout.wanted(snap)] == [["c:/A"]]


def test_layout_old_desks_have_no_positions():
    assert layout.wanted({"windows": [{"app": "code.exe"}]}) == []


def test_layout_folders_match_their_own_window():
    a, b = place("code.exe", targets=["C:/a"]), place("code.exe", targets=["C:/b"])
    win_b, win_a = Win(1, "code.exe", targets=["c:/b"]), Win(2, "code.exe", targets=["c:/a"])
    assert sorted(layout.pairs([a, b], [win_b, win_a]), key=lambda fit: fit[1].hwnd) == [(b, win_b), (a, win_a)]


def test_layout_a_folder_never_takes_a_window_on_another_folder():
    assert layout.pairs([place("code.exe", targets=["C:/a"])], [Win(1, "code.exe", targets=["C:/z"]), Win(2, "code.exe")]) == []


def test_layout_titles_pick_the_right_window_of_an_app():
    a, b = place("notepad.exe", "a.txt - Notepad"), place("notepad.exe", "b.txt - Notepad")
    win = Win(1, "notepad.exe", "b.txt - Notepad")
    assert layout.pairs([a, b], [win]) == [(b, win)]


def run_settle(places, windows_at, before=(), wait=8):
    """settle() on a fake clock; windows_at(second) is what's open then. Returns the moves."""
    now, moves = [0.0], []
    layout.settle(places, set(before), look=lambda: windows_at(now[0]), move=lambda h, p: moves.append((now[0], h)),
                  wait=wait, sleep=lambda s: now.__setitem__(0, now[0] + s), clock=lambda: now[0])
    return moves


def test_layout_never_moves_a_window_that_was_already_open():
    assert run_settle([place("code.exe", "x")], lambda t: [Win(1, "code.exe", "x")], before=[1]) == []


def test_layout_moves_a_window_when_it_appears_and_once_more():
    moves = run_settle([place("code.exe", "x")], lambda t: [Win(7, "code.exe", "x")] if t >= 3 else [])
    assert [m[1] for m in moves] == [7, 7] and moves[1][0] - moves[0][0] >= layout.MOVE_AGAIN


def test_layout_waits_for_a_better_title_before_settling_for_the_app():
    seen = lambda t: [Win(7, "word.exe", "Opening…")]
    moves = run_settle([place("word.exe", "report.docx - Word")], seen)
    assert moves and moves[0][0] >= layout.PATIENT_SECONDS


def test_layout_gives_up_if_the_window_never_opens():
    assert run_settle([place("code.exe", "x")], lambda t: []) == []
