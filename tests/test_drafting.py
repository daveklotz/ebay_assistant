from __future__ import annotations

import pytest

from ebay_assistant.config import DEFAULT_TEMPLATE
from ebay_assistant.drafting import DraftError, guess_package_desc, render_message
from ebay_assistant.orders import LineItem


def li(title: str, qty: int = 1) -> LineItem:
    return LineItem(title=title, quantity=qty)


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([li("2023 Topps Chrome Jordan Walker RC #142")], "the card"),
        ([li("2023 Topps Chrome Jordan Walker RC #142", qty=2)], "the cards"),
        ([li("Card A"), li("Card B")], "the cards"),
        ([li("2024 Bowman Lot of 5 Prospects")], "the cards"),
        ([li("2024 Topps Chrome Blaster Box")], "the box"),
        ([li("2024 Topps Chrome Blaster Box", qty=2)], "the boxes"),
        ([li("Sealed 2023 Panini Prizm Hanger Pack")], "the box"),
        ([li("1998 Boxing card Muhammad Ali")], "the card"),
        ([li("Unboxing special edition insert")], "the card"),
        ([li("Single card"), li("2023 Blaster Box")], "the boxes"),
        ([li("Hobby fresh pull refractor")], "the box"),
    ],
)
def test_guess_package_desc(items, expected):
    assert guess_package_desc(items) == expected


def test_render_default_template():
    message = render_message(DEFAULT_TEMPLATE, package_desc="the cards")
    assert "the cards" in message
    assert "{" not in message
    assert len(message) <= 2000


def test_render_all_placeholders():
    out = render_message(
        "To {buyer_username}: {package_desc} via {carrier} ({tracking_number})",
        package_desc="the card",
        buyer_username="fan",
        tracking_number="9400",
        carrier="USPS",
    )
    assert out == "To fan: the card via USPS (9400)"


def test_render_unknown_placeholder():
    with pytest.raises(DraftError, match="unknown placeholder"):
        render_message("Hello {foo}", package_desc="x")


def test_render_too_long():
    with pytest.raises(DraftError, match="2000"):
        render_message("x" * 2000 + "{package_desc}", package_desc="the cards")


def test_render_empty():
    with pytest.raises(DraftError, match="empty"):
        render_message("   ", package_desc="the card")
