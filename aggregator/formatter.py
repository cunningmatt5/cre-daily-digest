from datetime import datetime, timezone

from .config import SECTOR_COLORS

FONT = "Arial, Helvetica, sans-serif"


def _esc(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _source_chips(article, accent):
    short = article["source_short"]
    chip = (
        f'<span style="display:inline-block;background:{accent};color:#ffffff;'
        f'padding:2px 7px;border-radius:2px;font-size:9px;font-family:{FONT};'
        f'text-transform:uppercase;letter-spacing:1px;font-weight:700;">{_esc(short)}</span>'
    )
    also = article.get("also_sources") or []
    if also:
        names = ", ".join(_esc(s) for s in also[:4])
        more = f" +{len(also) - 4}" if len(also) > 4 else ""
        chip += (
            f'<span style="color:#9ca3af;font-size:10px;font-family:{FONT};'
            f'margin-left:7px;">also {names}{more}</span>'
        )
    return chip


def _paywall_badge(article):
    if not article.get("paywalled"):
        return ""
    return (
        '<span style="display:inline-block;color:#92400e;background:#fef3c7;'
        'border:1px solid #f59e0b;border-radius:2px;font-size:9px;'
        f'font-family:{FONT};font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.8px;padding:1px 5px;margin-left:6px;'
        'vertical-align:middle;">&#128274; Subscription</span>'
    )


def _top_tag(article):
    if article.get("significance", 0) < 75:
        return ""
    return (
        '<span style="display:inline-block;color:#b91c1c;background:#fee2e2;'
        'border-radius:2px;font-size:9px;'
        f'font-family:{FONT};font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.8px;padding:1px 5px;margin-left:6px;'
        'vertical-align:middle;">&#9733; Top story</span>'
    )


def _story_card(article, accent):
    title = _esc(article["title"])
    summary = _esc(article.get("summary", ""))
    link = article["link"]

    date_line = (
        f'<span style="color:#9ca3af;font-size:11px;font-family:{FONT};">'
        f'{_esc(article.get("pub_date"))}</span>'
        if article.get("pub_date") else ""
    )
    summary_html = (
        f'<div style="margin-top:4px;color:#4b5563;font-size:12.5px;'
        f'line-height:1.5;font-family:{FONT};">{summary}</div>'
        if summary else ""
    )

    return f"""<tr>
      <td style="padding:0 0 0 12px;border-left:3px solid {accent};">
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
          style="margin:0 0 14px;">
          <tr><td>
            <div style="margin-bottom:5px;">
              {_source_chips(article, accent)}{_paywall_badge(article)}{_top_tag(article)}
            </div>
            <div>
              <a href="{link}" style="color:#1a1f36;text-decoration:none;font-size:14px;
                font-weight:700;line-height:1.4;font-family:{FONT};">{title}</a>
            </div>
            {f'<div style="margin-top:3px;">{date_line}</div>' if date_line else ""}
            {summary_html}
          </td></tr>
        </table>
      </td>
    </tr>"""


def _sector_section(sector, items):
    accent = SECTOR_COLORS.get(sector, "#4b5563")
    cards = "".join(_story_card(a, accent) for a in items)
    return f"""<tr>
      <td style="padding:18px 32px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr><td style="padding-bottom:12px;border-bottom:2px solid {accent};">
            <span style="color:{accent};font-size:13px;font-weight:700;font-family:{FONT};
              text-transform:uppercase;letter-spacing:1.5px;">{_esc(sector)}</span>
            <span style="color:#c0c8d8;font-size:11px;font-family:{FONT};
              margin-left:8px;">{len(items)}</span>
          </td></tr>
        </table>
      </td>
    </tr>
    <tr><td style="padding:14px 32px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">{cards}</table>
    </td></tr>"""


def _lead_block(lead):
    if not lead:
        return ""
    return f"""<tr>
      <td style="padding:18px 32px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
          style="background:#f4f6fb;border-left:4px solid #0d1b3e;border-radius:4px;">
          <tr><td style="padding:14px 18px;">
            <div style="color:#0d1b3e;font-size:10px;font-family:{FONT};font-weight:700;
              text-transform:uppercase;letter-spacing:2px;margin-bottom:6px;">
              Today&#39;s Brief
            </div>
            <div style="color:#1a1f36;font-size:13.5px;line-height:1.6;font-family:{FONT};">
              {_esc(lead)}
            </div>
          </td></tr>
        </table>
      </td>
    </tr>"""


def build_html_email(today, sections, lead=None, count=None):
    """Render the digest.

    ``sections`` is a list of ``(sector_name, [articles])``. ``lead`` is the
    optional LLM editor's brief (omitted in deterministic fallback mode).
    """
    date_str = today.strftime("%B %d, %Y")
    dow = today.strftime("%A")
    timestamp = datetime.now(timezone.utc).strftime("%I:%M %p UTC")
    if count is None:
        count = sum(len(items) for _, items in sections)
    subtitle = (
        "Clustered, ranked &amp; summarized by Claude"
        if lead else
        "Ranked by deal size, named entities &amp; cross-source corroboration"
    )
    section_html = "".join(_sector_section(s, items) for s, items in sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CRE Daily Digest — {date_str}</title>
</head>
<body style="margin:0;padding:20px 12px;background-color:#f1f3f8;font-family:{FONT};">
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center">
        <table cellpadding="0" cellspacing="0" border="0"
          style="width:100%;max-width:720px;background:#ffffff;border-radius:6px;
          overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:#0d1b3e;padding:20px 32px 18px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <div style="color:#7b9ec7;font-size:10px;font-family:{FONT};
                      text-transform:uppercase;letter-spacing:2.5px;margin-bottom:4px;">
                      Commercial Real Estate
                    </div>
                    <div style="color:#ffffff;font-size:22px;font-weight:700;
                      font-family:{FONT};letter-spacing:0.2px;line-height:1;">
                      Daily Digest
                    </div>
                  </td>
                  <td align="right" style="vertical-align:bottom;">
                    <div style="color:#a8c0d8;font-size:13px;font-family:{FONT};">
                      {dow}, {date_str}
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Subheader bar -->
          <tr>
            <td style="background:#162444;padding:8px 32px;">
              <span style="color:#7b9ec7;font-size:11px;font-family:{FONT};">
                {count} stories &nbsp;·&nbsp; {subtitle}
              </span>
            </td>
          </tr>

          {_lead_block(lead)}
          {section_html}

          <!-- Footer -->
          <tr>
            <td style="background:#f8f9fb;border-top:1px solid #e5e7eb;
              padding:16px 32px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <span style="color:#9ca3af;font-size:11px;font-family:{FONT};">
                      CRE Daily Digest
                    </span>
                  </td>
                  <td align="right">
                    <span style="color:#9ca3af;font-size:11px;font-family:{FONT};">
                      Generated {timestamp}
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
