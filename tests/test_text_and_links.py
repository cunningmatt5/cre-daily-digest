"""Text acquisition, Google News link resolution, and free-alternate selection.

All three reach the network in production, so every test here mocks that edge.
The failure paths matter more than the happy ones: resolution runs against an
undocumented Google endpoint, and the whole design promise is that it degrades
to today's behaviour rather than breaking the digest.
"""

from unittest import mock

import pytest

from aggregator import extract as X
from aggregator import publicize as P
from aggregator import resolve as R


# ── extract: which text tier wins ────────────────────────────────────────────

def test_rich_feed_text_is_preferred(article):
    text, origin = X.best_text(article(full_text="x" * 1200))
    assert origin == "feed" and len(text) == 1200


def test_body_is_fetched_when_the_feed_is_thin(article):
    with mock.patch.object(X, "fetch_body", return_value="y" * 900):
        _, origin = X.best_text(article(full_text="tiny", link="https://bisnow.com/a"))
    assert origin == "body"


def test_falls_back_to_thin_when_nothing_is_fetchable(article):
    a = article(full_text="", summary="a teaser blurb",
                link="https://news.google.com/rss/articles/XYZ")
    with mock.patch.object(X, "fetch_body", return_value=""):
        text, origin = X.best_text(a)
    assert origin == "thin" and text == "a teaser blurb"


def test_google_links_are_not_fetchable():
    assert X._is_direct("https://bisnow.com/story") is True
    assert X._is_direct("https://news.google.com/rss/articles/Q") is False


def test_gather_sets_keys_on_every_article(article):
    arts = [article(full_text="z" * 900, link="https://a.com/1"),
            article(full_text="", link="https://news.google.com/rss/articles/Q")]
    with mock.patch.object(X, "fetch_body", return_value=""):
        counts = X.gather(arts, max_workers=2)
    assert counts["feed"] == 1 and counts["thin"] == 1
    assert all("source_text" in a and "text_thin" in a for a in arts)
    assert arts[0]["text_thin"] is False and arts[1]["text_thin"] is True


# ── resolve: must fail safe on an undocumented endpoint ──────────────────────

def test_is_google_link():
    assert R.is_google_link("https://news.google.com/rss/articles/CBMi") is True
    assert R.is_google_link("https://bisnow.com/a") is False


def test_resolution_returns_none_on_network_error():
    session = mock.Mock()
    session.get.side_effect = RuntimeError("network down")
    assert R.resolve_one("https://news.google.com/rss/articles/X", session) is None


def test_resolution_returns_none_when_signature_is_missing():
    """The shape Google would serve if it changed the bounce page."""
    session = mock.Mock()
    session.get.return_value = mock.Mock(text="<html>no signature</html>")
    assert R.resolve_one("https://news.google.com/rss/articles/X", session) is None


def test_resolution_returns_none_when_rpc_yields_no_url():
    session = mock.Mock()
    session.get.return_value = mock.Mock(text='data-n-a-sg="s" data-n-a-ts="123"')
    session.post.return_value = mock.Mock(text="[[null]]")
    assert R.resolve_one("https://news.google.com/rss/articles/X", session) is None


def test_non_google_links_are_left_alone():
    assert R.resolve_one("https://bisnow.com/a") is None


def test_resolve_links_preserves_the_original_url(article):
    """google_link feeds the seen-URL ledger; losing it repeats the story."""
    arts = [article(link="https://news.google.com/rss/articles/AAA"),
            article(link="https://bisnow.com/keep-me")]
    with mock.patch.object(R, "resolve_one", return_value="https://real.com/story"):
        stats = R.resolve_links(arts, max_workers=2)
    assert stats == {"attempted": 1, "resolved": 1}
    assert arts[0]["link"] == "https://real.com/story"
    assert arts[0]["google_link"] == "https://news.google.com/rss/articles/AAA"
    assert "google_link" not in arts[1]


def test_total_resolution_failure_is_reported(article, capsys):
    """Zero-of-many is the signature of the endpoint changing; it must be loud."""
    arts = [article(link=f"https://news.google.com/rss/articles/{i}") for i in range(3)]
    with mock.patch.object(R, "resolve_one", return_value=None):
        stats = R.resolve_links(arts, max_workers=2)
    assert stats["resolved"] == 0
    assert "may have changed" in capsys.readouterr().err


# ── publicize: choosing a public alternate ───────────────────────────────────

def test_cluster_candidates_exclude_paywalled_and_farms(article):
    story = article(access="paywalled", cluster_members=[
        {"source_name": "WSJ", "link": "https://wsj.com/x", "access": "paywalled"},
        {"source_name": "Hoodline", "link": "https://hoodline.com/x", "access": "free"},
        {"source_name": "Bisnow", "link": "https://bisnow.com/x", "access": "free"},
    ])
    assert [c["source_name"] for c in P._from_cluster(story)] == ["Bisnow"]


def test_same_story_gate_separates_topic_from_event():
    same = P._same_story("Blackstone buys $2B logistics portfolio",
                         "Blackstone acquires $2B logistics portfolio")
    different = P._same_story("Blackstone buys $2B logistics portfolio",
                              "Blackstone names new chief financial officer")
    assert same >= P._MIN_TITLE_OVERLAP
    assert different < P._MIN_TITLE_OVERLAP


def test_candidate_ranking_prefers_fetchable_over_text_rich():
    """A public link the summarizer can also read beats one it can only link."""
    fetchable = {"source_name": "Bisnow", "link": "https://bisnow.com/a", "full_text": "y" * 900}
    bounce = {"source_name": "Commercial Observer",
              "link": "https://news.google.com/rss/articles/Q", "full_text": "x" * 5000}
    assert max([fetchable, bounce], key=P._rank_candidate) is fetchable


def test_apply_alternate_swaps_link_keeps_provenance_borrows_text(article):
    story = article(link="https://news.google.com/x", source_short="WSJ", source_name="WSJ",
                    access="paywalled", paywalled=True, full_text="tiny")
    story["public_alt"] = {"link": "https://bisnow.com/x", "source_name": "Bisnow",
                           "source_short": "Bisnow", "full_text": "B" * 1500}
    assert P.apply_alternate(story) is True
    assert story["link"] == "https://bisnow.com/x"
    assert story["original_source"] == "WSJ"
    assert story["access"] == "free" and story["paywalled"] is False
    assert len(story["full_text"]) == 1500


def test_apply_alternate_is_a_noop_without_a_candidate(article):
    story = article()
    assert P.apply_alternate(story) is False
    assert "original_source" not in story


def test_resolve_all_only_targets_gated_stories(article):
    stories = [article(access="free"), article(access="paywalled", link="https://p.com/1")]
    with mock.patch.object(P, "_resolve_one", return_value=None):
        stats = P.resolve_all(stories, max_workers=2)
    assert stats["gated"] == 1
