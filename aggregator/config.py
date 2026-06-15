import os
from urllib.parse import quote_plus

# ── Tier colors (source chips) ───────────────────────────────────────────────
# Tier 1 = Navy (#0d1b3e) — premium / highest authority
# Tier 2 = Royal Blue (#1e40af) — core trade press + major brokers
# Tier 3 = Forest Green (#1a5c2e) — sector-specific / associations

NAVY  = "#0d1b3e"
ROYAL = "#1e40af"
GREEN = "#1a5c2e"


def gnews(query: str) -> str:
    """Build a Google News RSS search URL for a query.

    Used as a resilient proxy for sources that block scraping or have no feed
    (the same pattern already proven for Bloomberg). Returns real publisher
    headlines that the rest of the pipeline treats like any other RSS item.
    """
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

SECTOR_COLORS = {
    "Capital Markets":           "#0d1b3e",
    "Office":                    "#1e3a8a",
    "Multifamily":               "#1a5c2e",
    "Industrial":                "#92400e",
    "Retail":                    "#9d174d",
    "Hospitality":               "#7c2d12",
    "Data Centers":              "#3730a3",
    "Healthcare & Life Science": "#0e7490",
    "Macro & Policy":            "#374151",
    "Other":                     "#4b5563",
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
        "url": gnews('site:costar.com "commercial real estate"'),
        "method": "rss",
        "tier_weight": 30,
        "color": NAVY,
        "paywalled": True,
    },
    {
        "name": "Bloomberg Real Estate",
        "short": "Bloomberg",
        # Bloomberg disabled native RSS; Google News RSS surfaces bloomberg.com CRE articles
        "url": gnews('site:bloomberg.com "commercial real estate"'),
        "method": "rss",
        "tier_weight": 28,
        "color": NAVY,
        "paywalled": True,
    },
    {
        "name": "Green Street",
        "short": "Green St",
        # Fully paywalled to scrape; Google News surfaces greenstreetnews.com headlines
        "url": gnews("site:greenstreetnews.com"),
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
        "url": gnews("site:globest.com"),
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
        "url": gnews("site:perenews.com"),
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
]

MAX_ARTICLES_PER_SOURCE = 5
MAX_TOTAL_ARTICLES = 60
SUMMARY_MAX_CHARS = 280
