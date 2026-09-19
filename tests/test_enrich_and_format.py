"""LLM call guards and HTML rendering.

The truncation guard exists because on 2026-09-06 the model returned 1 article
out of 77 and the digest shipped with a single story. Every branch of that
guard is asserted here.
"""

from datetime import date
from unittest import mock

from aggregator import enrich as E
from aggregator import formatter as F


def _payload(n, lead="a lead"):
    return {"lead": lead,
            "articles": [{"id": i, "keep": True, "significance": 90 - i,
                          "sector": "Office", "summary": f"s{i}", "cluster": i}
                         for i in range(n)]}


# ── truncation guard ─────────────────────────────────────────────────────────

def test_retry_then_give_up_on_persistent_truncation():
    calls = {"n": 0}

    def truncated(*_a, **_k):
        calls["n"] += 1
        return _payload(1)

    with mock.patch.object(E, "_call_model", truncated):
        out = E._call_with_retry("u", "s", {}, expected=20)
    assert calls["n"] == E._MAX_ATTEMPTS
    assert out is None


def test_recovers_on_retry():
    calls = {"n": 0}

    def flaky(*_a, **_k):
        calls["n"] += 1
        return _payload(1) if calls["n"] == 1 else _payload(20)

    with mock.patch.object(E, "_call_model", flaky):
        out = E._call_with_retry("u", "s", {}, expected=20)
    assert calls["n"] == 2
    assert len(out["articles"]) == 20


def test_api_errors_are_retried_then_degrade():
    with mock.patch.object(E, "_call_model", side_effect=RuntimeError("529")):
        assert E._call_with_retry("u", "s", {}, expected=10) is None


def test_a_full_response_passes_first_time():
    with mock.patch.object(E, "_call_model", return_value=_payload(20)) as m:
        out = E._call_with_retry("u", "s", {}, expected=20)
    assert m.call_count == 1 and out is not None


# ── elaborate ────────────────────────────────────────────────────────────────

def _stories(n, **kw):
    base = {"title": "T", "source_short": "X", "pub_date": "Sep 19", "sector": "Office",
            "source_text": "body " * 80, "text_thin": False, "summary": "short triage"}
    return [dict(base, title=f"Story {i}", **kw) for i in range(n)]


def test_elaborate_writes_long_summaries():
    stories = _stories(6)
    resp = {"lead": "fresh lead",
            "articles": [{"id": i, "summary_long": f"Long {i}.", "alternate_ok": False}
                         for i in range(6)]}
    with mock.patch.object(E, "_call_model", return_value=resp):
        lead = E.elaborate(stories)
    assert lead == "fresh lead"
    assert stories[0]["summary"] == "Long 0."


def test_elaborate_failure_preserves_short_summaries():
    """Losing the long-form pass must not lose the digest."""
    stories = _stories(6)
    with mock.patch.object(E, "_call_model", return_value={"lead": "x", "articles": []}):
        lead = E.elaborate(stories)
    assert lead is None
    assert all(s["summary"] == "short triage" for s in stories)


def test_elaborate_records_alternate_confirmation():
    stories = _stories(4)
    for s in stories:
        s["public_alt"] = {"link": "l", "source_name": "CBS News", "title": "alt", "summary": ""}
    resp = {"lead": "L", "articles": [{"id": i, "summary_long": f"S{i}.",
                                       "alternate_ok": i % 2 == 0} for i in range(4)]}
    with mock.patch.object(E, "_call_model", return_value=resp):
        E.elaborate(stories)
    assert [s["alt_confirmed"] for s in stories] == [True, False, True, False]


def test_elaborate_on_empty_input():
    assert E.elaborate([]) is None


def test_thin_stories_are_marked_for_the_prompt():
    stories = _stories(2, text_thin=True, source_text="just a headline")
    built = E._build_elaborate_input(stories)
    assert "[THIN SOURCE TEXT]" in built


# ── formatter ────────────────────────────────────────────────────────────────

def test_attribute_escaping_blocks_quote_breakout():
    evil = 'https://x.com/a"><script>alert(1)</script>'
    out = F._story_row({"title": "T", "summary": "s", "link": evil, "source_short": "X"},
                       "#000", True, False)
    assert "&quot;" in out
    assert "<script>" not in out


def test_body_text_is_escaped():
    out = F._story_row({"title": "<b>bold</b>", "summary": "a & b", "link": "https://x.com/a",
                        "source_short": "X"}, "#000", True, False)
    assert "&lt;b&gt;bold&lt;/b&gt;" in out and "a &amp; b" in out


def test_best_of_rest_renders_without_summaries(article):
    items = [article(title=f"Rest story {i}", link=f"https://ex.com/{i}") for i in range(5)]
    html = F._best_of_rest(items)
    assert "Best of the Rest" in html
    assert "line-height:1.62" not in html  # the summary paragraph style
    assert html.count('<tr><td style="padding:9px 0') == 5


def test_best_of_rest_is_omitted_when_empty():
    assert F._best_of_rest([]) == ""


def test_rest_rows_carry_paywall_and_attribution(article):
    items = [article(title="Gated story here", paywalled=True, original_source="Bloomberg")]
    html = F._best_of_rest(items)
    assert "&#128274;" in html and "originally Bloomberg" in html


def test_full_email_includes_both_sections(article):
    main = [article(title="Main story about a deal", summary="A summary. Another.")]
    rest = [article(title=f"Rest story {i}", link=f"https://ex.com/r{i}") for i in range(3)]
    html = F.build_html_email(date(2026, 9, 19), [("Capital Markets", main)],
                              lead="Lead.", top_stories=main, count=1, rest=rest)
    assert "Best of the Rest" in html
    assert "+ 3 more" in html.replace("&#43;", "+")
    assert html.index("Best of the Rest") > html.index("Main story about a deal")


def test_email_without_rest_has_no_section_or_label(article):
    main = [article(title="Main story about a deal", summary="A summary.")]
    html = F.build_html_email(date(2026, 9, 19), [("Capital Markets", main)],
                              lead="L", top_stories=main, count=1)
    assert "Best of the Rest" not in html
