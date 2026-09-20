"""The article cap and the pre-enrichment URL dedup.

The cap previously bound silently: the count was printed after truncating, so
three runs in a row appeared to cluster into exactly 90 distinct stories. That
also starved Best of the Rest, which draws from whatever the display cap left.
"""

from unittest import mock

import pytest

from aggregator import config as C
from aggregator import enrich as E
from aggregator.scorer import score_and_sort


def _cluster_payload(n):
    """One article per cluster, so clustering yields exactly n stories."""
    return {"lead": "L",
            "articles": [{"id": i, "keep": True, "significance": 90 - (i % 90),
                          "sector": "Office", "summary": f"s{i}", "cluster": i}
                         for i in range(n)]}


def _articles(n):
    """Titles must be genuinely distinct.

    The fallback scorer clusters on Jaccard title overlap, and `_title_tokens`
    drops tokens shorter than three characters — so a bare index is invisible
    and "Story 1"/"Story 2" collapse into one cluster. Embedding the index
    inside words keeps each token set distinct.
    """
    out = []
    for i in range(n):
        title = (f"Acme{i}bridge Partners buys Tower{i}plaza "
                 f"in Metro{i}ville for ${i}00 million")
        out.append({"title": title, "link": f"https://example.com/story-{i}",
                    "summary": "", "source_short": "X", "source_name": "Bisnow",
                    "pub_date": "Sep 20", "position": 0, "full_text": "",
                    "access": "free"})
    return out


def test_cap_is_high_enough_not_to_bind_normally():
    """Runs cluster to roughly 90-120; the cap should sit clear of that."""
    assert C.MAX_TOTAL_ARTICLES >= 140


def test_distinct_count_is_reported_before_the_cap(capsys):
    """The log must show what clustering actually produced."""
    n = C.MAX_TOTAL_ARTICLES + 12
    with mock.patch.object(E, "_call_model", return_value=_cluster_payload(n)):
        _, ranked = E.enrich(_articles(n))
    out = capsys.readouterr().out
    assert f"{n} distinct stories" in out
    assert f"capped to {C.MAX_TOTAL_ARTICLES}" in out
    assert len(ranked) == C.MAX_TOTAL_ARTICLES


def test_no_cap_note_when_the_cap_does_not_bind(capsys):
    n = 20
    with mock.patch.object(E, "_call_model", return_value=_cluster_payload(n)):
        _, ranked = E.enrich(_articles(n))
    out = capsys.readouterr().out
    assert f"{n} distinct stories" in out
    assert "capped to" not in out
    assert len(ranked) == n


def test_fallback_scorer_reports_its_own_cap(capsys):
    ranked = score_and_sort(_articles(C.MAX_TOTAL_ARTICLES + 30))
    assert len(ranked) == C.MAX_TOTAL_ARTICLES
    assert "Deterministic ranking capped" in capsys.readouterr().out


# ── URL dedup ────────────────────────────────────────────────────────────────

def _dedupe(articles):
    """The rule as applied in main(), isolated for assertion."""
    seen, unique = set(), []
    for a in articles:
        key = a["link"].rstrip("/")
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def test_identical_urls_from_different_sources_collapse(article):
    """CRE Daily's main and multifamily feeds carry the same briefs."""
    arts = [article(link="https://credaily.com/briefs/rents-flat", source_short="CRE Daily"),
            article(link="https://credaily.com/briefs/rents-flat", source_short="CRE MF"),
            article(link="https://bisnow.com/other-story", source_short="Bisnow")]
    assert len(_dedupe(arts)) == 2


def test_trailing_slash_is_not_a_different_article(article):
    arts = [article(link="https://ex.com/story"), article(link="https://ex.com/story/")]
    assert len(_dedupe(arts)) == 1


def test_first_occurrence_wins(article):
    arts = [article(link="https://ex.com/s", source_short="First"),
            article(link="https://ex.com/s", source_short="Second")]
    assert _dedupe(arts)[0]["source_short"] == "First"


def test_same_headline_from_different_outlets_is_kept(article):
    """Deliberate: that's syndication, and merging it is the clustering step's
    job — it needs the model's judgement and the also_sources signal."""
    arts = [article(title="Blackstone buys $2B portfolio", link="https://a.com/1"),
            article(title="Blackstone buys $2B portfolio", link="https://b.com/1")]
    assert len(_dedupe(arts)) == 2
