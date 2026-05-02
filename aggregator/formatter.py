from datetime import datetime, timezone


def _article_row(article):
    color = article["source_color"]
    title = article["title"].replace("<", "&lt;").replace(">", "&gt;")
    summary = article["summary"].replace("<", "&lt;").replace(">", "&gt;") if article["summary"] else ""
    link = article["link"]
    short = article["source_short"]

    return f"""
    <div style="margin-bottom:26px;padding-bottom:26px;border-bottom:1px solid #e8eaed;">
      <div style="margin-bottom:9px;">
        <span style="display:inline-block;background:{color};color:#ffffff;padding:3px 10px;border-radius:3px;font-size:10px;font-family:Arial,Helvetica,sans-serif;text-transform:uppercase;letter-spacing:1px;font-weight:700;">{short}</span>
      </div>
      <h2 style="margin:0 0 7px;font-size:17px;line-height:1.45;font-family:Georgia,'Times New Roman',serif;font-weight:bold;">
        <a href="{link}" style="color:#1a2744;text-decoration:none;">{title}</a>
      </h2>
      <p style="margin:0;color:#555555;font-size:14px;line-height:1.65;font-family:Georgia,'Times New Roman',serif;font-style:italic;">{summary if summary else "&nbsp;"}</p>
    </div>"""


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
<body style="margin:0;padding:24px 16px;background-color:#eef0f4;font-family:Georgia,'Times New Roman',serif;">
  <div style="max-width:660px;margin:0 auto;">

    <!-- Header -->
    <div style="background:#1a2744;border-radius:8px 8px 0 0;padding:28px 40px 24px;">
      <p style="margin:0 0 4px;color:#7a9cc0;font-size:11px;font-family:Arial,Helvetica,sans-serif;text-transform:uppercase;letter-spacing:2px;">Commercial Real Estate</p>
      <h1 style="margin:0;color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:22px;font-weight:700;letter-spacing:0.5px;">Daily Digest</h1>
      <p style="margin:8px 0 0;color:#a8bcd4;font-size:14px;font-family:Arial,Helvetica,sans-serif;">{date_str}</p>
    </div>

    <!-- Body -->
    <div style="background:#ffffff;padding:36px 40px 28px;">
      {rows}
      <p style="margin:4px 0 0;color:#aaaaaa;font-size:12px;font-family:Arial,Helvetica,sans-serif;">
        Top {count} articles ranked by source authority and editorial prominence.
      </p>
    </div>

    <!-- Footer -->
    <div style="background:#dde1e9;border-radius:0 0 8px 8px;padding:16px 40px;text-align:center;">
      <p style="margin:0;color:#888888;font-size:11px;font-family:Arial,Helvetica,sans-serif;">
        CRE Daily Digest &nbsp;·&nbsp; Generated {timestamp}
      </p>
    </div>

  </div>
</body>
</html>"""
