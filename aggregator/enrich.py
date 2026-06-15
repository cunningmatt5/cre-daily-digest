"""Claude-powered enrichment: cluster, rank, summarize, and sector-tag articles.

A single structured-output call replaces the regex scorer's keyword math with
actual editorial judgment. If anything goes wrong (no API key, network error,
malformed response) ``enrich`` returns ``None`` and the caller falls back to the
deterministic scorer, so the digest always sends.
"""

import json
import sys

from .config import LLM_MODEL, LLM_EFFORT, SECTORS, MAX_TOTAL_ARTICLES

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

- keep: false for anything that is not a substantive CRE news story — pure \
marketing/sponsored content, generic "best places to work" listicles, thin SEO \
filler, personnel-move briefs of no market significance, or items unrelated to \
commercial real estate. Keep genuine reporting on deals, financings, distress, \
development, leasing, capital markets, and CRE policy.

- significance: 0–100, how much an institutional CRE audience would care. Reward \
large deal size, marquee institutions (Blackstone, Brookfield, KKR, major REITs \
and brokers), M&A/IPOs/recapitalizations, distress/defaults/foreclosures, and \
market-moving macro or policy (Fed, rates, major legislation). Routine local \
deals and incremental research notes score low.

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


def _call_model(articles):
    import anthropic

    client = anthropic.Anthropic()
    user = (
        "Here are today's candidate CRE articles. Process every one per your "
        "instructions.\n\n" + _build_input(articles)
    )
    with client.messages.stream(
        model=LLM_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": LLM_EFFORT, "format": {"type": "json_schema", "schema": _SCHEMA}},
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = stream.get_final_message()

    text = next((b.text for b in message.content if b.type == "text"), "")
    return json.loads(text)


def enrich(articles):
    """Return ``(lead, ranked_articles)`` or ``None`` to signal fallback.

    ``ranked_articles`` are canonical (deduped) article dicts, each augmented
    with ``significance``, ``sector``, an LLM ``summary``, and ``also_sources``
    (the short names of other outlets that covered the same story). Sorted by
    significance, descending, capped at ``MAX_TOTAL_ARTICLES``.
    """
    if not articles:
        return None

    try:
        data = _call_model(articles)
    except Exception as exc:  # noqa: BLE001 — any failure degrades to fallback
        print(f"Enrichment unavailable ({type(exc).__name__}: {exc}); "
              f"falling back to deterministic scorer.", file=sys.stderr)
        return None

    lead = (data.get("lead") or "").strip()
    enriched = data.get("articles") or []

    # Group kept articles by cluster.
    clusters = {}
    for e in enriched:
        if not e.get("keep"):
            continue
        idx = e.get("id")
        if not isinstance(idx, int) or not (0 <= idx < len(articles)):
            continue
        sector = e.get("sector") if e.get("sector") in SECTORS else "Other"
        item = {
            "article": articles[idx],
            "significance": int(e.get("significance", 0)),
            "sector": sector,
            "summary": (e.get("summary") or "").strip(),
        }
        clusters.setdefault(e.get("cluster"), []).append(item)

    if not clusters:
        print("Enrichment kept no articles; falling back.", file=sys.stderr)
        return None

    ranked = []
    for members in clusters.values():
        members.sort(key=lambda m: m["significance"], reverse=True)
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
        ranked.append(a)

    ranked.sort(key=lambda x: x["significance"], reverse=True)
    ranked = ranked[:MAX_TOTAL_ARTICLES]
    print(f"Enrichment: {len(enriched)} scored -> {len(ranked)} stories after clustering.")
    return lead, ranked
