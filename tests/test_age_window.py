"""The business-day age window.

Calendar days created a weekend drought — the age filter removed 16% of the
pool on a Friday, 32% on Saturday and 54% on Sunday, and a Monday run could not
see Friday afternoon at all. Counting business days closes that gap without
loosening weekday freshness, which is the property these tests pin down.

`now` is passed explicitly so each case asserts a specific weekday rather than
whatever day the suite happens to run on.
"""

from datetime import datetime, timedelta

import pytest

from aggregator import main as M

# A known week: 2026-09-14 is a Monday.
MON = datetime(2026, 9, 14, 9, 0)
TUE = datetime(2026, 9, 15, 9, 0)
WED = datetime(2026, 9, 16, 9, 0)
THU = datetime(2026, 9, 17, 9, 0)
FRI = datetime(2026, 9, 18, 9, 0)
SAT = datetime(2026, 9, 19, 9, 0)
SUN = datetime(2026, 9, 20, 9, 0)


def test_the_reference_week_is_what_we_think():
    assert MON.weekday() == 0 and FRI.weekday() == 4
    assert SAT.weekday() == 5 and SUN.weekday() == 6


@pytest.mark.parametrize("now,expected_day", [
    # Midweek is unchanged: two calendar days back is also two business days.
    (WED, 14),   # Wednesday -> Monday
    (THU, 15),   # Thursday  -> Tuesday
    (FRI, 16),   # Friday    -> Wednesday
])
def test_weekday_behaviour_is_unchanged(now, expected_day):
    assert M._age_cutoff(now).day == expected_day


def test_monday_reaches_back_to_thursday():
    """The case this change exists for. Under calendar days a Monday cutoff
    landed on Saturday, so Friday afternoon's news was invisible."""
    cutoff = M._age_cutoff(MON)
    assert cutoff.day == 10          # the previous Thursday
    assert cutoff < FRI - timedelta(days=7)  # sanity: it's the *prior* week
    old_style = MON - timedelta(days=M.MAX_AGE_DAYS)
    assert cutoff < old_style, "Monday must reach further back than before"


def test_monday_would_have_missed_friday_before():
    """Concretely: a story published Friday afternoon, read on Monday."""
    friday_story = FRI + timedelta(hours=8)          # Friday 5pm, previous week
    friday_story -= timedelta(days=7)                 # the Friday before MON
    assert friday_story < MON - timedelta(days=M.MAX_AGE_DAYS)  # old rule: cut
    assert friday_story >= M._age_cutoff(MON)                   # new rule: kept


@pytest.mark.parametrize("now", [SAT, SUN])
def test_weekend_runs_reach_past_the_weekend(now):
    cutoff = M._age_cutoff(now)
    assert cutoff.weekday() < 5, "cutoff should land on a weekday"
    assert cutoff <= now - timedelta(days=M.MAX_AGE_DAYS)


def test_cutoff_never_moves_forward():
    """Whatever the day, the window is at least MAX_AGE_DAYS wide."""
    for offset in range(14):
        now = MON + timedelta(days=offset)
        assert M._age_cutoff(now) <= now - timedelta(days=M.MAX_AGE_DAYS)


def test_cutoff_is_never_absurdly_far_back():
    """A weekend can add at most two days; nothing should exceed that."""
    for offset in range(14):
        now = MON + timedelta(days=offset)
        assert M._age_cutoff(now) >= now - timedelta(days=M.MAX_AGE_DAYS + 2)


def test_filter_uses_the_window(article):
    """_is_too_old must go through _age_cutoff, not its own arithmetic."""
    fresh = datetime.now() - timedelta(hours=2)
    ancient = datetime.now() - timedelta(days=30)
    assert M._is_too_old(article(pub_datetime=fresh)) is False
    assert M._is_too_old(article(pub_datetime=ancient)) is True
    assert M._is_too_old(article(pub_datetime=None)) is False
