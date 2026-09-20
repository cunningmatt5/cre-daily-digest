"""Decide which ranked stories appear in the email, and how.

Extracted verbatim from ``main()``, which had grown past 250 lines with this
logic inline and therefore untestable — the sector-cap backfill in particular
is the kind of code that fails silently. Keeping it pure (no printing, no
network, no config imports) means the selection rules can be asserted directly.

The caller does the logging, using the returned ``stats``.

Four rules apply in order:

1. **Significance floor** — quality gate. If too few stories clear it, fall back
   to the top N so the digest is never near-empty.
2. **Story cap** — length gate. Everything above the floor is ranked; only the
   top N are summarized.
3. **Sector cap** — no single busy sector fills the email. Applied *after* the
   story cap, so it can displace stories; the backfill repairs that.
4. **Best of the Rest** — everything above the floor that lost the cut, as bare
   headlines.
"""

import collections


def _by_significance(stories):
    return sorted(stories, key=lambda x: x.get("significance", 0), reverse=True)


def select_display(ranked, group_by_sector, *, floor, min_stories, max_stories,
                   max_per_sector, rest_max):
    """Return ``(sections, displayed, rest, stats)``.

    ``group_by_sector`` is injected rather than imported so this module stays
    free of pipeline dependencies and the rule can be tested in isolation.

    ``stats`` carries everything the caller needs to log: ``below``, ``cut``,
    ``floor_fallback``, ``cleared_floor``, ``backfilled`` and ``rest_range``.
    """
    stats = {"below": [], "cut": [], "floor_fallback": False,
             "cleared_floor": len(ranked), "backfilled": 0, "rest_range": None}

    display_pool = ranked
    if floor:
        kept = [a for a in ranked if a.get("significance", 0) >= floor]
        below = [a for a in ranked if a.get("significance", 0) < floor]
        stats["cleared_floor"] = len(kept)
        if len(kept) >= min_stories:
            display_pool = kept
            stats["below"] = _by_significance(below)
        else:
            # Too few cleared the floor — a quiet news day or a compressed score
            # distribution. Show the top N regardless so the digest still sends.
            display_pool = ranked[:min_stories]
            stats["floor_fallback"] = True

    # Everything above the floor, ranked. Kept whole: the story cap truncates a
    # copy, and Best of the Rest is drawn from what the cap left behind.
    by_sig = _by_significance(display_pool)
    if len(by_sig) > max_stories:
        stats["cut"] = by_sig[max_stories:]
        display_pool = by_sig[:max_stories]
    else:
        display_pool = by_sig

    sections = group_by_sector(display_pool, max_per_sector=max_per_sector)
    displayed = [a for _, items in sections for a in items]

    # The sector cap runs after the story cap, so a crowded sector can both drop
    # a high scorer and leave the digest short. Top back up from the next-best
    # stories still under their sector's cap, so length is never paid for with
    # importance.
    if len(displayed) < max_stories:
        shown_links = {a["link"] for a in displayed}
        per_sector = collections.Counter(a.get("sector", "Other") for a in displayed)
        backfill = []
        for a in by_sig:
            if len(displayed) + len(backfill) >= max_stories:
                break
            sector = a.get("sector", "Other")
            if a["link"] in shown_links or per_sector[sector] >= max_per_sector:
                continue
            per_sector[sector] += 1
            backfill.append(a)
        if backfill:
            stats["backfilled"] = len(backfill)
            sections = group_by_sector(displayed + backfill,
                                       max_per_sector=max_per_sector)
            displayed = [a for _, items in sections for a in items]

    # Best of the Rest: cleared the floor, lost the cut. Drawn from the full
    # above-floor list, not the truncated pool.
    shown_links = {a["link"] for a in displayed}
    rest = [a for a in by_sig if a["link"] not in shown_links][:rest_max]
    if rest:
        rest_sigs = [a.get("significance", 0) for a in rest]
        stats["rest_range"] = (max(rest_sigs), min(rest_sigs))

    return sections, displayed, rest, stats
