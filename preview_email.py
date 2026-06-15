"""Render a representative digest to data/preview.html for design review.

Uses static sample data (not live feeds) so every visual feature shows up:
lead brief, Top Stories hero, multiple sectors, cross-source dupes, paywall.
Run:  python preview_email.py   then open data/preview.html
"""
from datetime import date
from pathlib import Path

from aggregator.formatter import build_html_email
from aggregator.scorer import group_by_sector


def a(title, sector, sig, src, date_str, summary, also=None, paywall=False, link="https://example.com/x"):
    return {
        "title": title, "sector": sector, "significance": sig,
        "source_short": src, "pub_date": date_str, "summary": summary,
        "also_sources": also or [], "paywalled": paywall, "link": link,
    }


ARTICLES = [
    a("Blackstone to take Canadian REIT private in $3.2B deal", "Capital Markets", 94,
      "WSJ", "Jun 14", "Blackstone agreed to acquire the diversified REIT at a ~20% premium, "
      "its largest Canadian take-private to date as it leans further into logistics and rentals.",
      also=["Real Deal", "Bisnow", "GlobeSt"], paywall=True),
    a("KKR, Nvidia and a Kuwait fund back $10B AI data center venture", "Data Centers", 88,
      "CRE Daily", "Jun 13", "The consortium will fund hyperscale campuses across the Sun Belt, "
      "underscoring how AI demand is reshaping industrial and power-adjacent real estate.",
      also=["Bisnow"]),
    a("SF office vacancy hits record 37% as conversions stall", "Office", 81,
      "GlobeSt", "Jun 13", "Downtown availability set another high even as the city fast-tracks "
      "office-to-residential conversions that remain financially unworkable at current rents."),
    a("Prologis pays $1.1B for Sun Belt logistics portfolio", "Industrial", 72,
      "Comm Obs", "Jun 14", "The 6.4M sf, 18-asset deal deepens Prologis's last-mile footprint "
      "in Dallas, Atlanta and Phoenix."),
    a("Fed holds rates, signals one cut by year-end", "Macro & Policy", 70,
      "Bloomberg", "Jun 14", "Powell flagged sticky shelter inflation; CRE lenders read the hold "
      "as a green light to reopen acquisition financing in Q3.", paywall=True),
    a("Distressed office loan volume tops $52B, Trepp says", "Capital Markets", 68,
      "Trepp", "Jun 13", "Special-servicing transfers accelerated in May, with office CMBS "
      "delinquencies now at their highest since 2012."),
    a("Sun Belt multifamily rents tick up as supply wave crests", "Multifamily", 55,
      "CRE MF", "Jun 13", "Effective rents rose 0.6% in May as deliveries finally slow across "
      "Austin, Nashville and Phoenix."),
    a("Simon Property reopens redeveloped Phoenix mall anchor", "Retail", 48,
      "SCB", "Jun 12", "The 280k sf redevelopment swaps a former department store for medical, "
      "fitness and dining uses."),
    a("Host Hotels acquires two luxury resorts for $740M", "Hospitality", 60,
      "Lodging", "Jun 13", "The deal expands Host's leisure-driven portfolio as group travel "
      "demand normalizes above 2019 levels."),
    a("Welltower raises 2026 guidance on senior-housing occupancy", "Healthcare & Life Science", 52,
      "Nareit", "Jun 12", "Same-store occupancy climbed for an 11th straight quarter, lifting "
      "the REIT's full-year FFO outlook."),
    a("Brookfield closes $8B opportunistic real estate fund", "Capital Markets", 65,
      "PERE", "Jun 12", "The vehicle will target distressed office and retail recapitalizations "
      "across North America and Europe.", paywall=True),
    a("Amazon signs 1.2M sf lease at New Jersey megawarehouse", "Industrial", 50,
      "Bisnow", "Jun 13", "The build-to-suit signals renewed big-box absorption after two soft years."),
]


def top_n(articles, n=5):
    return sorted(articles, key=lambda x: x["significance"], reverse=True)[:n]


lead = ("Blackstone headlined a busy session with a $3.2B Canadian REIT take-private, while "
        "AI capital kept flooding into data centers via a $10B KKR-Nvidia venture. Office "
        "distress deepened — SF vacancy hit a record and Trepp pegged troubled office loans "
        "above $52B — as the Fed's hold nudged lenders toward a Q3 thaw.")

sections = group_by_sector(ARTICLES)
html = build_html_email(date(2026, 6, 15), sections, lead=lead,
                        top_stories=top_n(ARTICLES), count=len(ARTICLES))

out = Path("data/preview.html")
out.parent.mkdir(exist_ok=True)
out.write_text(html, encoding="utf-8")
print(f"Wrote {out} ({len(html)} bytes) — open it in a browser.")
