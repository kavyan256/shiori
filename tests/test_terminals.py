"""Terminals: the right folder, the same Python environment, and safe commands in bash too."""
import os
import subprocess
import time

import controller
import psprofile
import terminals


def tab(shell="powershell.exe", command="", rerun=None, **more):
    return {**terminals.item(shell, r"C:\work", command), **({"rerun": rerun} if rerun is not None else {}), **more}


def test_powershell_activates_the_environment_then_runs_the_command(tmp_path):
    venv = tmp_path / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "Scripts" / "Activate.ps1").write_text("")
    args = terminals._shell_args(tab(command="npm run dev", venv=str(venv)))
    assert args[:3] == ["powershell.exe", "-NoExit", "-Command"]
    assert args[3] == f"& '{venv}\\Scripts\\Activate.ps1'\\; npm run dev"


def test_a_path_with_a_quote_stays_one_path(tmp_path):
    venv = tmp_path / "it's"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "Scripts" / "Activate.ps1").write_text("")
    assert "it''s" in terminals._shell_args(tab(venv=str(venv)))[3]


def test_cmd_activates_too(tmp_path):
    venv = tmp_path / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "Scripts" / "activate.bat").write_text("")
    args = terminals._shell_args(tab("cmd.exe", "flask run", venv=str(venv)))
    assert args == ["cmd.exe", "/k", f'call "{venv}\\Scripts\\activate.bat" & flask run']


def test_a_deleted_environment_is_just_left_out():
    assert terminals._shell_args(tab(venv=r"C:\gone\.venv")) == ["powershell.exe"]


def test_conda_environment():
    assert terminals._shell_args(tab(conda="ml-lab"))[3] == "conda activate ml-lab"


def test_commands_that_are_not_safe_never_run_even_with_an_environment():
    args = terminals._shell_args(tab(command="git push", conda="ml-lab"))
    assert "git push" not in args[3]


def test_bash_reruns_safe_commands_and_stays_open():
    assert terminals._shell_args(tab("bash.exe", "npm run dev")) == ["bash.exe", "-lc", "npm run dev\\; exec bash"]


def test_bash_with_nothing_to_run_is_just_a_shell():
    assert terminals._shell_args(tab("bash.exe")) == ["bash.exe"]
    assert terminals._shell_args(tab("bash.exe", "rm -rf build")) == ["bash.exe"]


def test_the_row_says_the_environment_comes_back():
    assert "venv" in controller.row_meta(tab(venv=r"C:\x\.venv"))
    assert "ml-lab" in controller.row_meta(tab(conda="ml-lab", command="npm run dev"))


class Shell:
    def __init__(self, pid, started=0):
        self.pid = pid
        self.started = started

    def create_time(self):
        return self.started


def test_a_reported_folder_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(terminals, "SHELLS_DIR", tmp_path)
    (tmp_path / "7.txt").write_text(str(tmp_path), encoding="utf-8")
    assert terminals.reported_folder(Shell(7)) == str(tmp_path)


def test_a_report_from_an_older_process_with_the_same_id_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(terminals, "SHELLS_DIR", tmp_path)
    (tmp_path / "7.txt").write_text(str(tmp_path), encoding="utf-8")
    assert terminals.reported_folder(Shell(7, started=time.time() + 60)) == ""


def test_a_reported_folder_that_is_gone_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(terminals, "SHELLS_DIR", tmp_path)
    (tmp_path / "7.txt").write_text(r"C:\gone\away", encoding="utf-8")
    assert terminals.reported_folder(Shell(7)) == ""


def test_tidy_removes_reports_from_closed_tabs(tmp_path, monkeypatch):
    monkeypatch.setattr(terminals, "SHELLS_DIR", tmp_path)
    (tmp_path / f"{os.getpid()}.txt").write_text("x")
    (tmp_path / "4000000.txt").write_text("x")
    terminals.tidy()
    assert [p.stem for p in tmp_path.iterdir()] == [str(os.getpid())]


# --- the PowerShell profile, on scratch files only -----------------------------------------
def test_adding_keeps_what_was_there_and_removing_restores_it(tmp_path):
    path = tmp_path / "profile.ps1"
    path.write_text("Set-Alias g git\n", encoding="utf-8")
    psprofile.add(path, tmp_path)
    assert psprofile.has_block(path) and path.read_text(encoding="utf-8").startswith("Set-Alias g git\n")
    psprofile.remove(path)
    assert path.read_text(encoding="utf-8") == "Set-Alias g git\n"
    assert (tmp_path / "profile.ps1.shiori-backup").read_text(encoding="utf-8") == "Set-Alias g git\n"


def test_adding_twice_adds_once(tmp_path):
    path = tmp_path / "profile.ps1"
    psprofile.add(path, tmp_path)
    psprofile.add(path, tmp_path)
    assert path.read_text(encoding="utf-8").count(psprofile.BEGIN) == 1


def test_a_utf16_profile_stays_utf16(tmp_path):
    path = tmp_path / "profile.ps1"
    path.write_text("# नमस्ते\n", encoding="utf-16")
    psprofile.add(path, tmp_path)
    assert path.read_bytes()[:2] in (b"\xff\xfe", b"\xfe\xff")
    assert "नमस्ते" in path.read_text(encoding="utf-16")


def test_the_block_really_reports_the_folder_and_keeps_your_prompt(tmp_path):
    """A real PowerShell, running only this scratch file."""
    script = tmp_path / "profile.ps1"
    script.write_text("function prompt { 'MINE> ' }\n", encoding="utf-8")
    psprofile.add(script, tmp_path)
    run = f". '{script}'; Set-Location C:\\Windows; prompt; $PID"
    done = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", run],
                          capture_output=True, text=True, timeout=30)
    lines = done.stdout.split()
    assert lines[0] == "MINE>"
    assert (tmp_path / f"{lines[1]}.txt").read_text(encoding="utf-8") == r"C:\Windows"
