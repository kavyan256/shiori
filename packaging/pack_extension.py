"""Zips the extension for the stores: dist/shiori-chrome.zip and dist/shiori-firefox.zip.

  python packaging/pack_extension.py

The Chrome Web Store (also used by Edge, Brave and Opera) and Firefox Add-ons each want a zip
with manifest.json at the top. Firefox's manifest differs, so it goes in under that name.
"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "extension"
DIST = ROOT / "dist"
SHARED = ["background.js", "icon128.png"]


def pack(name, manifest):
    DIST.mkdir(exist_ok=True)
    out = DIST / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as package:
        package.write(EXTENSION / manifest, "manifest.json")
        for file in SHARED:
            package.write(EXTENSION / file, file)
    return out


def main():
    chrome = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    firefox = json.loads((EXTENSION / "manifest.firefox.json").read_text(encoding="utf-8"))
    if chrome["version"] != firefox["version"]:
        raise SystemExit(f"Versions differ: Chrome {chrome['version']}, Firefox {firefox['version']}")
    for out in (pack("shiori-chrome.zip", "manifest.json"), pack("shiori-firefox.zip", "manifest.firefox.json")):
        print(out, out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
