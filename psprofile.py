"""An optional line in your PowerShell profile, so idle tabs come back in the right folder.

PowerShell's `cd` doesn't change what Windows sees, so from outside an idle tab only shows the
folder it started in. This adds a small block to your profile: at each prompt, if the folder
changed, the tab writes it to data/shells/<process id>.txt, which terminals.py reads.

It's off until you turn it on from the tray, sits between two marker lines at the end of the
profile, and turning it off takes out exactly that block. The first change keeps a backup.
"""
import ctypes
import shutil
import subprocess
from pathlib import Path

from paths import DATA

SHELLS_DIR = DATA / "shells"
BEGIN = "# >>> Shiori: reports this tab's folder, so it can come back in the right place >>>"
END = "# <<< Shiori <<<"
CSIDL_PERSONAL = 5  # Windows' number for your Documents folder
BLOCKED = {"Restricted", "AllSigned"}  # PowerShell won't run an edited profile under these


def block(folder=SHELLS_DIR):
    where = str(folder).replace("'", "''")
    return f"""{BEGIN}
$global:ShioriPrompt = $function:prompt
function global:prompt {{
    try {{
        if ($PWD.Provider.Name -eq 'FileSystem' -and $PWD.ProviderPath -ne $global:ShioriFolder) {{
            $global:ShioriFolder = $PWD.ProviderPath
            [IO.File]::WriteAllText('{where}\\' + $PID + '.txt', $PWD.ProviderPath)
        }}
    }} catch {{}}
    & $global:ShioriPrompt
}}
{END}
"""


def profiles():
    """Windows PowerShell's and PowerShell 7's profile for you. Documents may be moved by OneDrive."""
    documents = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None, 0, documents)
    return [Path(documents.value) / folder / "Microsoft.PowerShell_profile.ps1" for folder in ("WindowsPowerShell", "PowerShell")]


def policy():
    """What PowerShell will run. Shiori only reads this: changing it is your call."""
    done = subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Get-ExecutionPolicy"], capture_output=True,
                          text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    return done.stdout.strip()


def _read(path):
    """A profile's text and its encoding, kept the same when it's written back."""
    if not path.exists():
        return "", "utf-8"
    raw = path.read_bytes()
    encoding = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig" if raw[:3] == b"\xef\xbb\xbf" else "utf-8"
    return raw.decode(encoding), encoding


def has_block(path):
    return BEGIN in _read(path)[0]


def _write(path, text, encoding):
    backup = path.with_name(path.name + ".shiori-backup")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding, newline="\n")


def add(path, folder=SHELLS_DIR):
    if has_block(path):
        return
    text, encoding = _read(path)
    folder.mkdir(parents=True, exist_ok=True)
    gap = "\n" if text and not text.endswith("\n") else ""
    _write(path, f"{text}{gap}{block(folder)}", encoding)


def remove(path):
    text, encoding = _read(path)
    if BEGIN not in text or END not in text:
        return
    before, rest = text.split(BEGIN, 1)
    after = rest.split(END, 1)[1].removeprefix("\n")
    _write(path, before + after, encoding)


def is_on():
    return any(has_block(p) for p in profiles())


def turn_on():
    """Returns '' if done, else what stopped it."""
    allowed = policy()
    if allowed in BLOCKED:
        return allowed
    for path in profiles():
        add(path)
    return ""


def turn_off():
    for path in profiles():
        remove(path)
