"""Gather the best available source text for the stories we're going to show.

A 4–5 sentence summary is only honest if there is something to summarize. Text
comes from three places, in descending order of quality:

1. ``full_text`` straight off the feed — ``content:encoded`` carries near-full
   articles on some feeds (CRE Daily ~4.4k chars, Trepp ~6k, Commercial
   Observer ~1.9k). Free, already fetched.
2. The article body, fetched and stripped. Only possible for direct publisher
   links — Google News URLs are opaque bounce pages, and they're the majority
   of the pool.
3. Headline plus teaser blurb. Marked ``text_thin`` so the summarizer writes
   fewer sentences instead of padding.

Runs only over the display set (~15 stories), not the full candidate pool.
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from .config import FULL_TEXT_MAX_CHARS, THIN_TEXT_CHARS
from .feeds import HEADERS
from .resolve import is_direct_link

# Chrome that a paywall teaser leaves behind. Not used to *detect* paywalls —
# testing showed Commercial Observer and Bisnow both trip paywall-marker
# regexes while still serving the full article, so marker matching gives false
# positives. Extracted length is the reliable signal instead.
_STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form",
               "figure", "noscript"]




def fetch_body(link: str, timeout: int = 14) -> str:
    """Return cleaned article body text, or "" if it can't be had.

    Deliberately forgiving: any failure returns empty and the caller falls back
    a tier. Never raises.
    """
    if not is_direct_link(link):
        return ""
    try:
        r = requests.get(link, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "lxml")
    except Exception:  # noqa: BLE001 — degrade a tier, never abort the digest
        return ""
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    # Short <p> tags are almost always captions, bylines or nav crumbs.
    body = " ".join(p for p in paras if len(p) > 40)
    return body[:FULL_TEXT_MAX_CHARS]


def best_text(article) -> tuple:
    """Return ``(text, origin)`` — the richest text available for one article.

    ``origin`` is ``"feed"``, ``"body"`` or ``"thin"``, for logging and so the
    prompt knows how much it has to work with.
    """
    feed_text = (article.get("full_text") or "").strip()
    if len(feed_text) >= THIN_TEXT_CHARS:
        return feed_text, "feed"

    body = fetch_body(article.get("link", ""))
    if len(body) >= THIN_TEXT_CHARS:
        return body, "body"

    # Keep whichever scrap is longer rather than dropping to the headline.
    fallback = max(feed_text, (article.get("summary") or "").strip(), key=len)
    return fallback, "thin"


def gather(articles, max_workers: int = 6) -> dict:
    """Attach ``source_text``/``text_origin``/``text_thin`` to each article.

    Fetches in parallel but stays modestly concurrent — this hits publisher
    sites directly, so it should never look like a crawl. Returns a count by
    origin for the funnel log.
    """
    counts = {"feed": 0, "body": 0, "thin": 0}
    if not articles:
        return counts

    def work(a):
        text, origin = best_text(a)
        return a, text, origin

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(work, a) for a in articles]
        for future in as_completed(futures):
            try:
                a, text, origin = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  text gather failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                continue
            a["source_text"] = text
            a["text_origin"] = origin
            a["text_thin"] = origin == "thin"
            counts[origin] += 1

    # Anything the pool dropped still needs the keys set.
    for a in articles:
        if "source_text" not in a:
            a["source_text"] = (a.get("summary") or "").strip()
            a["text_origin"] = "thin"
            a["text_thin"] = True
            counts["thin"] += 1
    return counts
