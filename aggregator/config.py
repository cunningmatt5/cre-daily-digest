import os
from urllib.parse import quote_plus

# ── Tier colors (source chips) ───────────────────────────────────────────────
# Tier 1 = Navy (#0d1b3e) — premium / highest authority
# Tier 2 = Royal Blue (#1e40af) — core trade press + major brokers
# Tier 3 = Forest Green (#1a5c2e) — sector-specific / associations

NAVY  = "#0d1b3e"
ROYAL = "#1e40af"
GREEN = "#1a5c2e"


def gnews(query: str, days=None) -> str:
    """Build a Google News RSS search URL for a query.

    Used as a resilient proxy for sources that block scraping or have no feed
    (the same pattern already proven for Bloomberg). Returns real publisher
    headlines that the rest of the pipeline treats like any other RSS item.

    ``days`` appends Google's ``when:Nd`` operator to restrict results to the
    last N days. Without it, ``site:`` searches rank by relevance and return
    years-old articles that the age filter then discards — so always pass it.
    """
    if days:
        query = f"{query} when:{days}d"
    q = quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


# ── LLM enrichment config ────────────────────────────────────────────────────
# The enrichment stage (clustering, ranking, summarizing, sectoring) runs only
# when an API key is present. Without it the pipeline falls back to the
# deterministic scorer, so the digest always sends.
LLM_MODEL = os.environ.get("DIGEST_MODEL", "claude-opus-4-8")
LLM_EFFORT = os.environ.get("DIGEST_EFFORT", "high")  # low | medium | high | max
LLM_ENABLED = bool(os.environ.get("ANTHROPIC_API_KEY"))

# ── Sectors (display order + band color) ─────────────────────────────────────
# The enrichment stage tags every story with exactly one of these labels.
# Order here is the order sections appear in the email.
SECTORS = [
    "Capital Markets",
    "Office",
    "Multifamily",
    "Industrial",
    "Retail",
    "Hospitality",
    "Data Centers",
    "Healthcare & Life Science",
    "Macro & Policy",
    "Other",
]

# Curated jewel-tone palette — saturated but tonally coordinated so the
# per-sector accents read as a set, not a clash.
SECTOR_COLORS = {
    "Capital Markets":           "#0d1b3e",  # navy
    "Office":                    "#1d4ed8",  # blue
    "Multifamily":               "#047857",  # emerald
    "Industrial":                "#b45309",  # amber
    "Retail":                    "#be123c",  # rose
    "Hospitality":               "#7c3aed",  # violet
    "Data Centers":              "#0e7490",  # cyan
    "Healthcare & Life Science": "#0f766e",  # teal
    "Macro & Policy":            "#475569",  # slate
    "Other":                     "#64748b",  # gray
}

