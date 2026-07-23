"""ebay-assistant command-line entry point."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from . import __version__, init_cmd, notify
from .auth import AuthError, get_access_token, warn_if_expiring
from .config import ConfigError, load_config, load_credentials
from .ebay_client import EbayApiError, EbayClient
from .orders import fetch_labeled_orders
from .state import State, StateError


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ebay-assistant",
        description=(
            "Personal assistant for eBay sellers — message buyers when you drop "
            "their package at the post office."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="interactive setup: keyset, OAuth token, config files"
    )
    init_parser.add_argument(
        "--refresh-token",
        dest="refresh_token_only",
        action="store_true",
        help="only replace the saved OAuth refresh token",
    )
    init_parser.set_defaults(func=init_cmd.run)

    orders_parser = subparsers.add_parser(
        "orders", help="list recent orders and their label status (read-only)"
    )
    orders_parser.add_argument(
        "--days", type=int, help="look-back window in days (default: config days_back)"
    )
    orders_parser.set_defaults(func=cmd_orders)

    notify_parser = subparsers.add_parser(
        "notify", help="send drop-off messages for recently labeled orders"
    )
    notify_parser.add_argument(
        "--days", type=int, help="look-back window in days (default: config days_back)"
    )
    notify_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show drafts but send nothing and record nothing",
    )
    notify_parser.add_argument(
        "--include-messaged",
        action="store_true",
        help="also review orders already marked as handled",
    )
    notify_parser.set_defaults(func=notify.run)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (ConfigError, StateError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except AuthError as exc:
        print(f"auth error: {exc}", file=sys.stderr)
        return 2
    except EbayApiError as exc:
        print(f"eBay API error: {exc}", file=sys.stderr)
        return 3
    except (KeyboardInterrupt, EOFError):
        print()
        return 130


def cmd_orders(args) -> int:
    config = load_config()
    creds = load_credentials()
    warn_if_expiring(creds)
    client = EbayClient(config.api_base, lambda: get_access_token(config, creds))
    days = args.days or config.days_back
    state = State.load(config.config_dir)

    print(f"Orders labeled (or awaiting a label) in the last {days} days:")
    labeled, unlabeled, earlier = fetch_labeled_orders(client, days, labeled_only=False)
    orders = labeled + unlabeled
    if not orders:
        print("  (none)")
        if earlier:
            print(
                f"  ({len(earlier)} older labeled order(s) were modified recently "
                "— widen with --days to see them)"
            )
        return 0

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    orders.sort(key=lambda o: o.creation_date or epoch, reverse=True)
    for order in orders:
        sold = order.creation_date.strftime("%b %d") if order.creation_date else "?"
        if order.has_label:
            status = {"sent": "messaged", "never": "never-message"}.get(
                state.status(order.order_id), "ready to notify"
            )
        else:
            status = "awaiting label"
        buyer = order.buyer_username or "?"
        print(f"\n  {order.order_id}  buyer: {buyer}  sold: {sold}  [{status}]")
        for item in order.line_items:
            print(f"    {item.quantity}x {item.title}")
        for fulfillment in order.fulfillments:
            labeled_on = (
                fulfillment.shipped_date.strftime("%b %d")
                if fulfillment.shipped_date
                else "?"
            )
            pieces = " ".join(
                p for p in (fulfillment.carrier_code, fulfillment.tracking_number) if p
            )
            print(f"    -> label {labeled_on}: {pieces or 'no tracking'}")
    if earlier:
        print(
            f"\n  (+ {len(earlier)} older labeled order(s) modified recently, "
            "hidden — widen with --days to see them)"
        )
    return 0
