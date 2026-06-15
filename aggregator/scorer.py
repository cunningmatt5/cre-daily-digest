"""Deterministic fallback ranker.

Used only when the Claude enrichment stage is unavailable. It keyword-scores
headlines, boosts recent and cross-source-corroborated stories, collapses
near-duplicate titles, and assigns a coarse sector — so the email looks the same
whether or not the LLM ran (just without the editor's lead and crisp summaries).
"""

import re
from datetime import datetime

from .config import MAX_TOTAL_ARTICLES, SECTORS

# Each tuple: (regex pattern, point value)
# Checked against lowercase headline + summary text.
# Higher points = stronger signal of a high-engagement story.
_SIGNALS = [
    # ── Major institutional investors / private equity ──────────────────
    (r"\bblackstone\b", 30),
    (r"\bbrookfield\b", 28),
    (r"\bkkr\b", 25),
    (r"\bapollo\b", 22),
    (r"\bstarwood\b", 22),
    (r"\bares\b", 20),
    (r"\bcarlyle\b", 20),
    (r"\bcerberus\b", 18),
    (r"\bnuveen\b", 18),
    (r"\bpgim\b", 18),
    # ── Major REITs ──────────────────────────────────────────────────────
    (r"\bprologis\b", 25),
    (r"\bsimon property\b", 25),
    (r"\brealty income\b", 22),
    (r"\bvornado\b", 22),
    (r"\bboston properties\b", 22),
    (r"\bsl green\b", 22),
    (r"\bequity residential\b", 20),
    (r"\bavalon\s?bay\b", 20),
    (r"\bpublic storage\b", 20),
    (r"\bextra space\b", 18),
    (r"\bwelltower\b", 18),
    (r"\bventas\b", 18),
    (r"\bamerican tower\b", 20),
    (r"\bcrown castle\b", 20),
    (r"\biron mountain\b", 16),
    # ── Major brokers / servicers ────────────────────────────────────────
    (r"\bcbre\b", 20),
    (r"\bjll\b", 20),
    (r"\bcushman\b", 18),
    (r"\bnewmark\b", 16),
    (r"\bmarcus.{1,4}millichap\b", 14),
    (r"\beastdil\b", 14),
    # ── Deal size signals ────────────────────────────────────────────────
    (r"\b\d+(\.\d+)?\s*billion\b", 30),
    (r"\b[5-9]\d{2}\s*million\b", 18),   # $500M+
    (r"\b[1-4]\d{2}\s*million\b", 10),   # $100–499M
    # ── Transaction / corporate events ──────────────────────────────────
    (r"\bacquisition\b", 18),
    (r"\bmerger\b", 18),
    (r"\bjoint venture\b", 14),
    (r"\brecapitaliz\w+\b", 14),
    (r"\brefinanc\w+\b", 12),
    (r"\bipo\b", 20),
    (r"\bspin.?off\b", 16),
    # ── Distress / credit signals ────────────────────────────────────────
    (r"\bbankruptcy\b", 25),
    (r"\bdefault\b", 22),
    (r"\bforeclosure\b", 22),
    (r"\bdistress\w*\b", 18),
    (r"\bdelinquen\w+\b", 16),
    (r"\bspecial servic\w+\b", 16),
    (r"\bcmbs\b", 14),
    # ── Macro / policy ───────────────────────────────────────────────────
    (r"\bfederal reserve\b", 22),
    (r"\binterest rate\b", 18),
    (r"\brate cut\b", 18),
    (r"\brate hike\b", 18),
    (r"\bcap rate\b", 14),
    (r"\brecession\b", 20),
    (r"\binflation\b", 16),
    (r"\btariff\b", 16),
    # ── High-profile property sectors ───────────────────────────────────
    (r"\bdata center\b", 16),
    (r"\blife science\b", 14),
    (r"\boffice.{1,20}(vacant|conversion|distress)\b", 14),
    # ── Major markets ────────────────────────────────────────────────────
    (r"\bmanhattan\b", 10),
    (r"\bnew york\b", 8),
    (r"\blos angeles\b", 8),
    (r"\bchicago\b", 6),
    (r"\bmiami\b", 6),
    (r"\bsan francisco\b", 8),
]

_COMPILED = [(re.compile(pat, re.I), pts) for pat, pts in _SIGNALS]

