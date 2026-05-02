import json
import sys
from datetime import date, timedelta
from pathlib import Path

from .config import SOURCES
from .feeds import fetch_rss, scrape_headlines
from .scorer import score_and_sort
from .formatter import build_html_email
from .email_sender import send_gmail

SEEN_FILE = Path(__file__).parent.parent / "data" / "seen_urls.json"
KEEP_DAYS = 30


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
