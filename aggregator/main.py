import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from .config import (SOURCES, MAX_PER_SECTOR, DISPLAY_MIN_SIGNIFICANCE,
                     DISPLAY_MIN_STORIES, DISPLAY_MAX_STORIES, REST_MAX_STORIES)
from .feeds import fetch_all
from .scorer import score_and_sort, group_by_sector
from .select import select_display
from .enrich import enrich, elaborate
from .extract import gather
from .resolve import resolve_links, is_google_link
from .publishers import classify
from .publicize import resolve_all, apply_alternate
from .formatter import build_html_email
from .email_sender import send_gmail

SEEN_FILE = Path(__file__).parent.parent / "data" / "seen_urls.json"
PREVIEW_FILE = Path(__file__).parent.parent / "data" / "preview.html"
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


def _non_article_reason(article) -> str:
    """Returns a reason string if the article should be filtered, empty string if it should pass."""
    url = article["link"]
    try:
        parsed = urlparse(url)
    except Exception:
        return "unparseable URL"

    if parsed.fragment:
        return f"fragment anchor (#{parsed.fragment})"

    path = parsed.path.rstrip("/")
    segments = [s for s in path.split("/") if s]

    if len(segments) == 0:
        return "bare domain"

    if len(segments) == 1:
        slug = segments[0].lower()
        # Known generic category names are always filtered
        if slug in _NON_ARTICLE_ENDINGS:
            return f"category path ({slug})"
        # Short slugs with few hyphens are likely category pages, not articles
        # Long hyphenated slugs (e.g. lodgingmagazine.com/choice-hotels-q1-results)
        # are article URLs and should pass through
        if len(slug) < 25 and slug.count("-") < 3:
            return f"short non-slug path ({slug})"

    last = segments[-1].lower()
    if last in _NON_ARTICLE_ENDINGS:
        return f"category/landing path ending ({last})"

    if _PROFILE_RE.search(path):
        return f"profile/author path ({path})"

    if len(article.get("title", "")) < 20:
        return f"title too short ({repr(article.get('title', ''))})"

    return ""


def _is_non_article(article) -> bool:
    return bool(_non_article_reason(article))


def _has_no_date(article) -> bool:
    return article.get("pub_datetime") is None


def _refine_access_from_domain(article) -> bool:
    """Use the resolved domain to settle access when the publisher name didn't.

    Publisher names from Google News are inconsistent ("WSJ", "wsj.com", "Wall
    Street Journal") and unfamiliar outlets classify as unknown. The domain is
    a second, cleaner signal — but only trusted to *add* information, never to
    override a confident name match.
    """
    if article.get("access") != "unknown":
        return False
    domain = urlparse(article.get("link", "")).netloc.lower()
    if not domain:
        return False
    verdict = classify(domain)
    if verdict == "unknown":
        return False
    article["access"] = verdict
    article["paywalled"] = verdict == "paywalled"
    return True


