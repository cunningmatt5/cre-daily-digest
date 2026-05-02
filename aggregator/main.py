import json
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
        return False  # no date available — keep it (scraped homepage content is inherently recent)
    cutoff = datetime.utcnow() - timedelta(days=MAX_AGE_DAYS)
    return dt < cutoff


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

    # Filter social media links
    before = len(articles)
    articles = [a for a in articles if not _is_social(a)]
    print(f"Social filter: {before} → {len(articles)} ({before - len(articles)} removed)")

    # Filter articles older than 2 days
    before = len(articles)
    articles = [a for a in articles if not _is_too_old(a)]
    print(f"Age filter: {before} → {len(articles)} ({before - len(articles)} too old)")

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