# Ordered (sector, keyword-regex) — first property-type match wins, then the
# cross-cutting buckets. Mirrors how the LLM is told to tag.
_SECTOR_RULES = [
    ("Data Centers", r"\bdata center\b|\bhyperscale\b|\bcolocation\b"),
    ("Multifamily", r"\bmultifamily\b|\bapartment\b|\bmulti-?housing\b|\brental housing\b|\bsenior housing\b"),
    ("Hospitality", r"\bhotel\b|\bhospitality\b|\blodging\b|\bresort\b|\bmotel\b"),
    ("Healthcare & Life Science", r"\blife science\b|\blab space\b|\bmedical office\b|\bhealthcare\b|\bbiotech\b"),
    ("Industrial", r"\bindustrial\b|\bwarehouse\b|\blogistics\b|\bfulfillment\b|\bdistribution center\b"),
    ("Retail", r"\bretail\b|\bshopping center\b|\bmall\b|\bstorefront\b|\bgrocery-anchored\b"),
    ("Office", r"\boffice\b|\bcoworking\b|\bworkplace\b"),
    ("Capital Markets", r"\bcmbs\b|\brefinanc\w+\b|\brecapitaliz\w+\b|\bacquisition\b|\bmerger\b|\bipo\b|\bfund\b|\breit\b|\bloan\b|\bdebt\b|\blender\b|\bbillion\b|\bmillion\b"),
    ("Macro & Policy", r"\bfederal reserve\b|\binterest rate\b|\binflation\b|\brecession\b|\btariff\b|\bzoning\b|\blegislation\b|\bregulation\b|\btax\b"),
]
_SECTOR_COMPILED = [(name, re.compile(pat, re.I)) for name, pat in _SECTOR_RULES]

_STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "on", "for", "and", "as", "at", "by",
    "with", "from", "is", "are", "be", "new", "us", "amid", "after", "over",
}


def _headline_score(text: str) -> int:
    total = 0
    for pattern, pts in _COMPILED:
        if pattern.search(text):
            total += pts
    return total


def _classify_sector(text: str) -> str:
    for name, pattern in _SECTOR_COMPILED:
        if pattern.search(text):
            return name
    return "Other"


def _recency_bonus(article) -> int:
    dt = article.get("pub_datetime")
    if not dt:
        return 0
    age_days = (datetime.utcnow() - dt).total_seconds() / 86400
    if age_days <= 1:
        return 20
    if age_days <= 2:
        return 10
    return 0


def _title_tokens(title: str) -> frozenset:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 2)


def _cluster_duplicates(articles):
    """Greedy Jaccard clustering of near-identical titles (O(n^2), n is small)."""
    clusters = []  # each: {"members": [...], "tokens": frozenset}
    for a in articles:
        toks = _title_tokens(a["title"])
        placed = False
        for c in clusters:
            inter = len(toks & c["tokens"])
            union = len(toks | c["tokens"]) or 1
            if inter / union >= 0.6:
                c["members"].append(a)
                placed = True
                break
        if not placed:
            clusters.append({"members": [a], "tokens": toks})
    return clusters


def score_and_sort(articles):
    seen = set()
    unique = []
    for a in articles:
        key = a["link"].rstrip("/")
        if key not in seen and a["title"]:
            seen.add(key)
            unique.append(a)

    clusters = _cluster_duplicates(unique)

    ranked = []
    for c in clusters:
        members = c["members"]
        # Canonical = member with the strongest base headline score, tie-broken
        # by feed position (lower = more featured).
        def base(a):
            text = f"{a['title']} {a.get('summary', '')}"
            return _headline_score(text) - min(a.get("position", 0), 4)
        members.sort(key=base, reverse=True)
        canonical = dict(members[0])

        text = f"{canonical['title']} {canonical.get('summary', '')}"
        position_penalty = min(canonical.get("position", 0), 4) * 8
        corroboration = (len(members) - 1) * 12  # covered by multiple outlets
        canonical["significance"] = (
            _headline_score(text)
            + max(0, 40 - position_penalty)
            + _recency_bonus(canonical)
            + corroboration
        )
        canonical["sector"] = _classify_sector(text)

        also = []
        seen_src = {canonical.get("source_short")}
        for m in members[1:]:
            s = m.get("source_short")
            if s and s not in seen_src:
                seen_src.add(s)
                also.append(s)
        canonical["also_sources"] = also
        ranked.append(canonical)

    ranked.sort(key=lambda x: x["significance"], reverse=True)
    return ranked[:MAX_TOTAL_ARTICLES]


def group_by_sector(articles, max_per_sector=None):
    """Bucket ranked articles into SECTORS order, dropping empty sectors.

    Returns a list of ``(sector_name, [articles])`` preserving SECTORS order,
    with each sector's articles sorted by significance descending. When
    ``max_per_sector`` is set, each sector is truncated to its top N.
    """
    buckets = {s: [] for s in SECTORS}
    for a in articles:
        buckets.setdefault(a.get("sector", "Other"), []).append(a)
    out = []
    for sector in SECTORS:
        items = buckets.get(sector) or []
        if items:
            items.sort(key=lambda x: x.get("significance", 0), reverse=True)
            if max_per_sector:
                items = items[:max_per_sector]
            out.append((sector, items))
    return out
