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

# Outlook on Windows renders mail with the Microsoft Word engine, not a browser
# engine. It ignores max-width, drops margins on <div>, prefers the HTML width
# attribute over CSS on cells, and applies its own line spacing unless told not
# to. Left alone it produced a visibly different email for an Outlook reader:
# the column ran the full window width and the text blocks closed up.
#
# MSO_LH makes Word honour a stated line-height instead of substituting its own.
# Spacing that has to survive is expressed as table-cell padding, which Word
# does respect, rather than as a margin on a div, which it frequently discards.
MSO_LH = "mso-line-height-rule:exactly;"
# Kills the extra gutter Word adds either side of a nested table.
MSO_TABLE = "mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;"
CARD_WIDTH = 640


def _esc(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _esc_attr(url):
    """Escape a URL for use inside a double-quoted HTML attribute.

    Links now include search-derived alternates, so a stray quote is no longer
    only a theoretical way to break out of the href.
    """
    return _esc(url).replace('"', "&quot;")


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
    # When the link was swapped to a freely readable outlet, credit whoever
    # actually broke the story rather than silently dropping them.
    original = article.get("original_source")
    if original:
        parts.append(f'<span style="color:{META};">originally {_esc(original)}</span>')
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
    # No margin here: callers place this in its own table cell with padding,
    # because Word drops margins on a div.
    return (
        f'<div style="font-size:12px;font-family:{FONT};{MSO_LH}line-height:1.45;'
        f'">{sep.join(parts)}</div>'
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
    link = _esc_attr(article["link"])
    border = "" if last else f"border-bottom:1px solid {SOFT};"
    # The rank cell carries an HTML width attribute as well as CSS: Word ignores
    # the CSS and collapses the cell to its content, which pushed the number
    # hard against the headline for an Outlook reader. The badge itself is a
    # one-cell table rather than a styled div, so Word gives it real dimensions
    # (it still renders square there — border-radius is unsupported).
    return f"""<tr>
      <td width="34" style="width:34px;padding:11px 0;vertical-align:top;{border}">
        <table width="23" cellpadding="0" cellspacing="0" border="0" style="{MSO_TABLE}">
          <tr><td width="23" height="23" align="center" bgcolor="{TEAL}"
            style="width:23px;height:23px;background:{TEAL};border-radius:50%;
            color:#ffffff;font-size:12px;font-weight:800;text-align:center;
            {MSO_LH}line-height:23px;font-family:{FONT};">{rank}</td></tr>
        </table>
      </td>
      <td style="padding:11px 0;vertical-align:top;{border}">
        <a href="{link}" style="color:{INK};text-decoration:none;font-size:14.5px;
          font-weight:700;{MSO_LH}line-height:1.35;font-family:{FONT};">{title}</a>
        <div style="padding-top:4px;">{_meta_line(article, sector=article.get("sector"))}</div>
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
    link = _esc_attr(article["link"])
    border = "" if first else f"border-top:1px solid {SOFT};"
    tag = _top_pill() if is_top else ""
    # Summaries are now 4–5 sentences rather than one, so they carry a little
    # more leading and top margin to stay readable as a paragraph.
    summary_html = (
        f'<tr><td style="padding-top:7px;color:{BODY};font-size:13.5px;'
        f'{MSO_LH}line-height:1.62;font-family:{FONT};">{summary}</td></tr>'
        if summary else ""
    )
    # Headline, source line and summary each get their own row: cell padding is
    # the only vertical spacing Word reliably honours, where the div margins
    # this used to rely on were simply dropped.
    return f"""<tr><td style="padding:13px 0 13px 14px;border-left:3px solid {color};{border}">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="{MSO_TABLE}">
        <tr><td style="{MSO_LH}line-height:1.4;">
          {tag}<a href="{link}" style="color:{INK};text-decoration:none;font-size:15px;
            font-weight:700;line-height:1.4;font-family:{FONT};{MSO_LH}">{title}</a>
        </td></tr>
        <tr><td style="padding-top:4px;">{_meta_line(article)}</td></tr>
        {summary_html}
      </table>
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


# ── Best of the Rest ─────────────────────────────────────────────────────────
def _rest_row(article, last):
    """One scannable line: headline, then outlet and date. No summary."""
    border = "" if last else f"border-bottom:1px solid {SOFT};"
    parts = [f'<span style="color:{INK};font-weight:700;">'
             f'{_esc(article.get("source_short", ""))}</span>']
    if article.get("original_source"):
        parts.append(f'originally {_esc(article["original_source"])}')
    if article.get("paywalled"):
        parts.append("&#128274; sub")
    if article.get("pub_date"):
        parts.append(_esc(article["pub_date"]))
    sep = '<span style="color:#c8cdd4;"> &nbsp;&middot;&nbsp; </span>'
    return f"""<tr><td style="padding:9px 0;{border}">
      <a href="{_esc_attr(article["link"])}" style="color:{INK};text-decoration:none;
        font-size:13.5px;font-weight:600;{MSO_LH}line-height:1.4;font-family:{FONT};"
        >{_esc(article["title"])}</a>
      <div style="font-size:11.5px;color:{META};font-family:{FONT};{MSO_LH}
        line-height:1.45;padding-top:3px;">{sep.join(parts)}</div>
    </td></tr>"""


def _best_of_rest(items):
    """Everything else that cleared the bar, as a flat scannable list.

    Deliberately unsorted by sector and unsummarized — this is the wide net,
    read by skimming headlines, not the curated part of the digest.
    """
    if not items:
        return ""
    n = len(items)
    rows = "".join(_rest_row(a, i == n - 1) for i, a in enumerate(items))
    return f"""<tr><td style="padding:22px 32px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr><td style="padding:16px 0 8px;border-bottom:2px solid {META};">
          <span style="display:inline-block;width:9px;height:9px;background:{META};
            border-radius:2px;margin-right:8px;vertical-align:1px;"></span>
          <span style="color:{META};font-size:13px;font-weight:700;font-family:{FONT};
            text-transform:uppercase;letter-spacing:1.4px;">Best of the Rest</span>
          <span style="color:#aeb6c0;font-size:12px;font-family:{FONT};
            margin-left:7px;">{n}</span>
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
          <div style="color:{INK};font-size:14.5px;{MSO_LH}line-height:1.62;
            font-family:{FONT};">
            {_esc(lead)}
          </div>
        </td></tr>
      </table>
    </td></tr>"""


def build_html_email(today, sections, lead=None, top_stories=None, count=None,
                     rest=None):
    """Render the digest.

    ``sections``      list of ``(sector_name, [articles])``.
    ``lead``          optional LLM editor's brief (omitted in fallback mode).
    ``top_stories``   optional ranked list for the hero (omitted in fallback).
    ``rest``          optional extra stories shown as bare headline + link.
    """
    date_str = f"{today:%A, %B} {today.day}, {today.year}"
    now = datetime.now(timezone.utc)
    timestamp = f"{now.strftime('%I').lstrip('0')}:{now:%M %p} UTC"
    rest = rest or []
    if count is None:
        count = sum(len(items) for _, items in sections)
    # The masthead counts the summarized stories; the wider net is called out
    # separately so the headline number still reflects the curated part.
    rest_label = f" &#43; {len(rest)} more" if rest else ""
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
<body style="margin:0;padding:0;background-color:{PAGE};font-family:{FONT};">
  <!-- bgcolor as well as CSS: some Outlook versions ignore a styled body -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{PAGE}"
    style="{MSO_TABLE}background-color:{PAGE};">
    <tr><td align="center" style="padding:24px 12px;">
      <!--[if mso]>
      <table role="presentation" width="{CARD_WIDTH}" cellpadding="0" cellspacing="0"
        border="0" align="center"><tr><td>
      <![endif]-->
      <!-- Word ignores max-width, so without the fixed-width table above this
           card stretched to the full window and every line ran long. Other
           clients never see that table and keep the fluid max-width below. -->
      <table cellpadding="0" cellspacing="0" border="0"
        style="{MSO_TABLE}width:100%;max-width:{CARD_WIDTH}px;background:#ffffff;
        border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(13,27,62,0.12);">

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
          <div style="padding-top:9px;color:#9fe0d4;font-size:10.5px;font-family:{FONT};
            text-transform:uppercase;letter-spacing:1.5px;font-weight:600;">
            {count} stories{rest_label} &nbsp;&middot;&nbsp; {tagline}
          </div>
        </td></tr>

        {_lead_block(lead)}
        {_hero(top_stories)}
        {"".join(_sector_section(s, items, top_links) for s, items in sections)}
        {_best_of_rest(rest)}

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
      <!--[if mso]></td></tr></table><![endif]-->
    </td></tr>
  </table>
</body>
</html>"""
