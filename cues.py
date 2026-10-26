"""Git cues: for each repo in a park, the branch, what's uncommitted and the last commit.

  {"repo": "ka-OS", "path": "C:\\…\\ka-OS", "branch": "fix-login", "changed": 3,
   "last_commit": "Add kernel header"}

For a developer, "where was I" is mostly the branch and the diff. Saved when you
park; on resume Shiori compares with now ("you were on fix-login, now on main").
Read-only: Shiori only ever runs git status / rev-parse / log, never anything that changes a repo.
"""
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import limits

GIT = shutil.which("git")


def repo_root(folder):
    """The repo a folder belongs to (it or a parent has .git), or None."""
    try:
        path = Path(folder).resolve()
    except (OSError, ValueError):
        return None
    for p in (path, *path.parents):
        if (p / ".git").exists():
            return p
    return None


def _git(root, *args):
    result = subprocess.run([GIT, "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=4, creationflags=subprocess.CREATE_NO_WINDOW)
    return result.stdout.strip() if result.returncode == 0 else ""


def cue(root):
    try:
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if branch == "HEAD":  # detached: show the commit instead
            branch = "detached at " + _git(root, "rev-parse", "--short", "HEAD")
        status = _git(root, "status", "--porcelain")
        return {"repo": root.name, "path": str(root), "branch": branch,
                "changed": len([line for line in status.splitlines() if line.strip()]),
                "last_commit": _git(root, "log", "-1", "--format=%s")}
    except (subprocess.TimeoutExpired, OSError):
        return None  # a huge or broken repo: no cue rather than a slow park


def for_folders(folders):
    """Cues for every distinct repo among these folders (checked in parallel). Given up on
    after a few seconds: a folder on an offline network drive can hang the search for .git."""
    if not GIT:
        return []
    return limits.within(6, _for_folders, folders, default=[], what="git cues")


def _for_folders(folders):
    roots = list(dict.fromkeys(r for r in map(repo_root, folders) if r))
    with ThreadPoolExecutor(max_workers=4) as pool:
        return [c for c in pool.map(cue, roots) if c]


def folders_of(items):
    """The folders a park's items work in: VS Code folders and terminal folders."""
    out = []
    for item in items:
        if not item.get("keep", True):
            continue
        if item.get("kind") == "terminal":
            out.append(item["folder"])
        elif item.get("app") in ("code.exe", "code - insiders.exe", "cursor.exe", "windsurf.exe"):
            out += item.get("targets", [])
    return out


def compare(saved):
    """Saved cues next to now: adds 'now_branch' where you've switched branch since."""
    out = []
    there = limits.exist([c["path"] for c in saved])
    for c in saved:
        now = cue(Path(c["path"])) if GIT and there[c["path"]] else None
        out.append({**c, "now_branch": now["branch"] if now and now["branch"] != c["branch"] else ""})
    return out


def describe(c):
    """'fix-login · 3 changed · last: Add kernel header'"""
    parts = [c["branch"], f"{c['changed']} changed" if c["changed"] else "clean"]
    if c.get("last_commit"):
        parts.append(f"last: {c['last_commit'][:50]}")
    return " · ".join(parts)
