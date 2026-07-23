"""Interactive first-run setup: keyset, OAuth token, config files."""

from __future__ import annotations

import getpass
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote

from .auth import (
    SCOPES,
    AuthError,
    exchange_authorization_code,
    get_access_token,
)
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

    refresh_token, expires_at = _obtain_token(environment, app_id, cert_id)

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
    refresh_token, expires_at = _obtain_token(
        config.environment, creds.app_id, creds.cert_id
    )
    creds = Credentials(
        app_id=creds.app_id,
        cert_id=creds.cert_id,
        refresh_token=refresh_token,
        refresh_token_expires_at=expires_at,
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


def _obtain_token(environment: str, app_id: str, cert_id: str) -> tuple[str, datetime]:
    print(f"""
Step 2 — Get a user token. Either way, open developer.ebay.com ->
Your Account -> User Access Tokens, and sign in with your eBay SELLER
account when eBay prompts you. The consent screen should include:
    {SCOPES[0]}
    {SCOPES[1]}

  A) Portal token: under "Get a User Token Here", choose OAuth, sign in,
     and copy the REFRESH token (the long "v^1.1#..." string labeled
     refresh).
  B) Test Sign-in workaround (use this when the OAuth radio button keeps
     popping the "Configure the OAuth Settings" dialog): under "Get a Token
     from eBay via Your Application", click Test Sign-in, sign in, and when
     the browser lands on your redirect page, copy the ENTIRE address-bar
     URL — it carries a ?code=... that is valid for about 5 minutes.
""")
    while True:
        method = input("Method [A/B] (A): ").strip().lower() or "a"
        if method in ("a", "b"):
            break
        print('  please answer "A" or "B"')
    if method == "a":
        refresh_token = getpass.getpass("Refresh token (hidden): ").strip()
        return refresh_token, _prompt_expiry()
    runame = input(
        "RuName (the generated 'eBay Redirect URL name', e.g. Your_Name-AppName-xxxxx): "
    ).strip()
    pasted = input("Paste the full redirect URL (or just the code value): ").strip()
    print("Exchanging the code for tokens...")
    _, refresh_token, expires_at = exchange_authorization_code(
        API_BASE[environment], app_id, cert_id, _extract_code(pasted), runame
    )
    print("Refresh token obtained.")
    return refresh_token, expires_at


def _extract_code(pasted: str) -> str:
    """Accepts a full redirect URL, a bare query string, or the code itself
    (still percent-encoded or already decoded)."""
    if "code=" in pasted:
        query = pasted.split("?", 1)[1] if "?" in pasted else pasted
        codes = parse_qs(query).get("code", [])
        if codes:
            return codes[0]
    return unquote(pasted.strip())


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
