"""Find a freely readable source for stories whose own outlet is gated.

Two jobs, and the second one is easy to miss. The obvious job is giving the
reader a link that opens. The less obvious one is that a good alternate also
supplies *text*: measured on a real run, 10 of 15 displayed stories had nothing
but a headline, because ranking by significance systematically selects for
Bloomberg / CoStar / wire stories whose Google News links can't be fetched. An
alternate from a directly-fetchable outlet fixes both at once.

Candidates come from two places, cheapest first:

1. **The story's own cluster.** Triage already grouped outlets covering the same
   event, so these are same-story by construction — no verification needed — and
   cost no extra requests. A cluster member from a direct-feed outlet is the
   single best outcome available: public link *and* real body text.
2. **A Google News keyword search.** Wider reach, but the hits are unverified and
   their links are Google News bounce URLs, so they fix the link and not the
   text. Gated behind a title-similarity check and confirmed by the model later.
"""

import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import gnews
from .publishers import is_content_farm, is_linkable_free
from .scorer import _title_tokens

# Search hits are only keyword matches — the "$1M home" probe returned
# topically-related but genuinely different articles. Require substantial title
# overlap before a hit is even offered to the model for confirmation.
_MIN_TITLE_OVERLAP = 0.45

_STOPWORDS = {"the", "a", "an", "of", "in", "on", "for", "and", "to", "as", "at",
              "by", "with", "from", "is", "are", "says", "said", "after", "its",
              "amid", "over", "new"}


def _is_direct(link: str) -> bool:
    """True when the URL is a real publisher page we could fetch."""
    return bool(link) and "news.google.com" not in link


def _search_query(title: str, max_words: int = 9) -> str:
    cleaned = re.sub(r"[^\w\s$%.-]", " ", title or "")
    words = [w for w in cleaned.split() if w.lower() not in _STOPWORDS]
    return " ".join(words[:max_words])


def _same_story(title_a: str, title_b: str) -> float:
    a, b = _title_tokens(title_a or ""), _title_tokens(title_b or "")
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _rank_candidate(cand) -> tuple:
    """Sort key: allowlisted first, then fetchable, then richer text.

    Fetchability is weighted deliberately — a public link the summarizer can
    also read is worth more than one it can only link to.
    """
    return (
        is_linkable_free(cand.get("source_name", "")),
        _is_direct(cand.get("link", "")),
        len(cand.get("full_text") or ""),
    )


def _from_cluster(story):
    """Same-story alternates already in hand. Free, and pre-verified."""
    out = []
    for m in story.get("cluster_members") or []:
        name = m.get("source_name", "")
        if m.get("access") == "paywalled" or is_content_farm(name):
            continue
        if not is_linkable_free(name) or not m.get("link"):
            continue
        out.append({**m, "origin": "cluster"})
    return out


def _from_search(story, days=4, max_hits=3):
    """Wider net via Google News. Hits are unverified keyword matches."""
    from .feeds import fetch_rss  # local import: feeds imports publishers, not us

    query = _search_query(story.get("title", ""))
    if len(query) < 12:
        return []
    probe = {"name": "alt-probe", "short": "alt", "url": gnews(query, days=days),
             "method": "rss", "tier_weight": 1, "color": "#000"}
    out = []
    for hit in fetch_rss(probe):
        name = hit.get("source_name", "")
        if is_content_farm(name) or not is_linkable_free(name):
            continue
        overlap = _same_story(story.get("title"), hit.get("title"))
        if overlap < _MIN_TITLE_OVERLAP:
            continue
        out.append({
            "link": hit.get("link", ""),
            "title": hit.get("title", ""),
            "source_name": name,
            "source_short": hit.get("source_short", name),
            "access": hit.get("access", "unknown"),
            "full_text": hit.get("full_text", ""),
            "summary": hit.get("summary", ""),
            "origin": "search",
            "overlap": round(overlap, 2),
        })
        if len(out) >= max_hits:
            break
    return out


def _resolve_one(story, allow_search=True):
    candidates = _from_cluster(story)
    # Only pay for a search when the cluster gave us nothing usable.
    if not candidates and allow_search:
        try:
            candidates = _from_search(story)
        except Exception as exc:  # noqa: BLE001 — an alternate is a bonus, never fatal
            print(f"  alternate search failed for {story.get('title','')[:50]!r}: "
                  f"{type(exc).__name__}", file=sys.stderr)
            candidates = []
    if not candidates:
        return None
    return sorted(candidates, key=_rank_candidate, reverse=True)[0]


def resolve_all(stories, max_workers=6):
    """Attach a ``public_alt`` to each gated story that has one.

    Only sets the candidate — the link isn't swapped until the model confirms
    it's the same story (search hits) in ``enrich.elaborate``. Cluster
    candidates are pre-confirmed by triage's own clustering.

    Returns counts for the funnel log.
    """
    gated = [s for s in stories if s.get("access") == "paywalled"]
    stats = {"gated": len(gated), "cluster": 0, "search": 0, "none": 0, "fetchable": 0}
    if not gated:
        return stats

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_resolve_one, s): s for s in gated}
        for future in as_completed(futures):
            story = futures[future]
            try:
                alt = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  alternate resolution failed: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                alt = None
            if not alt:
                stats["none"] += 1
                continue
            story["public_alt"] = alt
            stats[alt["origin"]] += 1
            if _is_direct(alt.get("link", "")):
                stats["fetchable"] += 1
    return stats


def apply_alternate(story):
    """Swap in the confirmed public source, preserving provenance.

    Called only after confirmation. Keeps the original outlet on the story as
    ``original_source`` so the email can credit who actually broke it.
    """
    alt = story.get("public_alt")
    if not alt:
        return False
    story["original_source"] = story.get("source_short") or story.get("source_name")
    story["link"] = alt["link"]
    story["source_short"] = alt.get("source_short") or alt.get("source_name")
    story["source_name"] = alt.get("source_name", "")
    story["access"] = "free"
    story["paywalled"] = False
    # Borrow the alternate's text when it's richer — this is what turns a
    # headline-only story into one that can carry a real summary.
    if len(alt.get("full_text") or "") > len(story.get("full_text") or ""):
        story["full_text"] = alt["full_text"]
    return True
