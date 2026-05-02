import sys
from datetime import date

from .config import SOURCES
from .feeds import fetch_rss, scrape_headlines
from .scorer import score_and_sort
from .formatter import build_html_email
from .email_sender import send_gmail


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

    ranked = score_and_sort(articles)
    print(f"Ranked {len(ranked)} articles total")

    today = date.today()
    subject = f"CRE Daily Digest — {today.strftime('%B %d, %Y')}"
    html = build_html_email(ranked, today)
    send_gmail(html, subject)


if __name__ == "__main__":
    main()
