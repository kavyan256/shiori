"""The browser extension's two manifests, the store packages, and Firefox on the Python side."""
import json
import sys
import zipfile
from pathlib import Path

import browser
import docs

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))
import pack_extension  # noqa: E402


def manifest(name):
    return json.loads((ROOT / "extension" / name).read_text(encoding="utf-8"))


def test_both_manifests_are_the_same_version_with_the_same_permissions():
    chrome, firefox = manifest("manifest.json"), manifest("manifest.firefox.json")
    assert chrome["version"] == firefox["version"]
    assert chrome["permissions"] == firefox["permissions"]
    assert chrome["host_permissions"] == firefox["host_permissions"]


def test_the_extension_only_talks_to_this_pc_and_youtube():
    assert manifest("manifest.json")["host_permissions"] == ["http://127.0.0.1:47321/*", "https://www.youtube.com/*"]


def test_firefox_uses_a_background_script_and_chrome_a_service_worker():
    assert manifest("manifest.firefox.json")["background"] == {"scripts": ["background.js"]}
    assert manifest("manifest.json")["background"] == {"service_worker": "background.js"}


def test_each_package_has_its_manifest_at_the_top(tmp_path, monkeypatch):
    monkeypatch.setattr(pack_extension, "DIST", tmp_path)
    for name, source, wanted in (("c.zip", "manifest.json", "service_worker"), ("f.zip", "manifest.firefox.json", "gecko")):
        with zipfile.ZipFile(pack_extension.pack(name, source)) as package:
            assert sorted(package.namelist()) == ["background.js", "icon128.png", "manifest.json"]
            assert wanted in package.read("manifest.json").decode("utf-8")


def test_a_firefox_report_is_kept_as_firefox():
    browser._save_report({"browser": "firefox", "windows": [{"id": 1, "tabs": [{"title": "x", "url": "https://x.org"}]}]})
    assert "firefox" in browser.fresh_tabs({"firefox.exe"})
    browser._tabs.pop("firefox")


def test_firefox_is_a_browser_everywhere_it_needs_to_be():
    assert browser.BROWSER_OF_APP["firefox.exe"] == "firefox"
    assert "firefox.exe" in docs.BROWSERS