def load_seen_urls() -> set:
    if not SEEN_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    today = date.today()
    cutoff = today - timedelta(days=KEEP_DAYS)
    seen = set()
    for date_str, urls in data.items():
        try:
            d = date.fromisoformat(date_str)
            # Only block articles from previous days, not today.
            # This allows same-day reruns to resend the current digest.
            if cutoff <= d < today:
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

    def _fresh(key):
        # A malformed key must not crash a run whose email has already gone out.
        # load_seen_urls has always tolerated this; save did not.
        try:
            return date.fromisoformat(key) >= cutoff
        except ValueError:
            return False

    data = {k: v for k, v in data.items() if _fresh(k)}
    today_str = date.today().isoformat()
    data[today_str] = list(set(data.get(today_str, [])) | set(urls))
    SEEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    # Logs use Unicode (→, ·); force UTF-8 so a Windows cp1252 console doesn't crash.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    dry_run = os.environ.get("DIGEST_DRY_RUN") == "1"

    print("Fetching CRE articles...")
    articles = fetch_all(SOURCES)

    if not articles:
        print("No articles fetched — aborting.", file=sys.stderr)
        sys.exit(1)

    def _apply(label, predicate, reason_fn=None):
        kept, dropped = [], []
        for a in articles:
            if predicate(a):
                dropped.append(a)
            else:
                kept.append(a)
        print(f"{label}: {len(articles):3} → {len(kept):3}  ({len(dropped)} removed)")
        for a in dropped:
            reason = reason_fn(a) if reason_fn else ""
            print(f"  DROPPED [{a['source_name']}] {a['title'][:80]!r}  |  {a['link'][:80]}"
                  + (f"  |  {reason}" if reason else ""))
        return kept

    articles = _apply("Social filter     ", _is_social)
    articles = _apply("Non-article filter", _is_non_article, _non_article_reason)
    articles = _apply("No-date filter    ", _has_no_date)
    articles = _apply("Age filter        ", _is_too_old,
                      lambda a: f"pub {a['pub_datetime'].strftime('%Y-%m-%d %H:%M') if a.get('pub_datetime') else 'no date'}")

    seen_urls = load_seen_urls()
    before = len(articles)
    articles = [a for a in articles if a["link"].rstrip("/") not in seen_urls]
    print(f"Deduplication: {before} → {len(articles)} articles ({before - len(articles)} already sent)")

    if not articles:
        print("All articles already sent in previous digests — nothing new to send.")
        sys.exit(0)

    # Claude enrichment (cluster + rank + summarize + sector). Falls back to the
    # deterministic scorer if the API is unavailable, so the digest always sends.
    lead = None
    result = enrich(articles)
    if result is not None:
        lead, ranked = result
        enriched = True
    else:
        ranked = score_and_sort(articles)
        enriched = False
        print(f"Deterministic ranking: {len(ranked)} stories")

    # Significance floor — show only critical stories. LLM significance is a
    # calibrated 0–100; the fallback scorer's scale isn't, so skip the floor there.
    floor = DISPLAY_MIN_SIGNIFICANCE if enriched else 0
    sections, displayed, rest, sel = select_display(
        ranked, group_by_sector,
        floor=floor, min_stories=DISPLAY_MIN_STORIES, max_stories=DISPLAY_MAX_STORIES,
        max_per_sector=MAX_PER_SECTOR, rest_max=REST_MAX_STORIES,
    )

    if sel["floor_fallback"]:
        print(f"Significance floor ({floor}) left only {sel['cleared_floor']} "
              f"(< {DISPLAY_MIN_STORIES}); showing top {len(displayed)} by significance instead.")
    elif sel["below"]:
        print(f"Significance floor ({floor}): hiding {len(sel['below'])} below-threshold stories")
        for a in sel["below"]:
            print(f"  BELOW[{a.get('significance')}] [{a.get('sector')}] {a['title'][:80]!r}")

    if sel["cut"]:
        print(f"Story cap: showing top {DISPLAY_MAX_STORIES} by significance, "
              f"cutting {len(sel['cut'])} above the floor")
        # These cleared the quality floor and were dropped purely for length.
        # Logging them is the only way to notice a major story being squeezed
        # out by a crowded day.
        for a in sel["cut"][:12]:
            print(f"  CUT[{a.get('significance')}] [{a.get('sector')}] {a['title'][:78]!r}")
        if len(sel["cut"]) > 12:
            print(f"  ... and {len(sel['cut']) - 12} more")

    if sel["backfilled"]:
        print(f"Backfilled {sel['backfilled']} stories displaced by the sector cap")

    shown = len(displayed)
    if sel["rest_range"]:
        print(f"Best of the Rest: {len(rest)} additional stories "
              f"(significance {sel['rest_range'][0]} down to {sel['rest_range'][1]})")

    top_stories = sorted(displayed, key=lambda x: x.get("significance", 0), reverse=True)[:5]
    sigs = [a.get("significance", 0) for a in displayed]
    print(f"Display: {len(ranked)} ranked -> {shown} shown (floor {floor}, "
          f"max {DISPLAY_MAX_STORIES}, {MAX_PER_SECTOR}/sector)")
    if sigs:
        # The priority check: if the top of this list isn't the day's big news,
        # the significance rubric is the thing to fix, not the display logic.
        print(f"Significance of shown stories: {max(sigs)} high, {min(sigs)} low, "
              f"median {sorted(sigs)[len(sigs)//2]}")
        for a in sorted(displayed, key=lambda x: x.get("significance", 0), reverse=True):
            print(f"  SHOWN[{a.get('significance')}] [{a.get('sector')}] {a['title'][:78]!r}")

    # Long-form pass, over the displayed stories only. `displayed` holds the same
    # dicts as `sections`, so summaries written here land in the rendered email.
    if enriched and displayed:
        # Turn Google News bounce links into real publisher URLs. Done for the
        # displayed stories only — it costs two requests per link, and these are
        # the only links a reader will ever click. Wins: a direct link instead of
        # a Google interstitial, a real domain to sanity-check access against,
        # and an article we can actually fetch to summarize.
        # Resolve links for the Best of the Rest too — they're clickable, so
        # they shouldn't land on a Google interstitial either. They stop there:
        # no body fetch, no summarizer.
        link_stats = resolve_links(displayed + rest)
        if link_stats["attempted"]:
            print(f"Link resolution: {link_stats['resolved']}/{link_stats['attempted']} "
                  f"Google News links resolved to publisher URLs")
        refined = 0
        for story in displayed + rest:
            if story.get("google_link"):
                refined += _refine_access_from_domain(story)
        if refined:
            print(f"Access refined from resolved domain: {refined} stories")

        # Find a freely readable source for gated stories. Runs after link
        # resolution so `access` reflects the real domain, and so candidates can
        # be ranked on whether their URL is actually fetchable. Cluster
        # candidates are same-story by construction (triage grouped them), so
        # they apply immediately — and bring their text with them. Search
        # candidates are unverified and wait for the model to confirm.
        alt_stats = resolve_all(displayed)
        applied_now = 0
        for story in displayed:
            alt = story.get("public_alt")
            if alt and alt.get("origin") == "cluster":
                story["alt_confirmed"] = True
                applied_now += apply_alternate(story)
        print(f"Public sources: {alt_stats['gated']} gated -> "
              f"{alt_stats['cluster']} from cluster ({applied_now} applied), "
              f"{alt_stats['search']} pending confirmation, {alt_stats['none']} none found "
              f"({alt_stats['fetchable']} fetchable)")

        origins = gather(displayed)
        print(f"Source text: {origins['feed']} from feed, {origins['body']} fetched, "
              f"{origins['thin']} thin (headline only)")

        fresh_lead = elaborate(displayed)
        if fresh_lead:
            lead = fresh_lead

        # Apply the alternates the model confirmed; drop the ones it rejected.
        confirmed = rejected = 0
        for story in displayed:
            if not story.get("public_alt") or story.get("link") == story["public_alt"]["link"]:
                continue
            if story.get("alt_confirmed"):
                confirmed += apply_alternate(story)
            else:
                rejected += 1
                story.pop("public_alt", None)
        still_gated = sum(1 for s in displayed if s.get("access") == "paywalled")
        print(f"Alternates confirmed: {confirmed} applied, {rejected} rejected as "
              f"not-the-same-story; {still_gated} stories remain paywalled")

        # Search-found alternates carry Google News URLs, so applying one puts a
        # bounce link back on a story that had already been resolved — on
        # precisely the gated stories this is all meant to help. Resolve again.
        swapped = [s for s in displayed if is_google_link(s.get("link", ""))]
        if swapped:
            # Re-resolving overwrites `google_link`, which the seen-URL ledger
            # reads. Park the first-round bounce URL in cluster_links (also
            # retired) so the original story can't come back as new tomorrow.
            for story in swapped:
                prior = story.get("google_link")
                if prior:
                    story.setdefault("cluster_links", []).append(prior)
            again = resolve_links(swapped)
            print(f"Alternate links resolved: {again['resolved']}/{again['attempted']}")

    today = date.today()
    subject = f"CRE Daily Digest — {today.strftime('%B %d, %Y')}"
    html = build_html_email(today, sections, lead=lead, top_stories=top_stories,
                            count=shown, rest=rest)

    if dry_run:
        PREVIEW_FILE.parent.mkdir(exist_ok=True)
        PREVIEW_FILE.write_text(html, encoding="utf-8")
        print(f"DRY RUN — wrote preview to {PREVIEW_FILE} (no email sent, seen URLs unchanged).")
        return

    send_gmail(html, subject)

    # Retire only what the reader actually saw, plus the other outlets' versions
    # of those same stories. Previously every *ranked* story was retired, which
    # permanently buried anything the significance floor hid — ~48 stories a day
    # that were never shown to anyone. A story held back today can now resurface
    # tomorrow if it still matters; the age filter (MAX_AGE_DAYS) bounds how long
    # it can keep recirculating, so nothing stale leaks back in.
    displayed = [a for _, items in sections for a in items]
    # Best of the Rest stories were linked in the email too, so they count as
    # delivered — otherwise they'd reappear as fresh news tomorrow.
    delivered = displayed + rest
    sent_links = {a["link"].rstrip("/") for a in delivered}
    for a in delivered:
        for link in a.get("cluster_links") or []:
            sent_links.add(link.rstrip("/"))
        # A resolved story is keyed on its publisher URL, but tomorrow's fetch
        # produces the Google News URL again. Retire both, or every resolved
        # story comes back as new.
        if a.get("google_link"):
            sent_links.add(a["google_link"].rstrip("/"))
    save_seen_urls(sorted(sent_links))
    print(f"Seen URLs updated ({len(sent_links)} links from {len(delivered)} delivered "
          f"stories — {len(displayed)} summarized, {len(rest)} in Best of the Rest; "
          f"{len(ranked) - len(delivered)} unshown stories left eligible for tomorrow).")


if __name__ == "__main__":
    main()
