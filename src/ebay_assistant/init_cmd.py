"""Interactive first-run setup: keyset, OAuth token, config files."""

from __future__ import annotations

import getpass
import sys
from datetime import datetime, timedelta, timezone

from .auth import SCOPES, AuthError, get_access_token
from .config import (
    API_BASE,
    DEFAULT_TEMPLATE,
    TEMPLATE_FILE,
    TOKEN_CACHE_FILE,
    Config,
    ConfigError,
    Credentials,
    ensure_config_dir,
    load_config,
    load_credentials,
    parse_datetime,
    write_config,
    write_credentials,
)
from .ebay_client import EbayApiError, EbayClient

REFRESH_TOKEN_LIFETIME_DAYS = 547  # ~18 months, eBay's documented lifetime


def run(args) -> int:
    if getattr(args, "refresh_token_only", False):
        return _refresh_token_flow()
    return _full_setup()


def _full_setup() -> int:
    directory = ensure_config_dir()
    print("ebay-assistant setup")
    print(f"Config directory: {directory}\n")

    environment = _prompt_environment()

    print(f"""
Step 1 — Create your {environment} keyset
  1. Sign in at https://developer.ebay.com and open:
       Your Account -> Application Keys
  2. Create (or locate) your {environment.upper()} keyset.""")
    if environment == "production":
        print("""  3. eBay activates a production keyset only after you handle the
     "Marketplace Account Deletion" requirement. This tool runs locally
     and does not persist other eBay users' data, so choose the exemption
     ("Not persisting eBay data" opt-out) instead of providing a
     notification endpoint.""")
    print()
    app_id = input("App ID (Client ID): ").strip()
    cert_id = getpass.getpass("Cert ID (Client Secret, hidden): ").strip()

    print(f"""
Step 2 — Mint a user token
  1. Still on developer.ebay.com, open: Your Account -> User Access Tokens
  2. Pick this {environment} keyset, choose OAuth (not Auth'n'Auth), and
     sign in with your eBay SELLER account when prompted.
  3. Make sure the token includes these scopes:
       {SCOPES[0]}
       {SCOPES[1]}
  4. Copy the REFRESH token (the long "v^1.1#..." string labeled refresh).
""")
    refresh_token = getpass.getpass("Refresh token (hidden): ").strip()
    expires_at = _prompt_expiry()

    config = Config(
        environment=environment,
        days_back=7,
        email_copy_to_sender=False,
        config_dir=directory,
    )
    creds = Credentials(
        app_id=app_id,
        cert_id=cert_id,
        refresh_token=refresh_token,
        refresh_token_expires_at=expires_at,
    )

    write_config(config)
    write_credentials(creds, directory)
    (directory / TOKEN_CACHE_FILE).unlink(missing_ok=True)
    template_path = directory / TEMPLATE_FILE
    if template_path.exists():
        print(f"\nKept your existing message template: {template_path}")
    else:
        template_path.write_text(DEFAULT_TEMPLATE)
        print(f"\nWrote default message template: {template_path} (edit it any time)")
    print(f"Saved settings and credentials in {directory}")

    return _validate(config, creds)


def _refresh_token_flow() -> int:
    try:
        config = load_config()
        creds = load_credentials()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("Mint a new user token: developer.ebay.com -> Your Account -> User Access Tokens")
    print("(same keyset, OAuth, sign in as your seller account, scopes: "
          "sell.fulfillment.readonly + commerce.message)\n")
    refresh_token = getpass.getpass("New refresh token (hidden): ").strip()
    creds = Credentials(
        app_id=creds.app_id,
        cert_id=creds.cert_id,
        refresh_token=refresh_token,
        refresh_token_expires_at=_prompt_expiry(),
    )
    write_credentials(creds, config.config_dir)
    (config.config_dir / TOKEN_CACHE_FILE).unlink(missing_ok=True)
    print("Saved.")
    return _validate(config, creds)


def _validate(config: Config, creds: Credentials) -> int:
    print("\nValidating against eBay...")
    try:
        client = EbayClient(config.api_base, lambda: get_access_token(config, creds))
        total = client.count_recent_orders()
    except AuthError as exc:
        print(f"auth error: {exc}", file=sys.stderr)
        print(
            "Your details were saved — fix the keyset/token and re-run "
            "`ebay-assistant init` or `ebay-assistant init --refresh-token`.",
            file=sys.stderr,
        )
        return 2
    except EbayApiError as exc:
        print(f"eBay API error during validation: {exc}", file=sys.stderr)
        return 3
    print(f"Connected! eBay reports {total} order(s) in the last 90 days.")
    print(
        "Next: run `ebay-assistant orders` to see label status, "
        "then `ebay-assistant notify --dry-run`."
    )
    return 0


def _prompt_environment() -> str:
    while True:
        raw = (
            input("Environment [production/sandbox] (production): ").strip().lower()
            or "production"
        )
        if raw in API_BASE:
            return raw
        print('  please answer "production" or "sandbox"')


def _prompt_expiry() -> datetime:
    raw = input(
        "Refresh token expiry, if shown (YYYY-MM-DD, Enter = 18 months from now): "
    ).strip()
    if not raw:
        return datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_LIFETIME_DAYS)
    try:
        return parse_datetime(raw)
    except ValueError:
        print("  couldn't parse that date — storing 18 months from now instead")
        return datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_LIFETIME_DAYS)
