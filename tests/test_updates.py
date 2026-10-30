"""Telling you about a newer version: once, and never from a network problem."""
import settings
import updates


def test_compares_versions_as_numbers():
    assert updates.is_newer("v1.10.0", "1.9.0")
    assert updates.is_newer("1.2.0", "1.1.9")
    assert not updates.is_newer("v1.1.0", "1.1.0")
    assert not updates.is_newer("v1.0.0", "1.1.0")


def test_a_strange_version_is_never_newer():
    assert not updates.is_newer("nightly", "1.1.0")
    assert not updates.is_newer("", "1.1.0")


def test_a_new_version_is_announced_once():
    assert updates.check(lambda: "v99.0.0") == "v99.0.0"
    assert updates.check(lambda: "v99.0.0") == ""
    assert updates.available() == "v99.0.0"


def test_a_later_version_is_announced_again():
    updates.check(lambda: "v99.0.0")
    assert updates.check(lambda: "v99.1.0") == "v99.1.0"


def test_being_up_to_date_announces_nothing():
    assert updates.check(lambda: "v0.1.0") == ""
    assert updates.available() == ""


def test_no_internet_keeps_what_was_known():
    updates.check(lambda: "v99.0.0")
    assert updates.check(lambda: "") == ""
    assert updates.available() == "v99.0.0"


def test_no_internet_is_quiet(monkeypatch):
    def offline(*args, **kwargs):
        raise OSError("no network")
    monkeypatch.setattr(updates.urllib.request, "urlopen", offline)
    assert updates.fetch() == ""


def test_the_setting_exists_and_can_be_turned_off():
    assert settings.get("check_updates") is True
    settings.change("check_updates", False)
    assert settings.get("check_updates") is False


def test_home_mentions_a_new_version(shiori):
    updates.check(lambda: "v99.0.0")
    assert "99.0.0" in shiori.say("show my desks")["message"]
