import feedparser
import requests
from bs4 import BeautifulSoup
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


def _make_article(title, link, snippet, source, position):
    return {
        "title": title.strip(),
        "link": link.strip(),
        "summary": _truncate(snippet),
        "source_name": source["name"],
        "source_short": source["short"],
        "source_color": source["color"],
        "tier_weight": source["tier_weight"],
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
        articles.append(_make_article(title, link, raw_summary, source, i))

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
        if title and link:
            candidates.append((title, link, snippet))

    # Strategy 2: h2/h3 tags with anchor links
    if not candidates:
        for tag in soup.find_all(["h2", "h3"]):
            a_tag = tag.find("a", href=True)
            if not a_tag:
                # try parent
                parent = tag.parent
                a_tag = parent.find("a", href=True) if parent else None
            if not a_tag:
                continue
            title = tag.get_text(strip=True)
            link = urljoin(base, a_tag["href"])
            sibling = tag.find_next_sibling("p")
            snippet = sibling.get_text(strip=True) if sibling else ""
            if title and link:
                candidates.append((title, link, snippet))

    # Deduplicate and cap
    seen = set()
    articles = []
    for i, (title, link, snippet) in enumerate(candidates):
        if len(articles) >= MAX_ARTICLES_PER_SOURCE:
            break
        norm = link.rstrip("/")
        if norm in seen or not title:
            continue
        seen.add(norm)
        # Fallback summary: page-level meta description (same for all, used only when nothing else)
        if not snippet:
            meta = soup.find("meta", attrs={"name": "description"})
            snippet = meta.get("content", "") if meta else ""
        articles.append(_make_article(title, link, snippet, source, i))

    return articles
