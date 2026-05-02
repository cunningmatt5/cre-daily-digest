# Tier 1 = Navy (#0d1b3e) — premium / highest authority
# Tier 2 = Royal Blue (#1e40af) — core trade press + major brokers
# Tier 3 = Forest Green (#1a5c2e) — sector-specific / associations

NAVY  = "#0d1b3e"
ROYAL = "#1e40af"
GREEN = "#1a5c2e"

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
        # Login-walled; scrape returns 0 — kept for reference
        "url": "https://www.costar.com/news",
        "method": "scrape",
        "tier_weight": 30,
        "color": NAVY,
        "paywalled": True,
    },
    {
        "name": "Bloomberg Real Estate",
        "short": "Bloomberg",
        # Bloomberg disabled native RSS; Google News RSS surfaces bloomberg.com CRE articles
        "url": "https://news.google.com/rss/search?q=site:bloomberg.com+%22commercial+real+estate%22&hl=en-US&gl=US&ceid=US:en",
        "method": "rss",
        "tier_weight": 28,
        "color": NAVY,
        "paywalled": True,
    },
    {
        "name": "Green Street",
        "short": "Green St",
        # Fully paywalled — scrape returns 0; kept for reference
        "url": "https://www.greenstreetnews.com/articles",
        "method": "scrape",
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
        # RSS returns 403; scrape homepage instead
        "url": "https://www.globest.com/",
        "method": "scrape",
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
        "url": "https://www.perenews.com/",
        "method": "scrape",
        "tier_weight": 16,
        "color": ROYAL,
        "paywalled": True,
    },
    {
        "name": "National Real Estate Investor",
        "short": "NREI",
        # RSS URL was dead; scrape nreionline.com directly
        "url": "https://www.nreionline.com/",
        "method": "scrape",
        "tier_weight": 16,
        "color": ROYAL,
    },
    {
        "name": "Urban Land Institute",
        "short": "ULI",
        # urbanland.uli.org 403'd; try main ULI news page
        "url": "https://uli.org/news/",
        "method": "scrape",
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
        "name": "Multi-Housing News",
        "short": "MHN",
        # RSS returns 403; scrape homepage instead
        "url": "https://www.multihousingnews.com/",
        "method": "scrape",
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
]

MAX_ARTICLES_PER_SOURCE = 5
MAX_TOTAL_ARTICLES = 60
SUMMARY_MAX_CHARS = 280
