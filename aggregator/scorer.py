import re
from .config import MAX_TOTAL_ARTICLES

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


def _headline_score(text: str) -> int:
    total = 0
    for pattern, pts in _COMPILED:
        if pattern.search(text):
            total += pts
    return total


def score_and_sort(articles):
    seen = set()
    unique = []
    for a in articles:
        key = a["link"].rstrip("/")
        if key not in seen and a["title"]:
            seen.add(key)
            unique.append(a)

    for a in unique:
        text = f"{a['title']} {a.get('summary', '')}"
        # Headline prestige + feed position (top of feed = more featured)
        # Position penalty capped so a strong headline from position 4 still beats
        # a weak headline from position 0.
        position_penalty = min(a["position"], 4) * 8
        a["score"] = _headline_score(text) + max(0, 40 - position_penalty)

    unique.sort(key=lambda x: x["score"], reverse=True)
    return unique[:MAX_TOTAL_ARTICLES]
