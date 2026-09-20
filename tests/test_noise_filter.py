"""The noise pre-filter and content-farm alternate routing.

The pre-filter is deliberately narrow. The risk it carries is over-reach —
dropping real CRE — so the "must survive" cases below matter more than the
"must be dropped" ones.
"""

import pytest

from aggregator import main as M
from aggregator import publicize as P


@pytest.mark.parametrize("title,label", [
    ("Watch JPMorgan Global Real Estate Head on Hot Markets", "video/audio stub"),
    ("Watch Markets, Treasury Yields & the Bank of Japan", "video/audio stub"),
    ("Listen: the week in commercial property", "video/audio stub"),
    ("Podcast: inside the office conversion boom", "podcast stub"),
    ("Gail Liniger, Pioneering Real-Estate Executive, Dies at 81", "obituary"),
    ("House of the Week: A Curved Texas Home With A Fan-Shaped Roof", "lifestyle column"),
    ("Nominate a Leading Attorney for Connect CRE's 2026 Awards", "awards promo"),
    ("Private Equity Real Estate | Database", "database landing page"),
    ("Folio Announces Partnership With M3", "vendor PR"),
    ("Hapi Expands Its Partnership With Upgrade", "vendor PR"),
])
def test_noise_is_dropped(article, title, label):
    assert M._noise_reason(article(title=title)) == label


@pytest.mark.parametrize("title", [
    # Real CRE that must not be caught by any pattern above.
    "EQT Real Estate Makes $1.2B Buy of Logistics Portfolio in Southern California",
    "PSP, Ares Join Forces on $2.4B Logistics Investment",
    "Deutsche Bank's DWS to Shut US Property Fund Hit by Redemptions",
    "Blackstone Partnership With Brookfield Acquires Dallas Industrial Park",
    "Watchtower REIT Reports Third-Quarter Earnings",
    "Loudoun County board votes to pause new data center applications",
    "State Farm's 1.1M SF Suburban Atlanta Hub Put Up For Sale",
    "Trepp: industrial CMBS issuance gains share as SASB deals lead",
    "Simon Property Group Raised Its Outlook Again",
    "JLL Arranges $154.1 Million Financing for Six-Property Retail Portfolio",
])
def test_real_cre_survives_the_noise_filter(article, title):
    assert M._noise_reason(article(title=title)) == ""
    assert M._is_noise(article(title=title)) is False


def test_partnership_pattern_needs_the_announcement_verb():
    """'Partnership' alone is common in real deals — 'Joint Venture
    Partnership Acquires...' must survive; only the PR phrasing is noise."""
    assert M._noise_reason({"title": "Partnership Acquires 400,000 SF Industrial Asset"}) == ""
    assert M._noise_reason({"title": "Yardi Announces Partnership With RealPage"}) == "vendor PR"


def test_watch_must_be_at_the_start():
    """Otherwise 'Watchtower' and 'investors watch rates' get caught."""
    assert M._noise_reason({"title": "Investors watch rates ahead of the Fed meeting"}) == ""
    assert M._noise_reason({"title": "Watch: the Fed decision explained"}) == "video/audio stub"


# ── content-farm routing ─────────────────────────────────────────────────────

def test_farm_bylines_want_an_alternate(article):
    assert P.needs_alternate(article(source_name="TradingView", access="unknown")) is True
    assert P.needs_alternate(article(source_name="Yahoo Finance", access="unknown")) is True


def test_paywalled_still_wants_an_alternate(article):
    assert P.needs_alternate(article(source_name="WSJ", access="paywalled")) is True


def test_credible_free_sources_are_left_alone(article):
    assert P.needs_alternate(article(source_name="Bisnow", access="free")) is False


def test_farm_is_not_credited_as_originator(article):
    """'originally TradingView' would credit a rewrite site for someone
    else's reporting."""
    story = article(source_name="TradingView", source_short="TradingView", access="unknown")
    story["public_alt"] = {"link": "https://bisnow.com/x", "source_name": "Bisnow",
                           "source_short": "Bisnow", "full_text": ""}
    P.apply_alternate(story)
    assert "original_source" not in story
    assert story["source_short"] == "Bisnow"


def test_real_outlet_is_still_credited(article):
    story = article(source_name="WSJ", source_short="WSJ", access="paywalled")
    story["public_alt"] = {"link": "https://cbsnews.com/x", "source_name": "CBS News",
                           "source_short": "CBS News", "full_text": ""}
    P.apply_alternate(story)
    assert story["original_source"] == "WSJ"


def test_farm_keeps_its_byline_when_no_alternate_exists(article):
    """Losing coverage is worse than an imperfect byline."""
    story = article(source_name="TradingView", source_short="TradingView", access="unknown")
    assert P.apply_alternate(story) is False
    assert story["source_short"] == "TradingView"
