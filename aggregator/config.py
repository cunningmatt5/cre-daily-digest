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
    # NOTE: the Wall Street Journal feed was removed 2026-09-19. Dow Jones'
    # `latestnewsrealestate` is a *residential* feed: a sample of 10 returned
    # "House of the Week", "$50 Million Four Seasons", "The New Rules for
    # Selling Your Home" and similar. Three survived the filters and the model
    # then discarded all three as non-CRE, so a tier-weight-30 source was
    # contributing nothing but tokens.
    # Two CRE-scoped `site:wsj.com` replacements were tested and both returned
    # off-topic results (industrial-production statistics, the Lakers sale,
    # Hyrox) — Google's site: matching is too loose for a publisher this broad.
    # WSJ's actual CRE stories still reach the digest through the wire queries
    # below, correctly classified paywalled; what is lost is the residential
    # noise, not the coverage.
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
    # NOTE: CBRE Research and JLL Research were removed 2026-09-19. Their
    # listing AND article pages publish no date in any form — no <time>, no
    # article:published_time, no JSON-LD datePublished — so every item they
    # produced was (correctly) discarded by the no-date filter. They had been
    # contributing exactly zero stories. Google News `site:` proxies for both
    # return job postings and property listings rather than research, so there
    # is no dated substitute. Both firms' newsworthy activity is still captured
    # by the "CRE Major Players" discovery query below, which names them.
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
        # The /national/feed/ endpoint went dead (returns 0 entries, silently).
        # Google News surfaces therealdeal.com articles with real publish dates.
        "url": gnews("site:therealdeal.com", days=2),
        "method": "rss",
        "tier_weight": 18,
        "color": ROYAL,
    },
    {
        "name": "Trepp",
        "short": "Trepp",
        # The TreppTalk page declares this feed in its own <link rel="alternate">;
        # scraping the HTML yielded no dates, so every item was being filtered out.
        "url": "https://www.trepp.com/trepptalk/rss.xml",
        "method": "rss",
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
    # NOTE: Marcus & Millichap removed 2026-09-19 — same undated-source problem
    # as CBRE/JLL above, and its listing page yielded only a nav link anyway.
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
    # NOTE: NMHC removed 2026-09-19 — undated, no feed, and a `site:nmhc.org`
    # Google News proxy returns nothing at all. Multifamily coverage is carried
    # by CRE Daily Multifamily and the sector discovery query.
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
    # ── Added 2026-09-19 after a source audit ───────────────────────────
    # Only 6 of the previous 22 sources yielded article text: 11 were Google
    # News proxies (thin by nature) and several direct feeds ship teasers only.
    # Every source below was measured first for publish dates, freshness,
    # `content:encoded` richness and body-fetchability, and rejected if it
    # failed any of them. They are all free, directly-fetchable trade press,
    # chosen to deepen the text supply rather than just add headline volume.
    {
        "name": "REBusinessOnline",
        "short": "REBusiness",
        # France Media's regional deal wire — highest fresh-article volume of
        # every candidate tested, spanning all sectors.
        "url": "https://rebusinessonline.com/feed/",
        "method": "rss",
        "tier_weight": 16,
        "color": ROYAL,
    },
    {
        "name": "Scotsman Guide",
        "short": "Scotsman",
        # CRE lending and finance. Richest feed text of any candidate (~3.1k
        # chars of content:encoded per item).
        "url": "https://www.scotsmanguide.com/feed/",
        "method": "rss",
        "tier_weight": 15,
        "color": ROYAL,
    },
    {
        "name": "Propmodo",
        "short": "Propmodo",
        # CRE strategy and technology; long-form, ~3.9k chars per item.
        "url": "https://propmodo.com/feed/",
        "method": "rss",
        "tier_weight": 14,
        "color": ROYAL,
    },
    {
        "name": "Hotel Business",
        "short": "HotelBiz",
        "url": "https://hotelbusiness.com/feed/",
        "method": "rss",
        "tier_weight": 10,
        "color": GREEN,
    },
    {
        "name": "Yield PRO",
        "short": "YieldPRO",
        "url": "https://yieldpro.com/feed/",
        "method": "rss",
        "tier_weight": 10,
        "color": GREEN,
    },
    {
        "name": "Senior Housing News",
        "short": "SHN",
        # Healthcare & Life Science was the thinnest-covered sector; this feed
        # also carries the most text per item of anything tested (~6.2k chars).
        "url": "https://seniorhousingnews.com/feed/",
        "method": "rss",
        "tier_weight": 10,
        "color": GREEN,
    },
    {
        "name": "Inside Self-Storage",
        "short": "ISS",
        # Self storage had no coverage at all; stories land under "Other".
        "url": "https://www.insideselfstorage.com/rss.xml",
        "method": "rss",
        "tier_weight": 9,
        "color": GREEN,
    },
    {
        "name": "Construction Dive",
        "short": "ConstrDive",
        "url": "https://www.constructiondive.com/feeds/news/",
        "method": "rss",
        "tier_weight": 10,
        "color": GREEN,
    },
    {
        "name": "Retail Dive",
        "short": "RetailDive",
        # Retailer bankruptcies and store-fleet moves drive retail CRE.
        "url": "https://www.retaildive.com/feeds/news/",
        "method": "rss",
        "tier_weight": 9,
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
# Ceiling on distinct stories carried out of the ranking stage. Applied AFTER
# clustering, so it costs nothing to raise — the summarizer only ever sees the
# top DISPLAY_MAX_STORIES, and Best of the Rest draws from what's left.
#
# It was 90, which bound on most runs (114, 104 and 119 clusters were all
# truncated to exactly 90) and quietly starved Best of the Rest — one run
# filled only 17 of its 20 slots because the pool had been cut upstream. Raised
# to a level that shouldn't bind in normal operation, kept as a sanity guard
# against a runaway clustering result rather than removed.
MAX_TOTAL_ARTICLES = 150
# Display cap per sector in the email (wide capture, curated display).
MAX_PER_SECTOR = 6
# Only display stories at/above this LLM significance (0–100). Keeps the email
# focused on critical news — big deals, major firms, market-moving events —
# and filters trivia (e.g. a celebrity buying a house). Tunable via env.
DISPLAY_MIN_SIGNIFICANCE = int(os.environ.get("DIGEST_MIN_SIG", "50"))
# Safety net: if the floor leaves fewer than this many stories (e.g. a quiet
# news day or a compressed score distribution), show the top N by significance
# instead, so the digest is never near-empty.
DISPLAY_MIN_STORIES = int(os.environ.get("DIGEST_MIN_STORIES", "12"))
# Hard cap on how many stories the email shows. With 4–5 sentence summaries the
# email is roughly 3x longer per story, so breadth has to give way to depth —
# the goal is a brief you read end to end without clicking. This is also a more
# predictable control than the significance floor, which was retuned three times
# (60→55→50) without settling: the floor stays as a quality gate, the count
# decides length.
DISPLAY_MAX_STORIES = int(os.environ.get("DIGEST_MAX_STORIES", "20"))
# "Best of the Rest": stories that cleared the significance floor but lost the
# top-N cut. Listed as bare headline + link at the foot of the email — no
# summary, no sector grouping — so the net is wider without making the digest
# longer to read. They cost nothing extra to produce: no body fetch, and they
# are not sent to the long-form summarizer.
REST_MAX_STORIES = int(os.environ.get("DIGEST_REST_STORIES", "20"))
SUMMARY_MAX_CHARS = 280
# How much article body to hand the summarizer. ~2.5k chars is far more than
# 4–5 sentences needs, and keeps the whole elaborate() call near 15k tokens.
FULL_TEXT_MAX_CHARS = 2500
# Below this, a story has too little source material to summarize at length;
# the model is told to write fewer sentences rather than invent detail.
THIN_TEXT_CHARS = 400
