"""Suggesting the desk you usually work on now."""
from datetime import datetime, timedelta

import habits

NOW = datetime(2026, 11, 10, 18, 0)


def desk(name, *times):
    return {"name": name, "snapshots": [{"parked_at": t.isoformat()} for t in times]}


def days_ago(*days, hour=18):
    return [(NOW - timedelta(days=d)).replace(hour=hour) for d in days]


def test_three_days_at_this_hour_is_a_habit():
    assert habits.usual_desk([desk("dsa", *days_ago(1, 2, 3))], NOW) == "dsa"


def test_two_days_is_not():
    assert habits.usual_desk([desk("dsa", *days_ago(1, 2))], NOW) is None


def test_other_hours_and_saves_today_do_not_count():
    assert habits.usual_desk([desk("dsa", *days_ago(1, 2, 3, hour=9))], NOW) is None
    assert habits.usual_desk([desk("dsa", *days_ago(0, 1, 2))], NOW) is None


def test_the_most_days_wins():
    assert habits.usual_desk([desk("a", *days_ago(1, 2, 3)), desk("b", *days_ago(1, 2, 3, 4))], NOW) == "b"
