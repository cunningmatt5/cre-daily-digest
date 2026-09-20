"""Collisions that only become visible after link resolution.

URL dedup runs before resolution, so it compares Google News bounce URLs. When
one of those resolves onto an article we also pull from a direct feed, both
copies survive. Measured at roughly one in forty resolutions on a live pool —
a wire item landing on yieldpro.com while Yield PRO is already a source.
"""

from aggregator import main as M


def _sections(*groups):
    return [(name, list(items)) for name, items in groups]


def test_rest_entry_colliding_with_a_summarized_story_is_dropped(article):
    """The reader would otherwise see the same story twice."""
    shown = article(link="https://yieldpro.com/2026/09/lyra-palmetto-bay",
                    title="IPA Arranges $40M for Lyra Palmetto Bay", sector="Multifamily")
    other = article(link="https://bisnow.com/other", title="Something else")
    # Same article, arrived via a wire query and only revealed by resolution.
    dupe = article(link="https://yieldpro.com/2026/09/lyra-palmetto-bay/",
                   title="IPA Arranges $40M for Lyra Palmetto Bay", sector="Multifamily")
    sections = _sections(("Multifamily", [shown]), ("Other", [other]))

    sections, displayed, rest, dropped = M._drop_link_collisions(
        sections, [shown, other], [dupe])

    assert dropped == 1
    assert rest == []
    assert len(displayed) == 2


def test_the_summarized_copy_is_the_one_kept(article):
    """It carries the long-form summary and a sector placement; the rest entry
    is only a headline."""
    shown = article(link="https://ex.com/story", summary="A full four-sentence summary.")
    dupe = article(link="https://ex.com/story", summary="")
    _, displayed, rest, _ = M._drop_link_collisions(
        _sections(("Office", [shown])), [shown], [dupe])
    assert displayed[0]["summary"].startswith("A full")
    assert rest == []


def test_duplicates_within_the_summarized_set_are_dropped(article):
    """Two wire items can resolve onto each other, not just onto the rest list."""
    a1 = article(link="https://ex.com/same", sector="Office")
    a2 = article(link="https://ex.com/same", sector="Office")
    sections, displayed, _, dropped = M._drop_link_collisions(
        _sections(("Office", [a1, a2])), [a1, a2], [])
    assert dropped == 1
    assert len(displayed) == 1
    assert sum(len(items) for _, items in sections) == 1


def test_sections_are_rebuilt_so_the_email_matches(article):
    """A dropped story must leave the rendered sections too, or the email shows
    what `displayed` says it removed."""
    a1 = article(link="https://ex.com/same", sector="Office")
    a2 = article(link="https://ex.com/same", sector="Office")
    keep = article(link="https://ex.com/keep", sector="Retail")
    sections, displayed, _, _ = M._drop_link_collisions(
        _sections(("Office", [a1, a2]), ("Retail", [keep])), [a1, a2, keep], [])
    rendered = [a for _, items in sections for a in items]
    assert len(rendered) == len(displayed) == 2


def test_emptied_sections_are_removed(article):
    """A sector whose only story was a duplicate shouldn't render as a heading
    with nothing under it."""
    a1 = article(link="https://ex.com/same", sector="Office")
    dup = article(link="https://ex.com/same", sector="Retail")
    sections, displayed, _, dropped = M._drop_link_collisions(
        _sections(("Office", [a1]), ("Retail", [dup])), [a1, dup], [])
    assert dropped == 1
    assert [name for name, _ in sections] == ["Office"]


def test_trailing_slash_is_the_same_article(article):
    a = article(link="https://ex.com/s")
    b = article(link="https://ex.com/s/")
    _, displayed, _, dropped = M._drop_link_collisions(
        _sections(("Office", [a])), [a], [b])
    assert dropped == 1


def test_no_collisions_leaves_everything_untouched(article):
    d = [article(link=f"https://ex.com/{i}") for i in range(3)]
    r = [article(link=f"https://ex.com/r{i}") for i in range(2)]
    sections = _sections(("Office", d))
    out_sections, displayed, rest, dropped = M._drop_link_collisions(sections, d, r)
    assert dropped == 0
    assert displayed == d and rest == r
    assert out_sections is sections, "unchanged input should not be rebuilt"
