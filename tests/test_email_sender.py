"""Recipient parsing and blind-copy delivery.

Two properties matter beyond "it sends". Readers must not see each other's
addresses, and no address may reach the logs — this runs in a public repo's CI,
where Actions masks a secret's exact value but not fragments of it, so a split
list printed one address per line would be exposed.
"""

from unittest import mock

import pytest

from aggregator import email_sender as E


# ── parsing ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "a@x.com,b@y.com,c@z.com",
    "a@x.com, b@y.com, c@z.com",
    "a@x.com;b@y.com;c@z.com",
    "a@x.com b@y.com c@z.com",
    "  a@x.com , b@y.com,,c@z.com  ",
    "a@x.com\nb@y.com\nc@z.com",
])
def test_separators_people_actually_paste(raw):
    valid, invalid = E.parse_recipients(raw)
    assert valid == ["a@x.com", "b@y.com", "c@z.com"]
    assert invalid == []


def test_duplicates_are_dropped_case_insensitively():
    valid, _ = E.parse_recipients("A@x.com, a@X.COM, b@y.com")
    assert valid == ["A@x.com", "b@y.com"]


def test_angle_brackets_are_tolerated():
    valid, _ = E.parse_recipients("<a@x.com>, b@y.com")
    assert valid == ["a@x.com", "b@y.com"]


def test_malformed_entries_are_separated_not_sent():
    """One bad address can otherwise get the whole send rejected."""
    valid, invalid = E.parse_recipients("a@x.com, not-an-address, b@y.com, missing@tld")
    assert valid == ["a@x.com", "b@y.com"]
    assert invalid == ["not-an-address", "missing@tld"]


def test_empty_falls_back_to_the_sender():
    valid, _ = E.parse_recipients("", fallback="me@gmail.com")
    assert valid == ["me@gmail.com"]


def test_no_fallback_yields_nothing():
    assert E.parse_recipients("") == ([], [])


# ── delivery ─────────────────────────────────────────────────────────────────

@pytest.fixture
def smtp(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    server = mock.MagicMock()
    server.sendmail.return_value = {}
    ctx = mock.MagicMock()
    ctx.__enter__.return_value = server
    monkeypatch.setattr(E.smtplib, "SMTP_SSL", mock.Mock(return_value=ctx))
    return server


def test_single_recipient_keeps_a_normal_to_header(monkeypatch, smtp):
    monkeypatch.setenv("RECIPIENT_EMAIL", "solo@x.com")
    E.send_gmail("<p>hi</p>", "Subject")
    envelope_to = smtp.sendmail.call_args[0][1]
    body = smtp.sendmail.call_args[0][2]
    assert envelope_to == ["solo@x.com"]
    assert "To: solo@x.com" in body


def test_several_recipients_are_blind_copied(monkeypatch, smtp):
    """The envelope carries everyone; the headers name nobody."""
    monkeypatch.setenv("RECIPIENT_EMAIL", "a@x.com, b@y.com, c@z.com")
    E.send_gmail("<p>hi</p>", "Subject")
    envelope_to = smtp.sendmail.call_args[0][1]
    body = smtp.sendmail.call_args[0][2]
    assert envelope_to == ["a@x.com", "b@y.com", "c@z.com"]
    for addr in ("a@x.com", "b@y.com", "c@z.com"):
        assert addr not in body, f"{addr} leaked into the message headers"
    assert "Bcc:" not in body, "a Bcc header would transmit the list"


def test_addresses_never_reach_the_logs(monkeypatch, smtp, capsys):
    """Public CI logs: Actions masks the whole secret, not its fragments."""
    monkeypatch.setenv("RECIPIENT_EMAIL", "a@x.com, b@y.com, oops")
    E.send_gmail("<p>hi</p>", "Subject")
    out = capsys.readouterr()
    combined = out.out + out.err
    for addr in ("a@x.com", "b@y.com", "oops"):
        assert addr not in combined
    assert "2 recipient(s)" in out.out
    assert "1 entry(s)" in out.err


def test_refused_recipients_are_reported_by_count(monkeypatch, smtp, capsys):
    monkeypatch.setenv("RECIPIENT_EMAIL", "a@x.com, b@y.com")
    smtp.sendmail.return_value = {"b@y.com": (550, b"no such user")}
    E.send_gmail("<p>hi</p>", "Subject")
    out = capsys.readouterr()
    assert "1 recipient(s), 1 refused" in out.out
    assert "b@y.com" not in out.out + out.err


def test_large_list_warns_before_gmails_limit(monkeypatch, smtp, capsys):
    monkeypatch.setenv("RECIPIENT_EMAIL",
                       ",".join(f"user{i}@x.com" for i in range(E.RECIPIENT_WARN_THRESHOLD + 5)))
    E.send_gmail("<p>hi</p>", "Subject")
    assert "near Gmail's per-message limit" in capsys.readouterr().err


def test_unset_recipient_still_sends_to_the_sender(monkeypatch, smtp):
    monkeypatch.delenv("RECIPIENT_EMAIL", raising=False)
    E.send_gmail("<p>hi</p>", "Subject")
    assert smtp.sendmail.call_args[0][1] == ["me@gmail.com"]
