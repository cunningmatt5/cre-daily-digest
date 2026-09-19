"""Inbound filters and the seen-URL ledger.

The ledger is the highest-consequence pure logic in the project: get it wrong
and either stories repeat every morning, or they are buried before anyone sees
them (which is exactly what happened before PR #11).
"""

import json
from datetime import date, datetime, timedelta

import pytest

from aggregator import main as M


# ── inbound filters ──────────────────────────────────────────────────────────

def test_social_links_are_dropped(article):
    assert M._is_social(article(link="https://www.linkedin.com/posts/xyz")) is True
    assert M._is_social(article(link="https://bisnow.com/a-real-story")) is False


@pytest.mark.parametrize("url,reason_fragment", [
    ("https://example.com/", "bare domain"),
    ("https://example.com/news", "category path"),
    ("https://example.com/insights/", "category"),
    ("https://example.com/author/jane-doe", "profile/author"),
    ("https://example.com/story#section", "fragment anchor"),
    ("https://example.com/blog", "category"),
])
def test_non_article_urls_are_rejected(article, url, reason_fragment):
    reason = M._non_article_reason(article(link=url))
    assert reason and reason_fragment in reason


def test_real_article_urls_pass(article):
    for url in ["https://lodgingmagazine.com/choice-hotels-q1-results-beat-estimates",
                "https://globest.com/2026/09/18/eqt-real-estate-makes-12b-buy-of-logistics/"]:
        assert M._non_article_reason(article(link=url)) == ""


def test_short_titles_are_rejected(article):
    assert M._non_article_reason(article(title="Too short",
                                         link="https://ex.com/a-long-enough-slug-here-ok"))


def test_age_filter_uses_max_age_days(article):
    fresh = datetime.utcnow() - timedelta(hours=6)
    stale = datetime.utcnow() - timedelta(days=M.MAX_AGE_DAYS + 1)
    assert M._is_too_old(article(pub_datetime=fresh)) is False
    assert M._is_too_old(article(pub_datetime=stale)) is True
    # No date is handled by its own filter, not this one.
    assert M._is_too_old(article(pub_datetime=None)) is False


def test_no_date_filter(article):
    assert M._has_no_date(article(pub_datetime=None)) is True
    assert M._has_no_date(article(pub_datetime=datetime.utcnow())) is False


# ── domain-based access refinement ───────────────────────────────────────────

def test_domain_settles_unknown_access(article):
    a = article(access="unknown", link="https://www.wsj.com/articles/x")
    assert M._refine_access_from_domain(a) is True
    assert a["access"] == "paywalled" and a["paywalled"] is True


def test_domain_never_overrides_a_confident_name_match(article):
    a = article(access="free", link="https://www.wsj.com/articles/x")
    assert M._refine_access_from_domain(a) is False
    assert a["access"] == "free"


def test_domain_refinement_leaves_unrecognised_domains_alone(article):
    a = article(access="unknown", link="https://obscure-blog.example/x")
    assert M._refine_access_from_domain(a) is False
    assert a["access"] == "unknown"


# ── seen-URL ledger ──────────────────────────────────────────────────────────

@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "seen_urls.json"
    monkeypatch.setattr(M, "SEEN_FILE", path)
    return path


def test_save_then_load_round_trip(ledger):
    M.save_seen_urls(["https://a.com/1", "https://b.com/2"])
    data = json.loads(ledger.read_text())
    assert date.today().isoformat() in data
    # Today's entries are deliberately NOT blocked, so same-day reruns work.
    assert M.load_seen_urls() == set()


def test_previous_days_are_blocked(ledger):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    ledger.write_text(json.dumps({yesterday: ["https://a.com/1"]}))
    assert "https://a.com/1" in M.load_seen_urls()


def test_entries_older_than_keep_days_are_pruned(ledger):
    old = (date.today() - timedelta(days=M.KEEP_DAYS + 5)).isoformat()
    recent = (date.today() - timedelta(days=1)).isoformat()
    ledger.write_text(json.dumps({old: ["https://old.com/1"], recent: ["https://new.com/1"]}))
    M.save_seen_urls(["https://today.com/1"])
    data = json.loads(ledger.read_text())
    assert old not in data and recent in data


def test_malformed_date_key_does_not_crash_save(ledger):
    """A bad key must not take down a run whose email has already been sent."""
    ledger.write_text(json.dumps({"not-a-date": ["https://x.com/1"],
                                  (date.today() - timedelta(days=1)).isoformat(): ["https://y.com/1"]}))
    M.save_seen_urls(["https://today.com/1"])
    data = json.loads(ledger.read_text())
    assert date.today().isoformat() in data
    assert "not-a-date" not in data


def test_corrupt_file_degrades_to_empty(ledger):
    ledger.write_text("{ this is not json")
    assert M.load_seen_urls() == set()
    M.save_seen_urls(["https://a.com/1"])
    assert date.today().isoformat() in json.loads(ledger.read_text())


def test_swapped_story_retires_every_url(ledger):
    """A story can carry three URLs by the time it ships: the original Google
    bounce link, the alternate's bounce link, and the final publisher URL.
    Missing any one resurfaces it as fresh news tomorrow."""
    story = {
        "link": "https://cbsnews.com/free-version",
        "google_link": "https://news.google.com/rss/articles/ALT",
        "cluster_links": ["https://news.google.com/rss/articles/ORIG"],
    }
    links = {story["link"].rstrip("/")}
    links.update(l.rstrip("/") for l in story["cluster_links"])
    links.add(story["google_link"].rstrip("/"))
    M.save_seen_urls(sorted(links))
    saved = set(sum(json.loads(ledger.read_text()).values(), []))
    assert saved == {"https://cbsnews.com/free-version",
                     "https://news.google.com/rss/articles/ALT",
                     "https://news.google.com/rss/articles/ORIG"}
