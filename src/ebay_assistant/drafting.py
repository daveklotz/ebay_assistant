"""Draft the drop-off message: guess wording from the order, render the template."""

from __future__ import annotations

import re

from .orders import LineItem

MAX_MESSAGE_LEN = 2000

PACKAGE_DESCS = ["the card", "the cards", "the box", "the boxes"]

SUPPORTED_PLACEHOLDERS = ("package_desc", "buyer_username", "tracking_number", "carrier")

BOX_RE = re.compile(r"\b(blaster|hobby|mega|hanger|sealed|box)\b", re.IGNORECASE)
LOT_RE = re.compile(r"\blot\b", re.IGNORECASE)


class DraftError(Exception):
    pass


def guess_package_desc(line_items: list[LineItem]) -> str:
    total_quantity = sum(item.quantity for item in line_items)
    if any(BOX_RE.search(item.title) for item in line_items):
        return "the boxes" if total_quantity > 1 else "the box"
    if (
        total_quantity > 1
        or len(line_items) > 1
        or any(LOT_RE.search(item.title) for item in line_items)
    ):
        return "the cards"
    return "the card"


def render_message(
    template: str,
    *,
    package_desc: str,
    buyer_username: str = "",
    tracking_number: str = "",
    carrier: str = "",
) -> str:
    values = {
        "package_desc": package_desc,
        "buyer_username": buyer_username,
        "tracking_number": tracking_number,
        "carrier": carrier,
    }
    try:
        message = template.format_map(values).strip()
    except KeyError as exc:
        supported = ", ".join("{" + name + "}" for name in SUPPORTED_PLACEHOLDERS)
        raise DraftError(
            f"unknown placeholder {{{exc.args[0]}}} in template.txt "
            f"(supported: {supported})"
        ) from None
    except (IndexError, ValueError) as exc:
        raise DraftError(f"could not render template.txt: {exc}") from None
    if len(message) > MAX_MESSAGE_LEN:
        raise DraftError(
            f"rendered message is {len(message)} characters; eBay's limit is "
            f"{MAX_MESSAGE_LEN} — shorten template.txt"
        )
    if not message:
        raise DraftError("template.txt rendered an empty message")
    return message
