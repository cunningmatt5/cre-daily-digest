from datetime import datetime, timezone

from .config import SECTOR_COLORS

# ── Palette (navy + teal two-tone, with curated per-sector accents) ──────────
NAVY  = "#0d1b3e"   # masthead base, Capital Markets
TEAL  = "#0f766e"   # primary accent: hero badges, links, brand
AMBER = "#b45309"   # "Top story" featured pill
INK   = "#111827"   # headlines
BODY  = "#374151"   # summary text
META  = "#6b7280"   # source / date / counts
RULE  = "#e5e7eb"   # hairline dividers
SOFT  = "#eef1f4"   # row dividers
PAGE  = "#eef1f6"   # page background

FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,"
        "sans-serif")


def _esc(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _sector_color(sector):
    return SECTOR_COLORS.get(sector, META)


def _meta_line(article, sector=None):
    """Render `SECTOR · WSJ · also Real Deal +2 · 🔒 sub · Jun 14` as text."""
    parts = []
    if sector:
        parts.append(
            f'<span style="color:{_sector_color(sector)};font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.6px;">{_esc(sector)}</span>'
        )
    parts.append(
        f'<span style="color:{INK};font-weight:700;">{_esc(article["source_short"])}</span>'
    )
    also = article.get("also_sources") or []
    if also:
        names = ", ".join(_esc(s) for s in also[:2])
        more = f" +{len(also) - 2}" if len(also) > 2 else ""
        parts.append(f'<span style="color:{META};">also {names}{more}</span>')
    if article.get("paywalled"):
        parts.append(f'<span style="color:{META};">&#128274; sub</span>')
    if article.get("pub_date"):
        parts.append(f'<span style="color:{META};">{_esc(article["pub_date"])}</span>')
    sep = '<span style="color:#c8cdd4;"> &nbsp;&middot;&nbsp; </span>'
    return (
        f'<div style="font-size:12px;font-family:{FONT};line-height:1.45;'
        f'margin-top:4px;">{sep.join(parts)}</div>'
    )


def _top_pill():
    return (
        f'<span style="display:inline-block;color:#ffffff;background:{AMBER};'
        f'font-size:9.5px;font-family:{FONT};font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.7px;border-radius:3px;padding:1px 6px;margin-right:8px;'
        f'vertical-align:2px;">&#9733; Top</span>'
    )


# ── Hero: Top Stories ────────────────────────────────────────────────────────
def _hero_item(article, rank, last):
    title = _esc(article["title"])
    link = article["link"]
    border = "" if last else f"border-bottom:1px solid {SOFT};"
    return f"""<tr>
      <td style="width:34px;padding:11px 0;vertical-align:top;{border}">
        <div style="width:23px;height:23px;background:{TEAL};border-radius:50%;
          color:#ffffff;font-size:12px;font-weight:800;text-align:center;
          line-height:23px;font-family:{FONT};">{rank}</div>
      </td>
      <td style="padding:11px 0;vertical-align:top;{border}">
        <a href="{link}" style="color:{INK};text-decoration:none;font-size:14.5px;
          font-weight:700;line-height:1.35;font-family:{FONT};">{title}</a>
        {_meta_line(article, sector=article.get("sector"))}
      </td>
    </tr>"""


def _hero(top_stories):
    if not top_stories:
        return ""
    n = len(top_stories)
    rows = "".join(_hero_item(a, i + 1, i == n - 1) for i, a in enumerate(top_stories))
    return f"""<tr><td style="padding:22px 32px 4px;">
      <div style="color:{TEAL};font-size:12px;font-weight:700;font-family:{FONT};
        text-transform:uppercase;letter-spacing:1.8px;padding-bottom:4px;
        border-bottom:2px solid {TEAL};">
        Top Stories
      </div>
      <table width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table>
    </td></tr>"""


# ── Sector sections ──────────────────────────────────────────────────────────
def _story_row(article, color, first, is_top):
    title = _esc(article["title"])
    summary = _esc(article.get("summary", ""))
    link = article["link"]
    border = "" if first else f"border-top:1px solid {SOFT};"
    tag = _top_pill() if is_top else ""
    summary_html = (
        f'<div style="margin-top:5px;color:{BODY};font-size:13.5px;'
        f'line-height:1.55;font-family:{FONT};">{summary}</div>'
        if summary else ""
    )
    return f"""<tr><td style="padding:13px 0 13px 14px;border-left:3px solid {color};{border}">
      <div>
        {tag}<a href="{link}" style="color:{INK};text-decoration:none;font-size:15px;
          font-weight:700;line-height:1.4;font-family:{FONT};">{title}</a>
      </div>
      {_meta_line(article)}
      {summary_html}
    </td></tr>"""


def _sector_section(sector, items, top_links):
    color = _sector_color(sector)
    rows = "".join(
        _story_row(a, color, i == 0, a.get("link") in top_links)
        for i, a in enumerate(items)
    )
    return f"""<tr><td style="padding:10px 32px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr><td style="padding:18px 0 8px;border-bottom:2px solid {color};">
          <span style="display:inline-block;width:9px;height:9px;background:{color};
            border-radius:2px;margin-right:8px;vertical-align:1px;"></span>
          <span style="color:{color};font-size:13px;font-weight:700;font-family:{FONT};
            text-transform:uppercase;letter-spacing:1.4px;">{_esc(sector)}</span>
          <span style="color:#aeb6c0;font-size:12px;font-family:{FONT};
            margin-left:7px;">{len(items)}</span>
        </td></tr>
      </table>
      <table width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table>
    </td></tr>"""


def _lead_block(lead):
    if not lead:
        return ""
    return f"""<tr><td style="padding:20px 32px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
        style="background:#f0f7f6;border-left:4px solid {TEAL};border-radius:0 6px 6px 0;">
        <tr><td style="padding:15px 18px;">
          <div style="color:{TEAL};font-size:11px;font-family:{FONT};font-weight:700;
            text-transform:uppercase;letter-spacing:1.6px;margin-bottom:6px;">
            Today&#39;s Brief
          </div>
          <div style="color:{INK};font-size:14.5px;line-height:1.62;font-family:{FONT};">
            {_esc(lead)}
          </div>
        </td></tr>
      </table>
    </td></tr>"""


def build_html_email(today, sections, lead=None, top_stories=None, count=None):
    """Render the digest.

    ``sections``      list of ``(sector_name, [articles])``.
    ``lead``          optional LLM editor's brief (omitted in fallback mode).
    ``top_stories``   optional ranked list for the hero (omitted in fallback).
    """
    date_str = f"{today:%A, %B} {today.day}, {today.year}"
    now = datetime.now(timezone.utc)
    timestamp = f"{now.strftime('%I').lstrip('0')}:{now:%M %p} UTC"
    if count is None:
        count = sum(len(items) for _, items in sections)
    tagline = ("Clustered &amp; ranked by Claude" if lead
               else "Ranked by deal size &amp; cross-source corroboration")
    top_links = {a.get("link") for a in (top_stories or [])}
    gradient = f"background-color:{NAVY};background-image:linear-gradient(120deg,{NAVY} 0%,{TEAL} 135%);"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <title>CRE Daily Digest — {date_str}</title>
</head>
<body style="margin:0;padding:24px 12px;background-color:{PAGE};font-family:{FONT};">
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr><td align="center">
      <table cellpadding="0" cellspacing="0" border="0"
        style="width:100%;max-width:640px;background:#ffffff;border-radius:12px;
        overflow:hidden;box-shadow:0 1px 3px rgba(13,27,62,0.12);">

        <!-- Masthead (navy→teal gradient) -->
        <tr><td style="{gradient}padding:22px 32px 20px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td style="vertical-align:bottom;">
                <span style="color:#ffffff;font-size:22px;font-weight:800;font-family:{FONT};
                  letter-spacing:0.6px;">CRE</span><span style="color:#7fe3d4;font-size:22px;
                  font-weight:800;font-family:{FONT};letter-spacing:0.6px;"> DAILY</span>
              </td>
              <td align="right" style="vertical-align:bottom;">
                <span style="color:#c8d6e8;font-size:13px;font-family:{FONT};">{date_str}</span>
              </td>
            </tr>
          </table>
          <div style="margin-top:9px;color:#9fe0d4;font-size:10.5px;font-family:{FONT};
            text-transform:uppercase;letter-spacing:1.5px;font-weight:600;">
            {count} stories &nbsp;&middot;&nbsp; {tagline}
          </div>
        </td></tr>

        {_lead_block(lead)}
        {_hero(top_stories)}
        {"".join(_sector_section(s, items, top_links) for s, items in sections)}

        <!-- Footer -->
        <tr><td style="padding:24px 32px 26px;">
          <div style="border-top:1px solid {RULE};padding-top:14px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td><span style="color:{META};font-size:11.5px;font-family:{FONT};">
                  CRE Daily Digest</span></td>
                <td align="right"><span style="color:{META};font-size:11.5px;font-family:{FONT};">
                  Generated {timestamp}</span></td>
              </tr>
            </table>
          </div>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
