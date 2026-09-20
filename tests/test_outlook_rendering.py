"""Constructs Outlook on Windows needs, and the HTML staying well-formed.

Outlook renders mail with the Microsoft Word engine. An Outlook reader saw a
visibly different email: the column ran the full window width and the text
blocks closed up. Word ignores max-width, drops margins on a div, collapses a
cell whose width is CSS-only, and applies its own line spacing.

None of this is verifiable without a real Outlook client, so these tests pin the
constructs that fix it rather than the rendering itself.
"""

import re
from datetime import date

from bs4 import BeautifulSoup

from aggregator import formatter as F


def build(article, rest=None):
    main = [article(title="A headline of a realistic length for this digest",
                    summary="A first sentence. A second one. A third for measure.")]
    return F.build_html_email(date(2026, 9, 20), [("Capital Markets", main)],
                              lead="An editor's brief.", top_stories=main,
                              count=1, rest=rest or [])


# ── the fixed-width card ─────────────────────────────────────────────────────

def test_mso_ghost_table_pins_the_width(article):
    """Word ignores max-width, so without this the card fills the window."""
    html = build(article)
    assert "<!--[if mso]>" in html
    assert f'width="{F.CARD_WIDTH}"' in html
    assert "<![endif]-->" in html


def test_mso_conditionals_are_balanced(article):
    """An unclosed conditional would swallow the rest of the email in Outlook."""
    html = build(article)
    assert html.count("<!--[if mso]>") == html.count("<![endif]-->")


def test_other_clients_still_get_the_fluid_card(article):
    """The conditional must not replace max-width, only supplement it."""
    assert f"max-width:{F.CARD_WIDTH}px" in build(article)


# ── spacing Word actually honours ────────────────────────────────────────────

def test_story_rows_use_cell_padding_not_div_margins(article):
    """Margins on a div are dropped by Word, which closed the blocks up."""
    row = F._story_row({"title": "T", "summary": "S", "link": "https://x.com/a",
                        "source_short": "X"}, "#000", True, False)
    assert "padding-top:" in row
    assert not re.search(r'<div style="[^"]*margin-top', row), \
        "spacing that Word drops has come back"


def test_meta_line_carries_no_margin(article):
    """Its caller places it in a padded cell instead."""
    meta = F._meta_line({"source_short": "Bisnow", "pub_date": "Sep 20"})
    assert "margin-top" not in meta


def test_line_heights_are_marked_exact(article):
    """Word substitutes its own leading unless told not to."""
    html = build(article)
    assert html.count(F.MSO_LH) >= 5


def test_nested_tables_suppress_words_gutter(article):
    assert "mso-table-lspace:0pt" in build(article)


# ── the cell the reader actually noticed ─────────────────────────────────────

def test_rank_cell_has_an_html_width_attribute(article):
    """CSS-only width collapses in Word, pulling the number into the headline."""
    hero = F._hero_item({"title": "T", "link": "https://x.com/a", "source_short": "X",
                         "sector": "Office"}, 1, False)
    assert 'width="34"' in hero, "Word needs the attribute, not just the CSS"
    assert "width:34px" in hero, "browsers still need the CSS"


def test_rank_badge_is_a_table_not_a_styled_div(article):
    """A div with width/height is not reliably sized by Word."""
    hero = F._hero_item({"title": "T", "link": "https://x.com/a", "source_short": "X"},
                        1, False)
    assert 'height="23"' in hero and 'bgcolor=' in hero


# ── still well-formed ────────────────────────────────────────────────────────

def test_html_parses_and_tables_balance(article):
    """The story row gained a nested table; an unbalanced one wrecks every client."""
    html = build(article, rest=[article(title="A secondary story worth a glance")])
    soup = BeautifulSoup(html, "lxml")
    assert soup.find("body") is not None
    assert html.count("<table") == html.count("</table>")
    assert html.count("<tr") == html.count("</tr>")
    assert html.count("<td") == html.count("</td>")


def test_content_survives_the_restructure(article):
    """Rearranging into table rows must not lose the summary or the link."""
    html = build(article)
    assert "A headline of a realistic length" in html
    assert "A first sentence." in html
    soup = BeautifulSoup(html, "lxml")
    assert any(a.get("href") for a in soup.find_all("a"))


def test_page_background_is_set_on_a_table_too(article):
    """Some Outlook versions ignore a styled <body>."""
    assert f'bgcolor="{F.PAGE}"' in build(article)
