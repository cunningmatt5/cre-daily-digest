import feedparser
import re
import sys
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin

# Matches /YYYY/MM/DD/ in a URL path (e.g. globest.com/2026/05/01/article-title)
_URL_DATE_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")

from .config import (MAX_ARTICLES_PER_SOURCE, SUMMARY_MAX_CHARS,
                     FULL_TEXT_MAX_CHARS)
from .publishers import classify

# Every outbound fetch is bounded. Without this a single slow server could hang
# a worker until GitHub's 6-hour job ceiling.
FEED_TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _truncate(text, max_chars=SUMMARY_MAX_CHARS):
    if not text:
        return ""
    text = " ".join(text.split())
    sentences = text.split(". ")
    result = sentences[0].rstrip(".")
    if len(sentences) > 1:
        two = result + ". " + sentences[1].rstrip(".") + "."
        if len(two) <= max_chars:
            result = two
        else:
            result = result + "."
    else:
        result = result + "."
    if len(result) > max_chars:
        result = result[: max_chars - 1] + "…"
    return result


def _parse_rss_date(entry):
    """Return (display_str, datetime_obj) from a feedparser entry."""
    tp = entry.get("published_parsed") or entry.get("updated_parsed")
    if tp:
        try:
            dt = datetime(*tp[:6])
            return dt.strftime("%b %d, %Y"), dt
        except Exception:
            pass
    return "", None


def _parse_html_date(tag):
    """Return (display_str, datetime_obj) from a BeautifulSoup <time> element."""
    if not tag:
        return "", None
    raw = tag.get("datetime", "")
    if raw:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw[:19], fmt)
                return dt.strftime("%b %d, %Y"), dt
            except ValueError:
                pass
    return tag.get_text(strip=True)[:20], None


def _date_from_url(url: str):
    """Extract a date from a URL path like /2026/05/01/ as a fallback."""
    m = _URL_DATE_RE.search(url)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%b %d, %Y"), dt
        except ValueError:
            pass
    return "", None


def _make_article(title, link, snippet, pub_date, pub_datetime, source, position,
                  full_text=""):
    return {
        "title": title.strip(),
        "link": link.strip(),
        "summary": _truncate(snippet),
        # Untruncated body text where the feed provides it. ``summary`` stays
        # short for triage and the headline chip; this is the raw material the
        # long-form summarizer works from.
        "full_text": (full_text or "")[:FULL_TEXT_MAX_CHARS],
        "pub_date": pub_date,
        "pub_datetime": pub_datetime,
        "source_name": source["name"],
        "source_short": source["short"],
        "source_color": source["color"],
        "tier_weight": source["tier_weight"],
        "paywalled": source.get("paywalled", False),
        "position": position,
    }


def _apply_access(article, source):
    """Set ``access`` from the real publisher, and keep ``paywalled`` in sync.

    Classification wins where it has an opinion. Where the publisher is unknown
    we fall back to the source config's curated ``paywalled`` flag, so hand-won
    knowledge about a specific feed isn't lost.
    """
    access = classify(article["source_name"])
    if access == "unknown" and source.get("paywalled"):
        access = "paywalled"
    article["access"] = access
    article["paywalled"] = access == "paywalled"


def _gnews_publisher(entry):
    """Real publisher name from a Google News entry's <source> element, if any."""
    src = entry.get("source")
    if src is None:
        return ""
    title = getattr(src, "title", None) or (src.get("title") if isinstance(src, dict) else None)
    return (title or "").strip()


def fetch_rss(source):
    # Fetch with requests rather than letting feedparser do it. Three reasons:
    # feedparser.parse(url) has no timeout and will hang a worker indefinitely
    # on a slow server; it sends its own User-Agent, which some feeds reject;
    # and swallowing the error here meant a dead feed logged as "0 articles"
    # instead of FAILED, which is how The Real Deal's feed died unnoticed.
    # Errors now propagate to _fetch_one, which retries and reports them.
    response = requests.get(source["url"], headers=HEADERS, timeout=FEED_TIMEOUT)
    response.raise_for_status()
    feed = feedparser.parse(response.content)

    is_gnews = "news.google.com" in source["url"]
    articles = []
    for i, entry in enumerate(feed.entries[:MAX_ARTICLES_PER_SOURCE]):
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        # `content:encoded` carries near-full article text on many feeds
        # (CRE Daily ~4.4k chars, Trepp ~6k, Commercial Observer ~1.9k) while
        # `summary` holds only a teaser. Read both: the rich field feeds the
        # long-form summarizer, the teaser stays the display blurb.
        raw_summary = entry.get("summary", "") or entry.get("description", "")
        if raw_summary:
            raw_summary = BeautifulSoup(raw_summary, "lxml").get_text(" ", strip=True)
        raw_content = ""
        if entry.get("content"):
            raw_content = entry["content"][0].get("value", "") or ""
        body = raw_content or raw_summary
        if body is raw_content and body:
            body = BeautifulSoup(body, "lxml").get_text(" ", strip=True)
        pub_date, pub_datetime = _parse_rss_date(entry)
        if not pub_datetime:
            pub_date, pub_datetime = _date_from_url(link)
        article = _make_article(title, link, raw_summary, pub_date, pub_datetime, source, i,
                                full_text=body)

        # Google News items carry the originating outlet; surface it on the chip
        # and strip the trailing " - Publisher" that Google appends to titles.
        if is_gnews:
            pub = _gnews_publisher(entry)
            if pub:
                suffix = f" - {pub}"
                if article["title"].endswith(suffix):
                    article["title"] = article["title"][: -len(suffix)].strip()
                article["source_short"] = pub
                article["source_name"] = pub

        # Must run AFTER the override above: before it, every wire item still
        # carries the query's name ("CRE Headlines") rather than the outlet
        # that actually published it.
        _apply_access(article, source)
        articles.append(article)

    return articles


