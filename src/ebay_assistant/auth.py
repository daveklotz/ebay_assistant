"""OAuth token handling: refresh token → short-lived access token, with caching."""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timedelta, timezone

import requests

from .config import (
    TOKEN_CACHE_FILE,
    Config,
    Credentials,
    parse_datetime,
    to_iso,
    write_secret_file,
)

SCOPES = [
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
    "https://api.ebay.com/oauth/api_scope/commerce.message",
]

EXPIRY_WARNING_DAYS = 30


class AuthError(Exception):
    """eBay rejected our credentials; the message says how to fix it."""


def get_access_token(config: Config, creds: Credentials) -> str:
    cache_path = config.config_dir / TOKEN_CACHE_FILE
    now = datetime.now(timezone.utc)
    try:
        cache = json.loads(cache_path.read_text())
        expires_at = parse_datetime(cache["expires_at"])
        if cache.get("environment") == config.environment and expires_at > now + timedelta(
            seconds=120
        ):
            return cache["access_token"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    token, expires_at = refresh_access_token(config, creds)
    write_secret_file(
        cache_path,
        json.dumps(
            {
                "access_token": token,
                "expires_at": to_iso(expires_at),
                "environment": config.environment,
            }
        )
        + "\n",
    )
    return token


def refresh_access_token(config: Config, creds: Credentials) -> tuple[str, datetime]:
    basic = base64.b64encode(f"{creds.app_id}:{creds.cert_id}".encode()).decode()
    resp = requests.post(
        f"{config.api_base}/identity/v1/oauth2/token",
        headers={"Authorization": f"Basic {basic}"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "scope": " ".join(SCOPES),
        },
        timeout=30,
    )
    if resp.status_code == 200:
        payload = resp.json()
        lifetime = int(payload.get("expires_in", 7200))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(lifetime - 60, 60))
        return payload["access_token"], expires_at

    try:
        error_code = resp.json().get("error", "")
    except ValueError:
        error_code = ""
    if resp.status_code == 400 and error_code == "invalid_grant":
        raise AuthError(
            "your refresh token has expired or been revoked — mint a new user token "
            "on developer.ebay.com, then run `ebay-assistant init --refresh-token`"
        )
    if resp.status_code == 400 and error_code == "invalid_scope":
        raise AuthError(
            "your token is missing a required OAuth scope — mint a new user token that "
            "includes sell.fulfillment.readonly and commerce.message, then run "
            "`ebay-assistant init --refresh-token`"
        )
    if resp.status_code == 401:
        raise AuthError(
            "eBay rejected your App ID / Cert ID — re-check your keyset and re-run "
            "`ebay-assistant init`"
        )
    raise AuthError(f"token refresh failed (HTTP {resp.status_code}): {resp.text[:300]}")


def warn_if_expiring(creds: Credentials) -> None:
    expires_at = creds.refresh_token_expires_at
    if not expires_at:
        return
    days_left = (expires_at - datetime.now(timezone.utc)).days
    if days_left < 0:
        print(
            "warning: your saved refresh token is past its expected expiry date",
            file=sys.stderr,
        )
    elif days_left <= EXPIRY_WARNING_DAYS:
        print(
            f"warning: your refresh token expires in about {days_left} days — mint a "
            "new one soon and run `ebay-assistant init --refresh-token`",
            file=sys.stderr,
        )
