"""Claude-powered enrichment: cluster, rank, summarize, and sector-tag articles.

A single structured-output call replaces the regex scorer's keyword math with
actual editorial judgment. If anything goes wrong (no API key, network error,
malformed response) ``enrich`` returns ``None`` and the caller falls back to the
deterministic scorer, so the digest always sends.
"""

import json
import sys

from .config import LLM_MODEL, SECTORS, MAX_TOTAL_ARTICLES
from .publishers import is_content_farm

# Per-article fields the model returns. Numeric bounds are described in prose
# (the prompt), not as JSON-Schema min/max — structured outputs ignore those.
_SCHEMA = {
    "type": "object",
    "properties": {
        "lead": {"type": "string"},
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "keep": {"type": "boolean"},
                    "significance": {"type": "integer"},
                    "sector": {"type": "string", "enum": SECTORS},
                    "summary": {"type": "string"},
                    "cluster": {"type": "integer"},
                },
                "required": ["id", "keep", "significance", "sector", "summary", "cluster"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["lead", "articles"],
    "additionalProperties": False,
}

_SYSTEM = f"""You are the editor of a commercial real estate (CRE) daily news digest read by \
institutional investors, brokers, and lenders. You receive the day's candidate \
headlines (with short blurbs and sources) and must turn them into a ranked, \
deduplicated, sector-organized brief.

For EACH input article, decide:

- keep: default to TRUE. Only mark false for items that are clearly NOT \
commercial-real-estate news: pure marketing/sponsored/press-release fluff, SEO \
listicles ("top 10 brokers"), event or webinar promos, paywall/login stubs or \
empty/garbled headlines, purely residential consumer real estate, or articles \
unrelated to CRE. When in doubt, KEEP it — use a low significance score to rank \
minor stories down rather than dropping them. Better to include a marginal CRE \
story than to omit a real one.

- significance: 0–100 for genuine market impact to an institutional CRE \
audience. Use the FULL range and anchor to these bands (do not compress toward \
the middle):
  • 85-100 = market-defining: multi-billion-dollar deals, major M&A/IPOs, or \
market-moving macro/policy (Fed rate decisions, major legislation).
  • 70-84 = major: $500M+ transactions; marquee institutions (Blackstone, \
Brookfield, KKR, Starwood, Apollo, major REITs and brokers like CBRE/JLL) making \
real moves; large defaults/distress; significant fund closes; sector-wide shifts.
  • 55-69 = notable: ~$100M-$500M deals, mid-size-firm activity, meaningful \
regional market or regulatory developments.
  • 40-54 = routine: smaller or local single-asset deals, individual leases, \
incremental research notes.
  • below 40 = minor/marginal.
A $1B+ deal or a Blackstone/Starwood-scale move is an 80+, not a 55. Reserve \
sub-55 scores for genuinely small or local items.

- sector: choose the single best fit from this exact list: {", ".join(SECTORS)}. \
Use "Capital Markets" for financing/M&A/fund/REIT-level stories that aren't tied \
to one property type, "Macro & Policy" for rates/economy/regulation, and "Other" \
only when nothing else fits.

- summary: one or two tight, factual sentences (~25–40 words) capturing what \
happened and why it matters. No hype, no "the article discusses". If the source \
blurb is empty or unhelpful, write the summary from the headline.

- cluster: integer grouping articles that cover the SAME underlying event/deal \
(e.g. five outlets reporting one Blackstone acquisition share one cluster number). \
Give each distinct story its own unique cluster number.

Also write a "lead": 2–3 sentence editor's brief on the most important CRE themes \
of the day, referencing the top stories. Punchy and specific.

Return every input article id exactly once."""


def _build_input(articles):
    lines = []
    for i, a in enumerate(articles):
        date = a.get("pub_date") or "no date"
        src = a.get("source_short", "?")
        summary = (a.get("summary") or "").strip()
        lines.append(f"[{i}] ({src}, {date}) {a['title']}")
        if summary:
            lines.append(f"    {summary}")
    return "\n".join(lines)


def _call_model(user, system, schema, max_tokens=32000):
    import anthropic

    client = anthropic.Anthropic()
    # Bulk classification against an explicit rubric — not deep reasoning.
    # Extended thinking would consume the token budget and starve the JSON
    # output (it once truncated 127 articles down to 2). Disable it and give
    # the whole budget to the structured output; the schema constrains the
    # response, so no reasoning can leak into the text.
    with client.messages.stream(
        model=LLM_MODEL,
        max_tokens=max_tokens,
        thinking={"type": "disabled"},
        output_config={"format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = stream.get_final_message()

    text = next((b.text for b in message.content if b.type == "text"), "")
    return json.loads(text)


# The model must return at least this fraction of the articles it was given.
# A smaller result means the response was truncated, and shipping it produces a
# near-empty digest (on 2026-09-06 a run returned 1 article out of 77 and the
# digest went out with a single story). Treated as a hard failure, not a warning.
MIN_RETURN_RATIO = 0.6
_MAX_ATTEMPTS = 2


def _call_with_retry(user, system, schema, expected, label="Enrichment",
                     max_tokens=32000):
    """Return usable model output, or ``None`` if every attempt failed.

    Retries once on either an API error or a truncated response — truncation has
    been transient in practice, so a second call usually succeeds and is far
    cheaper than degrading the whole digest to the deterministic scorer.
    """
    need = MIN_RETURN_RATIO * expected
    problem = "no attempt made"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            data = _call_model(user, system, schema, max_tokens)
        except Exception as exc:  # noqa: BLE001 — any failure is retried, then degrades
            problem = f"{type(exc).__name__}: {exc}"
            print(f"{label} attempt {attempt}/{_MAX_ATTEMPTS} errored ({problem}).",
                  file=sys.stderr)
            continue
        returned = len(data.get("articles") or [])
        if returned >= need:
            if attempt > 1:
                print(f"{label} recovered on attempt {attempt} "
                      f"({returned}/{expected} articles).", file=sys.stderr)
            return data
        problem = f"returned {returned} of {expected} articles (need >= {need:.0f})"
        print(f"{label} attempt {attempt}/{_MAX_ATTEMPTS} truncated — {problem}.",
              file=sys.stderr)
    print(f"{label} unusable after {_MAX_ATTEMPTS} attempts ({problem}).",
          file=sys.stderr)
    return None


def enrich(articles):
    """Return ``(lead, ranked_articles)`` or ``None`` to signal fallback.

    ``ranked_articles`` are canonical (deduped) article dicts, each augmented
    with ``significance``, ``sector``, an LLM ``summary``, and ``also_sources``
    (the short names of other outlets that covered the same story). Sorted by
    significance, descending, capped at ``MAX_TOTAL_ARTICLES``.
    """
    if not articles:
        return None

    user = (
        "Here are today's candidate CRE articles. Process every one per your "
        "instructions.\n\n" + _build_input(articles)
    )
    data = _call_with_retry(user, _SYSTEM, _SCHEMA, len(articles), label="Enrichment")
    if data is None:
        print("Falling back to deterministic scorer.", file=sys.stderr)
        return None

    lead = (data.get("lead") or "").strip()
    enriched = data.get("articles") or []

    # Group kept articles by cluster; track what the model dropped.
    clusters = {}
    dropped_titles = []
    for e in enriched:
        idx = e.get("id")
        valid = isinstance(idx, int) and 0 <= idx < len(articles)
        if not e.get("keep"):
            if valid:
                dropped_titles.append(articles[idx]["title"])
            continue
        if not valid:
            continue
        sector = e.get("sector") if e.get("sector") in SECTORS else "Other"
        # A non-numeric or null significance would raise here. The whole point
        # of this module is that the digest always sends, so a malformed field
        # costs one story, not the run.
        try:
            significance = int(e.get("significance", 0))
        except (TypeError, ValueError):
            significance = 0
        item = {
            "article": articles[idx],
            "significance": significance,
            "sector": sector,
            "summary": (e.get("summary") or "").strip(),
        }
        clusters.setdefault(e.get("cluster"), []).append(item)

    if not clusters:
        print("Enrichment kept no articles; falling back.", file=sys.stderr)
        return None

    ranked = []
    for members in clusters.values():
        # Highest significance wins, but never let a content farm represent a
        # story a real outlet also covered — farms are rewrites, and their
        # byline would front the email. They stay in the cluster (so their
        # URL is still retired) and can still be the canonical if nothing
        # else covered the story at all.
        members.sort(key=lambda m: (not is_content_farm(m["article"].get("source_name")),
                                    m["significance"]), reverse=True)
        canonical = members[0]
        a = dict(canonical["article"])
        a["significance"] = canonical["significance"]
        a["sector"] = canonical["sector"]
        a["summary"] = canonical["summary"] or a.get("summary", "")
        # Other outlets that covered the same story (dedup, drop the canonical's own).
        also = []
        seen = {a.get("source_short")}
        for m in members[1:]:
            s = m["article"].get("source_short")
            if s and s not in seen:
                seen.add(s)
                also.append(s)
        a["also_sources"] = also
        # Every URL in this cluster, so that displaying the canonical story also
        # retires the other outlets' versions of it (see save_seen_urls).
        a["cluster_links"] = [m["article"]["link"] for m in members]
        # The other outlets' actual articles, not just their names. A cluster
        # member from a directly-fetchable free outlet can supply both a public
        # link and real body text for a story whose canonical is paywalled —
        # the cheapest fix available, since it costs no extra requests.
        a["cluster_members"] = [
            {
                "link": m["article"].get("link", ""),
                "title": m["article"].get("title", ""),
                "source_name": m["article"].get("source_name", ""),
                "source_short": m["article"].get("source_short", ""),
                "access": m["article"].get("access", "unknown"),
                "full_text": m["article"].get("full_text", ""),
                "summary": m["article"].get("summary", ""),
            }
            for m in members[1:]
        ]
        ranked.append(a)

    ranked.sort(key=lambda x: x["significance"], reverse=True)
    # Report the real cluster count, not the post-cap one. Printing len(ranked)
    # after truncating made the log read as though clustering had produced
    # exactly the cap — three runs in a row "produced" 90 distinct stories.
    distinct = len(ranked)
    ranked = ranked[:MAX_TOTAL_ARTICLES]
    capped = f" (capped to {MAX_TOTAL_ARTICLES})" if distinct > MAX_TOTAL_ARTICLES else ""
    kept_articles = sum(len(m) for m in clusters.values())
    print(f"Enrichment: {len(enriched)} scored -> {len(dropped_titles)} dropped (non-news), "
          f"{kept_articles} kept -> {distinct} distinct stories after clustering{capped}.")
    for t in dropped_titles[:25]:
        print(f"  DROPPED(keep=false) {t[:90]!r}")
    return lead, ranked


# ── Stage 2: long-form summaries ─────────────────────────────────────────────
# Run over the display set only (~15 stories), never the full pool. Writing
# 4–5 sentences for all ~90 ranked stories would triple output tokens and
# re-create the truncation that shipped a one-story digest on 2026-09-06.

_ELABORATE_SCHEMA = {
    "type": "object",
    "properties": {
        "lead": {"type": "string"},
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "summary_long": {"type": "string"},
                    "alternate_ok": {"type": "boolean"},
                },
                "required": ["id", "summary_long", "alternate_ok"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["lead", "articles"],
    "additionalProperties": False,
}

_ELABORATE_SYSTEM = """You are the editor of a commercial real estate (CRE) daily \
news digest read by institutional investors, brokers, and lenders. These are the \
stories selected for today's edition. For each one, write the summary that appears \
in the email.

The reader should be able to finish your summary and understand the story without \
opening the link. Many of these articles sit behind paywalls they cannot read, so \
your summary is often the only version they get.

For each article write "summary_long":

- Normally 4–5 sentences. Lead with what happened, then the specifics that matter \
to a CRE professional — dollar amounts, parties, asset type, location, square \
footage, cap rates, timing — then why it matters for the market.
- Write ONLY from the SOURCE TEXT provided. Do not add background, context, \
figures, or consequences that are not in that text. You have no other knowledge \
of this story, and a confident invented detail is worse than a short summary.
- When an article is marked [THIN SOURCE TEXT], you have only a headline and \
perhaps one line. Write 1–2 sentences covering just what that supports, and STOP. \
Do not pad to reach a length. A short accurate summary is a success, not a failure.
- Plain declarative prose. No hype, no "the article discusses", no "this \
development underscores", no closing editorial flourish.
- Never begin with the outlet's name.

Some articles include a [CANDIDATE ALTERNATE SOURCE]. The reader cannot open the \
original, so we want to link them to this other outlet's coverage instead — but \
only if it genuinely reports the SAME underlying event.

For each article set "alternate_ok":
- true only when the candidate covers the same specific event as the headline: \
the same deal, same parties, same property, same announcement.
- false when it merely shares a topic, covers a different transaction by the same \
firm, or is a roundup that happens to mention it. A keyword search produced these, \
so topical near-misses are common and sending the reader to the wrong article is \
worse than sending them to a paywall.
- false when no candidate is shown. Default to false whenever you are unsure.

Also write a "lead": a 2–3 sentence editor's brief on the day's most important CRE \
themes, referencing the specific stories below. Punchy and concrete.

Return every input article id exactly once."""


def _build_elaborate_input(stories):
    lines = []
    for i, a in enumerate(stories):
        src = a.get("source_short", "?")
        date = a.get("pub_date") or "no date"
        sector = a.get("sector", "?")
        lines.append(f"\n[{i}] ({src}, {date}, {sector}) {a['title']}")
        text = (a.get("source_text") or "").strip()
        if a.get("text_thin") or not text:
            lines.append(f"    [THIN SOURCE TEXT] {text or '(headline only)'}")
        else:
            lines.append(f"    SOURCE TEXT: {text}")
        alt = a.get("public_alt")
        if alt and not a.get("alt_confirmed"):
            blurb = (alt.get("summary") or "")[:200]
            lines.append(f"    [CANDIDATE ALTERNATE SOURCE] ({alt.get('source_name','?')}) "
                         f"{alt.get('title','')}")
            if blurb:
                lines.append(f"      {blurb}")
    return "\n".join(lines)


def elaborate(stories):
    """Attach ``summary_long`` to each story. Returns a refreshed lead or None.

    Failure is non-fatal by design: the stories keep their short triage
    summaries and the digest still sends, just less deeply.
    """
    if not stories:
        return None

    user = ("Here are today's selected CRE stories. Write the email summary for "
            "every one.\n" + _build_elaborate_input(stories))
    data = _call_with_retry(user, _ELABORATE_SYSTEM, _ELABORATE_SCHEMA, len(stories),
                            label="Long-form summaries", max_tokens=16000)
    if data is None:
        print("Long-form summaries unavailable; keeping short triage summaries.",
              file=sys.stderr)
        return None

    written = 0
    for item in data.get("articles") or []:
        idx = item.get("id")
        if not isinstance(idx, int) or not 0 <= idx < len(stories):
            continue
        story = stories[idx]
        text = (item.get("summary_long") or "").strip()
        if text:
            story["summary"] = text
            written += 1
        # Only meaningful for unconfirmed (search-found) candidates; cluster
        # alternates were applied earlier and carry alt_confirmed already.
        if story.get("public_alt") and not story.get("alt_confirmed"):
            story["alt_confirmed"] = bool(item.get("alternate_ok"))

    thin = sum(1 for s in stories if s.get("text_thin"))
    print(f"Long-form summaries: {written}/{len(stories)} written "
          f"({thin} from thin source text).")
    return (data.get("lead") or "").strip() or None