def scrape_headlines(source):
    try:
        r = requests.get(source["url"], headers=HEADERS, timeout=14)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "lxml")
    base = source["url"]
    candidates = []

    # Strategy 1: explicit <article> elements
    for article in soup.find_all("article"):
        heading = article.find(["h1", "h2", "h3", "h4"])
        if not heading:
            continue
        a_tag = heading.find("a", href=True) or article.find("a", href=True)
        if not a_tag:
            continue
        title = heading.get_text(strip=True)
        link = urljoin(base, a_tag["href"])
        p_tag = article.find("p")
        snippet = p_tag.get_text(strip=True) if p_tag else ""
        pub_date, pub_datetime = _parse_html_date(article.find("time"))
        if title and link:
            candidates.append((title, link, snippet, pub_date, pub_datetime))

    # Strategy 2: h2/h3 tags with anchor links
    if not candidates:
        for tag in soup.find_all(["h2", "h3"]):
            a_tag = tag.find("a", href=True)
            if not a_tag:
                parent = tag.parent
                a_tag = parent.find("a", href=True) if parent else None
            if not a_tag:
                continue
            title = tag.get_text(strip=True)
            link = urljoin(base, a_tag["href"])
            sibling = tag.find_next_sibling("p")
            snippet = sibling.get_text(strip=True) if sibling else ""
            time_tag = tag.find_next("time")
            pub_date, pub_datetime = _parse_html_date(time_tag)
            if title and link:
                candidates.append((title, link, snippet, pub_date, pub_datetime))

    # Deduplicate and cap
    seen = set()
    articles = []
    for i, (title, link, snippet, pub_date, pub_datetime) in enumerate(candidates):
        if len(articles) >= MAX_ARTICLES_PER_SOURCE:
            break
        norm = link.rstrip("/")
        if norm in seen or not title:
            continue
        seen.add(norm)
        if not snippet:
            meta = soup.find("meta", attrs={"name": "description"})
            snippet = meta.get("content", "") if meta else ""
        if not pub_datetime:
            pub_date, pub_datetime = _date_from_url(link)
        scraped = _make_article(title, link, snippet, pub_date, pub_datetime, source, i)
        _apply_access(scraped, source)
        articles.append(scraped)

    return articles


def _fetch_one(source, retries=2):
    """Fetch a single source with a small retry, returning a list of articles."""
    fetch = fetch_rss if source["method"] == "rss" else scrape_headlines
    last_exc = None
    for attempt in range(retries + 1):
        try:
            result = fetch(source)
            if result:
                return result
            # Empty result: retry once in case of a transient blip, else accept empty
        except Exception as exc:  # noqa: BLE001 — surfaced to caller for logging
            last_exc = exc
        if attempt < retries:
            time.sleep(1.0 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    return []


def fetch_all(sources, max_workers=8):
    """Fetch every source in parallel, printing per-source counts.

    Returns a flat list of article dicts. Failures are logged but never abort
    the run — a dead source just contributes nothing.
    """
    articles = []
    failed, empty = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, s): s for s in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                fetched = future.result()
                print(f"  [{source['name']}] {len(fetched)} articles")
                articles.extend(fetched)
                if not fetched:
                    empty.append(source["name"])
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{source['name']} ({type(exc).__name__})")
                print(f"  [{source['name']}] FAILED: {exc}", file=sys.stderr)

    # With 31 sources a dead feed is easy to miss in the per-source lines.
    # "Failed" means the fetch errored; "empty" means it answered with nothing,
    # which is normal for a low-cadence source like Nareit but suspicious if it
    # persists. Keeping them apart is what makes a real breakage visible.
    print(f"Source health: {len(sources) - len(failed) - len(empty)} ok, "
          f"{len(failed)} failed, {len(empty)} empty")
    if failed:
        print(f"  FAILED: {', '.join(sorted(failed))}", file=sys.stderr)
    if empty:
        print(f"  EMPTY: {', '.join(sorted(empty))}")
    return articles
