"""Shared fixtures.

Everything here is offline. No test may touch the network, call the Anthropic
API, or send mail — the suite has to be safe to run on every pull request.
"""

import pytest


@pytest.fixture
def article():
    """Factory for an article dict shaped like the pipeline produces."""
    def make(**overrides):
        base = {
            "title": "Blackstone Acquires $2B Logistics Portfolio",
            "link": "https://example.com/story-about-a-logistics-portfolio",
            "summary": "A short teaser blurb.",
            "full_text": "",
            "pub_date": "Sep 19, 2026",
            "pub_datetime": None,
            "source_name": "Commercial Observer",
            "source_short": "Comm Obs",
            "source_color": "#000000",
            "tier_weight": 20,
            "access": "free",
            "paywalled": False,
            "position": 0,
            "significance": 70,
            "sector": "Capital Markets",
            "also_sources": [],
            "cluster_links": [],
            "cluster_members": [],
        }
        base.update(overrides)
        return base
    return make


@pytest.fixture
def ranked(article):
    """A ranked list spanning several sectors and a wide score range."""
    sectors = ["Capital Markets", "Office", "Multifamily", "Industrial", "Retail"]
    out = []
    for i in range(40):
        out.append(article(
            link=f"https://example.com/story-number-{i}",
            title=f"Story number {i} about a commercial property deal",
            sector=sectors[i % len(sectors)],
            significance=95 - i,
        ))
    return out
