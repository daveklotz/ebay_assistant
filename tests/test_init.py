from __future__ import annotations

import pytest

from ebay_assistant.init_cmd import _consent_url, _extract_code

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


def test_extract_code_rejects_authnauth_redirect():
    with pytest.raises(ValueError, match="Auth'n'Auth"):
        _extract_code(
            "https://github.com/daveklotz/ebay_assistant"
            "?ebaytkn=&tknexp=2028-01-14+22%3A28%3A57&username=daveklotz"
        )


def test_consent_url():
    url = _consent_url("production", "MyAppId-123", "Me-App-xyz")
    assert url.startswith("https://auth.ebay.com/oauth2/authorize?")
    assert "client_id=MyAppId-123" in url
    assert "redirect_uri=Me-App-xyz" in url
    assert "response_type=code" in url
    assert (
        "scope=https%3A//api.ebay.com/oauth/api_scope/sell.fulfillment.readonly"
        "%20https%3A//api.ebay.com/oauth/api_scope/commerce.message" in url
    )
