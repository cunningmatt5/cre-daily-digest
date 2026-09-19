"""Publisher-level access classification.

Why publisher name and not URL: 55% of the candidate pool arrives as Google News
links, which are opaque protobuf bounce pages — they don't redirect, the blob
isn't base64-decodable, and the destination doesn't appear in the served HTML.
So the domain is simply unavailable. What we always do have is the publisher
name, from the Google News ``<source>`` element or the source config.

This replaces the old per-source ``paywalled`` flag, which was wrong for every
wire item: the Google News path overwrites ``source_name`` but never touched
``paywalled``, so a WSJ story arriving via the "CRE Headlines" query was marked
freely readable.

Names arrive in many shapes for the same outlet — ``WSJ``, ``Wall Street
Journal``, ``wsj.com`` — so matching is substring-based over a normalized form.
Keys must stay specific enough not to collide: "journal" alone would swallow
Insurance Journal, so the WSJ keys are spelled out in full.
"""

import re

# Outlets that gate articles behind a subscription or a login wall.
PAYWALLED = {
    "wall street journal", "wsj",
    "bloomberg",            # also catches bloomberg.com, Bloomberg Tax
    "costar",
    "green street",         # Green Street News
    "perenews", "pere news",
    "the real deal", "therealdeal",
    "financial times", "ft.com",
    "crain",                # Crain's New York / Chicago / Detroit
    "barron",
    "new york times", "nytimes",
    "washington post",
    "business insider",
    "the information",
    "seeking alpha",
    "the economist",
    "forbes",               # metered, frequently blocks
}

# Outlets we are happy to link to: freely readable and genuinely reported.
# Built from publishers actually observed in this pipeline's output.
FREE_ALLOWLIST = {
    # CRE trade press
    "commercial observer", "bisnow", "connect cre", "connectcre", "connectmoney",
    "cre daily", "credaily", "globest", "globe st", "commercialsearch",
    "lodging magazine", "lodging", "shopping center business",
    "data center dynamics", "datacenterdynamics", "trepp",
    "nareit", "reit.com", "multi-housing news", "multifamily dive",
    "commercial property executive", "rebusinessonline", "the registry",
    "bizjournals", "business journal",   # local Business Journals
    # Added with the 2026-09-19 source expansion; all verified free, dated
    # and directly fetchable before being added as feeds.
    "propmodo", "yield pro", "yieldpro", "hotel business",
    "senior housing news", "inside self-storage", "insideselfstorage",
    "construction dive", "retail dive", "multifamily dive", "hotel dive",
    "supply chain dive", "facilitiesnet", "rebusiness",
    # Mortgage / finance trade
    "scotsman guide", "themortgagepoint", "mortgage point", "housingwire",
    "national mortgage news",
    # General news with free CRE coverage
    "cbs news", "abc news", "nbc news", "npr",
    "new york post", "nypost",
    "reuters", "associated press", "ap news",
    "cnbc", "marketwatch", "axios", "politico",
    "realtor.com", "insurance journal",
    "the daily reporter", "long island business news", "vermontbiz",
    "chattanooga times", "west side rag", "the edge singapore",
    "moneycontrol",
}

# Low-quality aggregators and AI content farms. These frequently surface as
# "free alternates" for a paywalled story but are rewrites, not reporting —
# "Hoodline" showed up repeatedly in testing. Never link to these.
CONTENT_FARMS = {
    "hoodline", "canvasrebel", "investing.com", "simply wall st",
    "msn.com", "msn ", "yahoo", "newsbreak", "patch.com",
    "zerohedge", "benzinga", "tipranks", "insider monkey",
    "briefs finance", "slow boring",
}

_PUNCT = re.compile(r"[^\w\s.]+")
_WS = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Lowercase and strip punctuation so name variants compare equal.

    Keeps ``.`` so domain-style names (``bloomberg.com``, ``realtor.com``)
    still match their keys.
    """
    n = _PUNCT.sub(" ", (name or "").lower())
    return _WS.sub(" ", n).strip()


def _matches(name: str, keys) -> bool:
    return any(k in name for k in keys)


def is_content_farm(publisher: str) -> bool:
    """True for aggregators/rewrite sites we refuse to link to."""
    return _matches(normalize(publisher), CONTENT_FARMS)


def classify(publisher: str) -> str:
    """Return ``"paywalled"``, ``"free"``, or ``"unknown"`` for a publisher.

    ``"unknown"`` is a real answer, not a failure: the broad discovery queries
    surface outlets we've never seen. Callers decide how to treat it — the
    digest keeps unknown-access stories but won't offer them as a public
    alternate to a paywalled one.
    """
    name = normalize(publisher)
    if not name:
        return "unknown"
    # Farms are never a usable free source; treat them as unknown so they are
    # kept out of alternate selection without being labelled paywalled.
    if _matches(name, CONTENT_FARMS):
        return "unknown"
    if _matches(name, PAYWALLED):
        return "paywalled"
    if _matches(name, FREE_ALLOWLIST):
        return "free"
    return "unknown"


def is_linkable_free(publisher: str) -> bool:
    """True only for outlets we'd actively swap a paywalled link for.

    Deliberately stricter than ``classify(...) == "free"`` reads: an unknown
    outlet may well be free, but we don't have grounds to vouch for it.
    """
    return classify(publisher) == "free"