SOURCES = [
    # ── Tier 1 ──────────────────────────────────────────────────────────
    {
        "name": "Wall Street Journal",
        "short": "WSJ",
        # Official Dow Jones RSS — confirmed working (35 items)
        "url": "https://feeds.content.dowjones.io/public/rss/latestnewsrealestate",
        "method": "rss",
        "tier_weight": 30,
        "color": NAVY,
        "paywalled": True,
    },
    {
        "name": "CoStar",
        "short": "CoStar",
        # Site is login-walled to scrape; Google News surfaces costar.com articles
        "url": gnews("site:costar.com", days=2),
        "method": "rss",
        "tier_weight": 30,
        "color": NAVY,
        "paywalled": True,
    },
    {
        "name": "Bloomberg Real Estate",
        "short": "Bloomberg",
        # Bloomberg disabled native RSS; Google News RSS surfaces bloomberg.com CRE articles
        "url": gnews('site:bloomberg.com "real estate"', days=2),
        "method": "rss",
        "tier_weight": 28,
        "color": NAVY,
        "paywalled": True,
    },
    {
        "name": "Green Street",
        "short": "Green St",
        # Fully paywalled to scrape; Google News surfaces greenstreetnews.com headlines
        "url": gnews("site:greenstreetnews.com", days=3),
        "method": "rss",
        "tier_weight": 28,
        "color": NAVY,
        "paywalled": True,
    },
    {
        "name": "CBRE Research",
        "short": "CBRE",
        "url": "https://www.cbre.com/insights/articles",
        "method": "scrape",
        "tier_weight": 26,
        "color": NAVY,
    },
    {
        "name": "JLL Research",
        "short": "JLL",
        "url": "https://www.jll.com/en/trends-and-insights/research",
        "method": "scrape",
        "tier_weight": 26,
        "color": NAVY,
    },
    # ── Tier 2 ──────────────────────────────────────────────────────────
    {
        "name": "GlobeStreet",
        "short": "GlobeSt",
        # RSS returns 403 and homepage scrape is brittle; Google News proxy
        "url": gnews("site:globest.com", days=2),
        "method": "rss",
        "tier_weight": 20,
        "color": ROYAL,
    },
    {
        "name": "Commercial Observer",
        "short": "Comm Obs",
        "url": "https://commercialobserver.com/feed/",
        "method": "rss",
        "tier_weight": 20,
        "color": ROYAL,
    },
    {
        "name": "Bisnow",
        "short": "Bisnow",
        "url": "https://www.bisnow.com/rss",
        "method": "rss",
        "tier_weight": 18,
        "color": ROYAL,
    },
    {
        "name": "The Real Deal",
        "short": "Real Deal",
        # National feed confirmed working (10 items)
        "url": "https://therealdeal.com/national/feed/",
        "method": "rss",
        "tier_weight": 18,
        "color": ROYAL,
    },
    {
        "name": "Trepp",
        "short": "Trepp",
        "url": "https://www.trepp.com/trepptalk",
        "method": "scrape",
        "tier_weight": 18,
        "color": ROYAL,
    },
    {
        "name": "PERE",
        "short": "PERE",
        "url": gnews("site:perenews.com", days=3),
        "method": "rss",
        "tier_weight": 16,
        "color": ROYAL,
        "paywalled": True,
    },
    {
        "name": "CRE Daily",
        "short": "CRE Daily",
        # /feed/ returns empty; /briefs/feed/ is the active article feed
        "url": "https://www.credaily.com/briefs/feed/",
        "method": "rss",
        "tier_weight": 15,
        "color": ROYAL,
    },
    {
        "name": "Marcus & Millichap",
        "short": "M&M",
        "url": "https://www.marcusmillichap.com/research",
        "method": "scrape",
        "tier_weight": 14,
        "color": ROYAL,
    },
    # ── Tier 3 ──────────────────────────────────────────────────────────
    {
        "name": "CRE Daily Multifamily",
        "short": "CRE MF",
        "url": "https://www.credaily.com/sectors/multifamily/feed",
        "method": "rss",
        "tier_weight": 12,
        "color": GREEN,
    },
    {
        "name": "Connect CRE",
        "short": "ConnectCRE",
        "url": "https://www.connectcre.com/feed/",
        "method": "rss",
        "tier_weight": 10,
        "color": GREEN,
    },
    {
        "name": "Lodging Magazine",
        "short": "Lodging",
        # Replaces Hotel News Now (absorbed by CoStar in 2021)
        "url": "https://lodgingmagazine.com/feed/",
        "method": "rss",
        "tier_weight": 10,
        "color": GREEN,
    },
    {
        "name": "Shopping Center Business",
        "short": "SCB",
        "url": "https://www.shoppingcenterbusiness.com/feed/",
        "method": "rss",
        "tier_weight": 10,
        "color": GREEN,
    },
    {
        "name": "NMHC",
        "short": "NMHC",
        "url": "https://www.nmhc.org/news/",
        "method": "scrape",
        "tier_weight": 10,
        "color": GREEN,
    },
    {
        "name": "Nareit",
        "short": "Nareit",
        "url": "https://www.reit.com/news/rss.xml",
        "method": "rss",
        "tier_weight": 10,
        "color": GREEN,
    },
    {
        "name": "Data Center Dynamics",
        "short": "DCD",
        # Data-center coverage — a fast-growing CRE sector underrepresented above
        "url": "https://www.datacenterdynamics.com/rss/",
        "method": "rss",
        "tier_weight": 10,
        "color": GREEN,
    },
    # ── Broad discovery (Google News topic queries, time-restricted) ─────
    # The recall engine: these cast a wide, fresh net across ALL outlets —
    # not just the publishers listed above — so relevant CRE news from any
    # source surfaces. The real publisher is read from each item and shown
    # on the chip. Clustering in the enrichment stage collapses overlaps.
    {
        "name": "CRE Headlines",
        "short": "Wire",
        "url": gnews("commercial real estate", days=1),
        "method": "rss",
        "tier_weight": 12,
        "color": GREEN,
    },
    {
        "name": "CRE Deals & Capital",
        "short": "Wire",
        "url": gnews(
            'commercial real estate (acquisition OR "sale" OR portfolio OR '
            'refinancing OR recapitalization OR "joint venture" OR fund)',
            days=2,
        ),
        "method": "rss",
        "tier_weight": 12,
        "color": GREEN,
    },
    {
        "name": "CRE Distress & Credit",
        "short": "Wire",
        "url": gnews(
            "commercial real estate (distress OR default OR foreclosure OR "
            "CMBS OR delinquency OR bankruptcy OR workout)",
            days=2,
        ),
        "method": "rss",
        "tier_weight": 12,
        "color": GREEN,
    },
    {
        "name": "CRE by Sector",
        "short": "Wire",
        "url": gnews(
            '(office OR multifamily OR apartment OR industrial OR warehouse OR '
            'retail OR "data center" OR hotel OR "life science") "real estate" '
            "(lease OR sale OR development OR financing OR acquisition)",
            days=2,
        ),
        "method": "rss",
        "tier_weight": 12,
        "color": GREEN,
    },
    {
        "name": "CRE Major Players",
        "short": "Wire",
        "url": gnews(
            "(Blackstone OR Brookfield OR KKR OR Starwood OR Prologis OR CBRE OR "
            'JLL OR "Simon Property" OR Related OR Hines) real estate',
            days=2,
        ),
        "method": "rss",
        "tier_weight": 12,
        "color": GREEN,
    },
]

# Pull more per source (RSS feeds are freshest-first, so a higher cap = more
# of today's news, not stale backfill).
MAX_ARTICLES_PER_SOURCE = 10
# Candidate-pool cap fed to the enrichment stage (post-filter).
MAX_TOTAL_ARTICLES = 90
# Display cap per sector in the email (wide capture, curated display).
MAX_PER_SECTOR = 6
# Only display stories at/above this LLM significance (0–100). Keeps the email
# focused on critical news — big deals, major firms, market-moving events —
# and filters trivia (e.g. a celebrity buying a house). Tunable via env.
DISPLAY_MIN_SIGNIFICANCE = int(os.environ.get("DIGEST_MIN_SIG", "55"))
# Safety net: if the floor leaves fewer than this many stories (e.g. a quiet
# news day or a compressed score distribution), show the top N by significance
# instead, so the digest is never near-empty.
DISPLAY_MIN_STORIES = int(os.environ.get("DIGEST_MIN_STORIES", "12"))
SUMMARY_MAX_CHARS = 280
