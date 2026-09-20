import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Gmail caps recipients per message. The exact number varies by account type
# (roughly 100 for a personal account, higher for Workspace), and the daily
# total is capped separately. Warn well before the ceiling rather than
# discovering it when a morning send fails.
RECIPIENT_WARN_THRESHOLD = 90

_SPLIT = re.compile(r"[,;\s]+")


def parse_recipients(raw: str, fallback: str = "") -> tuple:
    """Split a configured recipient string into ``(valid, invalid)`` lists.

    Accepts commas, semicolons or whitespace as separators, so pasting a list
    from anywhere tends to work. Addresses are de-duplicated case-insensitively
    while keeping the original spelling and order.

    Anything without an ``@`` is returned separately rather than handed to the
    SMTP server, where a single malformed entry can reject the whole send.
    """
    seen, valid, invalid = set(), [], []
    for part in _SPLIT.split(raw or ""):
        part = part.strip().strip("<>")
        if not part:
            continue
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        (valid if "@" in part and "." in part.split("@")[-1] else invalid).append(part)
    if not valid and fallback:
        valid = [fallback]
    return valid, invalid


def send_gmail(html_body, subject):
    sender = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipients, invalid = parse_recipients(os.environ.get("RECIPIENT_EMAIL", ""), sender)

    if invalid:
        # Never print the entries themselves: this runs in a public repo's CI,
        # where Actions masks the secret's exact value but not fragments of it.
        print(f"WARNING: {len(invalid)} entry(s) in RECIPIENT_EMAIL are not valid "
              f"addresses and were skipped — check the separators.", file=sys.stderr)
    if len(recipients) > RECIPIENT_WARN_THRESHOLD:
        print(f"WARNING: {len(recipients)} recipients is near Gmail's per-message "
              f"limit; consider a mailing list or an email service.", file=sys.stderr)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"CRE Daily Digest <{sender}>"
    # One recipient keeps a normal To: header. Several become a blind copy —
    # the envelope carries them, no Bcc header is transmitted, and so no reader
    # sees anyone else's address.
    msg["To"] = recipients[0] if len(recipients) == 1 else f"CRE Daily Digest <{sender}>"

    plain = (
        "Your email client does not support HTML. "
        "Please view this email in a modern email client."
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        refused = server.sendmail(sender, recipients, msg.as_string())

    # Counts only, for the same reason as above.
    delivered = len(recipients) - len(refused)
    note = f", {len(refused)} refused" if refused else ""
    print(f"Sent: {subject!r} → {delivered} recipient(s){note}")
    if refused:
        print(f"WARNING: the mail server refused {len(refused)} recipient(s).",
              file=sys.stderr)
