from datetime import datetime, timezone


def _article_row(article):
    color = article["source_color"]
    title = article["title"].replace("<", "&lt;").replace(">", "&gt;")
    summary = article["summary"].replace("<", "&lt;").replace(">", "&gt;") if article["summary"] else ""
    link = article["link"]
    short = article["source_short"]

    return f"""<tr>
      <td style="padding:12px 0;border-bottom:1px solid #e2e5ec;vertical-align:top;">
        <span style="display:inline-block;background:{color};color:#ffffff;padding:2px 8px;border-radius:3px;font-size:9px;font-family:Arial,Helvetica,sans-serif;text-transform:uppercase;letter-spacing:0.9px;font-weight:700;margin-bottom:6px;">{short}</span><br>
        <a href="{link}" style="color:#0d1b3e;text-decoration:none;font-size:14px;font-weight:700;line-height:1.35;font-family:Arial,Helvetica,sans-serif;">{title}</a>
        {"<br><span style='color:#5a6070;font-size:12px;line-height:1.45;font-family:Arial,Helvetica,sans-serif;font-style:italic;'>" + summary + "</span>" if summary else ""}
      </td>
    </tr>"""


def build_html_email(articles, today):
    date_str = today.strftime("%B %d, %Y")
    timestamp = datetime.now(timezone.utc).strftime("%I:%M %p UTC")
    count = len(articles)
    rows = "".join(_article_row(a) for a in articles)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CRE Daily Digest — {date_str}</title>
</head>
<body style="margin:0;padding:16px;background-color:#eef1f7;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center">
        <table width="860" cellpadding="0" cellspacing="0" border="0" style="max-width:860px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="background:#0d1b3e;border-radius:6px 6px 0 0;padding:18px 36px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <span style="color:#7a9cc0;font-size:10px;text-transform:uppercase;letter-spacing:2px;">Commercial Real Estate</span><br>
                    <span style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:0.3px;">Daily Digest</span>
                  </td>
                  <td align="right" style="vertical-align:middle;">
                    <span style="color:#a8bcd4;font-size:13px;">{date_str}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="background:#ffffff;padding:20px 36px 16px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                {rows}
                <tr>
                  <td style="padding-top:12px;">
                    <span style="color:#aaaaaa;font-size:11px;">Top {count} articles · Ranked by source authority and editorial prominence</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#dde1eb;border-radius:0 0 6px 6px;padding:12px 36px;text-align:center;">
              <span style="color:#888888;font-size:11px;">CRE Daily Digest &nbsp;·&nbsp; Generated {timestamp}</span>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
