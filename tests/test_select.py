"""Display selection: floor, story cap, sector cap, backfill, Best of the Rest.

The backfill is the reason this module was extracted. It exists to stop a
crowded sector both dropping a high scorer and leaving the digest short, and
that failure is invisible in production — the email just quietly comes up
short.
"""

import collections

from aggregator.scorer import group_by_sector
from aggregator.select import select_display


SECTORS = ["Capital Markets", "Office", "Multifamily", "Industrial", "Retail",
           "Hospitality", "Data Centers", "Macro & Policy"]


def sel(ranked, floor=50, min_stories=12, max_stories=20, max_per_sector=6, rest_max=20):
    return select_display(ranked, group_by_sector, floor=floor, min_stories=min_stories,
                          max_stories=max_stories, max_per_sector=max_per_sector,
                          rest_max=rest_max)


def spread(article, n, *, start=95, prefix="s"):
    """Stories across many sectors, so the per-sector cap isn't the binding
    constraint — tests that care about the cap build their own crowding."""
    return [article(link=f"{prefix}{i}", sector=SECTORS[i % len(SECTORS)],
                    significance=start - i) for i in range(n)]


def test_floor_hides_below_threshold(article):
    ranked = ([article(link=f"hi{i}", significance=80) for i in range(15)]
              + [article(link=f"lo{i}", significance=20) for i in range(10)])
    _, displayed, _, stats = sel(ranked)
    assert len(stats["below"]) == 10
    assert all(a["significance"] >= 50 for a in displayed)


def test_floor_falls_back_when_too_few_clear_it(article):
    """A quiet day must still produce a digest rather than a near-empty one."""
    ranked = (spread(article, 3, start=80, prefix="hi")
              + spread(article, 20, start=20, prefix="lo"))
    _, displayed, _, stats = sel(ranked, min_stories=12)
    assert stats["floor_fallback"] is True
    assert len(displayed) == 12
    assert stats["cleared_floor"] == 3


def test_story_cap_keeps_the_highest_scoring(article):
    ranked = spread(article, 40)
    _, displayed, _, stats = sel(ranked, max_stories=20)
    assert len(displayed) == 20
    assert len(stats["cut"]) == 20
    assert max(a["significance"] for a in stats["cut"]) < min(a["significance"] for a in displayed)


def test_sector_cap_is_never_exceeded(article):
    ranked = [article(link=f"cm{i}", sector="Capital Markets", significance=90 - i)
              for i in range(30)]
    _, displayed, _, _ = sel(ranked, max_per_sector=6)
    counts = collections.Counter(a["sector"] for a in displayed)
    assert all(v <= 6 for v in counts.values())


def test_backfill_reaches_target_on_a_crowded_sector_day(article):
    """Without backfill this day produces 14 of 20 — six lost to the cap."""
    ranked = [article(link=f"cm{i}", sector="Capital Markets", significance=95 - i)
              for i in range(12)]
    for sector, base in [("Office", 70), ("Multifamily", 60), ("Industrial", 55)]:
        ranked += [article(link=f"{sector}{i}", sector=sector, significance=base - i)
                   for i in range(6)]
    _, displayed, _, stats = sel(ranked, max_stories=20, max_per_sector=6)
    assert len(displayed) == 20
    assert stats["backfilled"] > 0
    assert all(v <= 6 for v in collections.Counter(a["sector"] for a in displayed).values())


def test_highest_significance_story_always_survives(article):
    ranked = [article(link=f"cm{i}", sector="Capital Markets", significance=95 - i)
              for i in range(30)]
    ranked += [article(link=f"of{i}", sector="Office", significance=50 - i) for i in range(10)]
    _, displayed, _, _ = sel(ranked)
    assert "cm0" in {a["link"] for a in displayed}


def test_rest_excludes_displayed_and_respects_its_cap(article):
    ranked = spread(article, 60)
    _, displayed, rest, _ = sel(ranked, max_stories=20, rest_max=20)
    shown = {a["link"] for a in displayed}
    assert len(rest) == 20
    assert not shown & {a["link"] for a in rest}


def test_rest_is_drawn_from_everything_above_the_floor(article):
    """Not from the truncated pool — the cap's leftovers are exactly the point."""
    ranked = spread(article, 45)
    _, displayed, rest, stats = sel(ranked, max_stories=20, rest_max=20)
    cut_links = {a["link"] for a in stats["cut"]}
    assert {a["link"] for a in rest} <= cut_links


def test_rest_is_ordered_by_significance(article):
    ranked = spread(article, 60)
    _, _, rest, _ = sel(ranked)
    sigs = [a["significance"] for a in rest]
    assert sigs == sorted(sigs, reverse=True)


def test_empty_input_is_safe(article):
    sections, displayed, rest, stats = sel([])
    assert sections == [] and displayed == [] and rest == []
    assert stats["rest_range"] is None


def test_no_floor_keeps_everything_eligible(article):
    """The deterministic fallback path runs with floor=0."""
    ranked = spread(article, 30, start=5)
    _, displayed, _, stats = sel(ranked, floor=0)
    assert stats["below"] == []
    assert len(displayed) == 20


def test_sector_cap_binds_when_everything_is_one_sector(article):
    """Not a bug: with one sector and a cap of 6, six is the correct answer —
    the backfill has nowhere to draw from."""
    ranked = [article(link=f"cm{i}", sector="Capital Markets", significance=90 - i)
              for i in range(30)]
    _, displayed, rest, _ = sel(ranked, max_stories=20, max_per_sector=6)
    assert len(displayed) == 6
    # The remainder isn't lost — it flows into Best of the Rest.
    assert len(rest) == 20
