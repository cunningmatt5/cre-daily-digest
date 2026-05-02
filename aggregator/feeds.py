import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

from .config import MAX_ARTICLES_PER_SOURCE, SUMMARY_MAX_CHARS

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


def _make_article(title, link, snippet, pub_date, pub_datetime, source, position):
    return {
        "title": title.strip(),
        "link": link.strip(),
        "summary": _truncate(snippet),
        "pub_date": pub_date,
        "pub_datetime": pub_datetime,
        "source_name": source["name"],
        "source_short": source["short"],
        "source_color": source["color"],
        "tier_weight": source["tier_weight"],
        "paywalled": source.get("paywalled", False),
        "position": position,
    }


def fetch_rss(source):
    try:
        feed = feedparser.parse(source["url"])
    except Exception:
        return []

    articles = []
    for i, entry in enumerate(feed.entries[:MAX_ARTICLES_PER_SOURCE]):
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        raw_summary = entry.get("summary", "") or entry.get("description", "")
        if raw_summary:
            raw_summary = BeautifulSoup(raw_summary, "lxml").get_text(" ", strip=True)
        pub_date, pub_datetime = _parse_rss_date(entry)
        articles.append(_make_article(title, link, raw_summary, pub_date, pub_datetime, source, i))

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
        articles.append(_make_article(title, link, snippet, pub_date, pub_datetime, source, i))

    return articles
