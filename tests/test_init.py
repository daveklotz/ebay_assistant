from __future__ import annotations

import pytest

from ebay_assistant.init_cmd import _extract_code

DECODED = "v^1.1#i^1#f^0#p^3#r^1#I^3#t^Ul41XzE6RkFCQ0RFmM0MjA"
ENCODED = "v%5E1.1%23i%5E1%23f%5E0%23p%5E3%23r%5E1%23I%5E3%23t%5EUl41XzE6RkFCQ0RFmM0MjA"


@pytest.mark.parametrize(
    "pasted",
    [
        f"https://github.com/daveklotz/ebay_assistant?code={ENCODED}&expires_in=299",
        f"?code={ENCODED}&expires_in=299",
        f"code={ENCODED}&expires_in=299",
        ENCODED,
        DECODED,
    ],
)
def test_extract_code(pasted):
    assert _extract_code(pasted) == DECODED
