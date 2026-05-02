import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from .config import SOURCES
from .feeds import fetch_rss, scrape_headlines
from .scorer import score_and_sort
from .formatter import build_html_email
from .email_sender import send_gmail

SEEN_FILE = Path(__file__).parent.parent / "data" / "seen_urls.json"
KEEP_DAYS = 30
MAX_AGE_DAYS = 2

# Path endings that indicate a category page, landing page, or feed — not an article
_NON_ARTICLE_ENDINGS = {
    "news", "newsroom", "articles", "insights", "research", "your-research",
    "feed", "rss", "subscribe", "newsletter", "resources", "press-releases",
    "press", "media", "events", "about", "contact", "home", "overview",
    "market-research", "market-reports", "white-papers", "reports",
    "publications", "videos", "video", "podcast", "podcasts", "webinars",
    "blog", "index", "latest", "archive", "category", "tag", "topics",
    "mymmi",
}

# Profile or author URL segments indicate a person page, not an article
_PROFILE_RE = re.compile(r"/(in|author|profile|people|team|by)/[^/]+/?$", re.I)

SOCIAL_DOMAINS = {
    "linkedin.com", "www.linkedin.com",
    "twitter.com", "www.twitter.com",
    "x.com", "www.x.com",
    "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com",
    "youtube.com", "www.youtube.com",
    "tiktok.com", "www.tiktok.com",
    "reddit.com", "www.reddit.com",
    "pinterest.com", "www.pinterest.com",
    "threads.net", "www.threads.net",
}


def _is_social(article) -> bool:
    try:
        domain = urlparse(article["link"]).netloc.lower()
        return domain in SOCIAL_DOMAINS
    except Exception:
        return False


def _is_too_old(article) -> bool:
    dt = article.get("pub_datetime")
    if dt is None:
        return False
    cutoff = datetime.utcnow() - timedelta(days=MAX_AGE_DAYS)
    return dt < cutoff


def _is_non_article(article) -> bool:
    """True for landing pages, category pages, feed URLs, profile pages, etc."""
    url = article["link"]
    try:
        parsed = urlparse(url)
    except Exception:
        return True

    # Fragment anchors point to a section of a page, not a standalone article
    if parsed.fragment:
        return True

    path = parsed.path.rstrip("/")
    segments = [s for s in path.split("/") if s]

    # Bare domain or single-segment path → category or home page
    if len(segments) <= 1:
        return True

    # Last segment matches a known non-article category name
    if segments[-1].lower() in _NON_ARTICLE_ENDINGS:
        return True

    # Profile / author pages
    if _PROFILE_RE.search(path):
        return True

    # Title too short to be a real headline (navigation labels, e.g. "Newsroom", "Your Research")
    if len(article.get("title", "")) < 20:
        return True

    return False


def _has_no_date(article) -> bool:
    return article.get("pub_datetime") is None


def load_seen_urls() -> set:
    if not SEEN_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    cutoff = date.today() - timedelta(days=KEEP_DAYS)
    seen = set()
    for date_str, urls in data.items():
        try:
            if date.fromisoformat(date_str) >= cutoff:
                seen.update(urls)
        except ValueError:
            pass
    return seen


def save_seen_urls(urls: list):
    SEEN_FILE.parent.mkdir(exist_ok=True)
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8")) if SEEN_FILE.exists() else {}
    except Exception:
        data = {}
    cutoff = date.today() - timedelta(days=KEEP_DAYS)
    data = {k: v for k, v in data.items()
            if date.fromisoformat(k) >= cutoff}
    today_str = date.today().isoformat()
    data[today_str] = list(set(data.get(today_str, [])) | set(urls))
    SEEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    print("Fetching CRE articles...")
    articles = []
    for source in SOURCES:
        try:
            if source["method"] == "rss":
                fetched = fetch_rss(source)
            else:
                fetched = scrape_headlines(source)
            print(f"  [{source['name']}] {len(fetched)} articles")
            articles.extend(fetched)
        except Exception as exc:
            print(f"  [{source['name']}] FAILED: {exc}", file=sys.stderr)

    if not articles:
        print("No articles fetched — aborting.", file=sys.stderr)
        sys.exit(1)

    # Drop social media links
    before = len(articles)
    articles = [a for a in articles if not _is_social(a)]
    print(f"Social filter:      {before:3} → {len(articles):3} ({before - len(articles)} removed)")

    # Drop landing pages, category pages, feed URLs, profile pages
    before = len(articles)
    articles = [a for a in articles if not _is_non_article(a)]
    print(f"Non-article filter: {before:3} → {len(articles):3} ({before - len(articles)} removed)")

    # Drop articles with no parseable publish date
    before = len(articles)
    articles = [a for a in articles if not _has_no_date(a)]
    print(f"No-date filter:     {before:3} → {len(articles):3} ({before - len(articles)} removed)")

    # Drop articles older than 2 days
    before = len(articles)
    articles = [a for a in articles if not _is_too_old(a)]
    print(f"Age filter:         {before:3} → {len(articles):3} ({before - len(articles)} too old)")

    seen_urls = load_seen_urls()
    before = len(articles)
    articles = [a for a in articles if a["link"].rstrip("/") not in seen_urls]
    print(f"Deduplication: {before} → {len(articles)} articles ({before - len(articles)} already sent)")

    if not articles:
        print("All articles already sent in previous digests — nothing new to send.")
        sys.exit(0)

    ranked = score_and_sort(articles)
    print(f"Ranked {len(ranked)} articles total")

    today = date.today()
    subject = f"CRE Daily Digest — {today.strftime('%B %d, %Y')}"
    html = build_html_email(ranked, today)
    send_gmail(html, subject)

    save_seen_urls([a["link"].rstrip("/") for a in ranked])
    print("Seen URLs updated.")


if __name__ == "__main__":
    main()
