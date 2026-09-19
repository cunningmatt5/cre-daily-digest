"""Publisher access classification.

Google News reports the same outlet under several names, and the keys are
substring matches — so the collision cases matter as much as the hits.
"""

import pytest

from aggregator.publishers import (classify, is_content_farm, is_linkable_free,
                                   normalize)


@pytest.mark.parametrize("name", [
    "WSJ", "Wall Street Journal", "wsj.com",
    "bloomberg.com", "Bloomberg Real Estate", "news.bloombergtax.com",
    "CoStar", "Green Street News", "The Real Deal", "Crain's New York",
])
def test_paywalled_publishers(name):
    assert classify(name) == "paywalled"


@pytest.mark.parametrize("name", [
    "Commercial Observer", "Bisnow", "Connect CRE", "CRE Daily", "Globest",
    "New York Post", "CBS News", "Data Center Dynamics", "Trepp",
    "Long Island Business News", "Scotsman Guide",
    # added with the source expansion
    "Propmodo", "Yield PRO", "Senior Housing News", "Construction Dive",
    "Retail Dive", "Hotel Business",
])
def test_free_publishers(name):
    assert classify(name) == "free"


@pytest.mark.parametrize("name", ["Hoodline", "Slow Boring", "Briefs Finance",
                                  "Some Random Blog", "", None])
def test_unknown_and_farms_are_not_linkable(name):
    assert classify(name) == "unknown"
    assert is_linkable_free(name) is False


def test_content_farms_are_identified():
    assert is_content_farm("Hoodline") is True
    assert is_content_farm("Investing.com") is True
    assert is_content_farm("CBS News") is False


def test_farms_classify_unknown_not_paywalled():
    """Farms must be excluded from alternate selection without being labelled
    paywalled — mislabelling them would put a lock chip on a free page."""
    assert classify("Hoodline") == "unknown"


@pytest.mark.parametrize("name,expected", [
    # A bare "journal" or "post" key would swallow these.
    ("Insurance Journal", "free"),
    ("The Daily Reporter", "free"),
])
def test_substring_keys_do_not_collide(name, expected):
    assert classify(name) == expected


def test_normalize_keeps_domain_dots():
    """Domain-style names must still match their keys."""
    assert "bloomberg.com" in normalize("Bloomberg.com")
    assert normalize("  Crain's   New York  ") == "crain s new york"


def test_is_linkable_free_is_stricter_than_not_paywalled():
    """An unknown outlet may well be free, but we can't vouch for it."""
    assert is_linkable_free("Some Unknown Local Paper") is False
    assert is_linkable_free("Commercial Observer") is True
