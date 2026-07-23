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


def exchange_authorization_code(
    api_base: str, app_id: str, cert_id: str, code: str, redirect_uri: str
) -> tuple[str, str, datetime]:
    """Trade a one-time authorization code (from the consent redirect URL) for
    (access_token, refresh_token, refresh_token_expiry).

    Exists because the developer portal's "OAuth" radio button on the user-token
    page is sometimes broken; the RuName box's Test Sign-in flow still yields a
    ?code=... on the redirect URL, and this turns that into real tokens.
    """
    basic = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
    resp = requests.post(
        f"{api_base}/identity/v1/oauth2/token",
        headers={"Authorization": f"Basic {basic}"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    if resp.status_code == 200:
        payload = resp.json()
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(payload.get("refresh_token_expires_in", 47304000))
        )
        return payload["access_token"], payload["refresh_token"], refresh_expires_at

    try:
        error_code = resp.json().get("error", "")
    except ValueError:
        error_code = ""
    if error_code == "invalid_grant":
        raise AuthError(
            "eBay rejected the authorization code — codes are single-use and expire "
            "after about 5 minutes. Run Test Sign-in again and retry with a fresh URL."
        )
    if resp.status_code == 401 or error_code == "invalid_client":
        raise AuthError("eBay rejected your App ID / Cert ID — re-check your keyset.")
    if error_code == "invalid_request":
        raise AuthError(
            "eBay rejected the request — usually the redirect_uri is wrong: enter the "
            "RuName value (the generated string like Your_Name-AppName-xxxxx), not "
            "the URL it redirects to."
        )
    raise AuthError(f"code exchange failed (HTTP {resp.status_code}): {resp.text[:300]}")


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
