"""Saving desks on disk: finding them by a spoken name, versions, damaged files, and
the clean-up that keeps the data folder from growing forever."""
import json
import os
import time

import store


def save(name, shot=""):
    return store.park(name, [{"kind": "window", "app": "code.exe", "title": name, "keep": True}], note="n",
                      shot=shot)


def test_find_by_spoken_name():
    for name in ("College DBMS", "test parking 1", "hackathon"):
        save(name)
    assert store.find("college dbms") == "College DBMS"
    assert store.find("the college one") == "College DBMS"
    assert store.find("parking one") == "test parking 1"
    assert store.find("hackaton") == "hackathon"
    assert store.find("nothing like it") is None


def test_versions_are_capped():
    for _ in range(store.KEEP_VERSIONS + 5):
        save("dsa")
    assert len(store.load("dsa")["snapshots"]) == store.KEEP_VERSIONS


def test_a_damaged_file_is_set_aside_not_fatal():
    save("good")
    store.DATA_DIR.joinpath("bad.json").write_text("{not json", encoding="utf-8")
    assert [s["name"] for s in store.list_stages()] == ["good"]
    assert store.DATA_DIR.joinpath("bad.broken").exists()


def test_delete_goes_to_trash_and_can_come_back():
    save("dsa")
    trashed = store.delete("dsa")
    assert store.load("dsa") is None and trashed.exists()
    assert store.undelete(trashed, "dsa") and store.load("dsa")


def test_ticking_steps():
    store.park("dsa", [], note="n", steps=["a", "b"])
    assert store.set_step("dsa", 1, True) == [1]
    assert store.set_step("dsa", 1, False) == []
    assert store.set_step("dsa", 7, True) == []  # no step 8: ignored


def age(path, days):
    then = time.time() - days * 86400
    os.utime(path, (then, then))


def test_tidy_empties_old_trash_and_unused_pictures():
    store.SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("used.jpg", "in-trash.jpg", "unused-old.jpg", "unused-new.jpg"):
        store.SHOTS_DIR.joinpath(name).write_bytes(b"jpg")
    save("dsa", shot="used.jpg")
    save("old", shot="in-trash.jpg")
    recent_trash = store.delete("old")
    save("ancient")
    old_trash = store.delete("ancient")
    age(old_trash, store.TRASH_DAYS + 1)
    for name in ("used.jpg", "in-trash.jpg", "unused-old.jpg"):
        age(store.SHOTS_DIR / name, 2)

    assert store.tidy() == (1, 1)
    assert not old_trash.exists() and recent_trash.exists()
    left = sorted(p.name for p in store.SHOTS_DIR.iterdir())
    # used by a desk, used by a desk in the trash (it can be put back), too new to judge
    assert left == ["in-trash.jpg", "unused-new.jpg", "used.jpg"]


def test_tidy_removes_nothing_if_a_desk_cannot_be_read():
    store.SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    picture = store.SHOTS_DIR / "maybe-used.jpg"
    picture.write_bytes(b"jpg")
    age(picture, 2)
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    store.DATA_DIR.joinpath("half-written.json").write_text("{", encoding="utf-8")
    store.tidy()
    assert picture.exists()


def test_delete_pictures():
    store.SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    for n in range(3):
        store.SHOTS_DIR.joinpath(f"{n}.jpg").write_bytes(b"jpg")
    save("dsa", shot="0.jpg")
    assert store.delete_pictures() == 3
    assert json.loads(store.path_of("dsa").read_text(encoding="utf-8"))["name"] == "dsa"  # the desk stays
