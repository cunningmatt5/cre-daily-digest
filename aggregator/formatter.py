from datetime import datetime, timezone

FONT = "Arial, Helvetica, sans-serif"


def _article_row(article, index):
    color = article["source_color"]
    title = article["title"].replace("<", "&lt;").replace(">", "&gt;")
    summary = article["summary"].replace("<", "&lt;").replace(">", "&gt;") if article["summary"] else ""
    link = article["link"]
    short = article["source_short"]
    num = str(index + 1).zfill(2)

    summary_html = (
        f'<div style="margin-top:4px;color:#6b7280;font-size:12px;'
        f'line-height:1.5;font-family:{FONT};">{summary}</div>'
        if summary else ""
    )

    return f"""<tr>
      <td style="width:28px;padding:14px 10px 14px 0;vertical-align:top;border-bottom:1px solid #e5e7eb;">
        <span style="color:#c0c8d8;font-size:11px;font-weight:700;font-family:{FONT};">{num}</span>
      </td>
      <td style="padding:14px 0;vertical-align:top;border-bottom:1px solid #e5e7eb;">
        <span style="display:inline-block;background:{color};color:#ffffff;padding:2px 7px;
          border-radius:2px;font-size:9px;font-family:{FONT};text-transform:uppercase;
          letter-spacing:1px;font-weight:700;margin-bottom:5px;">{short}</span>
        <div style="margin:0;">
          <a href="{link}" style="color:#1a1f36;text-decoration:none;font-size:13.5px;
            font-weight:700;line-height:1.4;font-family:{FONT};">{title}</a>
        </div>
        {summary_html}
      </td>
    </tr>"""


def build_html_email(articles, today):
    date_str = today.strftime("%B %d, %Y")
    dow = today.strftime("%A")
    timestamp = datetime.now(timezone.utc).strftime("%I:%M %p UTC")
    count = len(articles)
    rows = "".join(_article_row(a, i) for i, a in enumerate(articles))

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
          style="width:100%;max-width:860px;">

          <!-- Header -->
          <tr>
            <td style="background:#0d1b3e;border-radius:6px 6px 0 0;
              padding:20px 32px 18px;">
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
                {count} articles &nbsp;·&nbsp; Ranked by deal size, named entities &amp; editorial prominence
              </span>
            </td>
          </tr>

          <!-- Article list -->
          <tr>
            <td style="background:#ffffff;padding:8px 32px 16px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                {rows}
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f8f9fb;border-top:1px solid #e5e7eb;
              border-radius:0 0 6px 6px;padding:12px 32px;">
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
