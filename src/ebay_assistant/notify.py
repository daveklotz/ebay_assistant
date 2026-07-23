"""The interactive notify flow: review each buyer's draft, confirm, send."""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from textwrap import indent

from .auth import get_access_token, warn_if_expiring
from .config import Config, load_config, load_credentials, load_template
from .drafting import (
    MAX_MESSAGE_LEN,
    PACKAGE_DESCS,
    DraftError,
    guess_package_desc,
    render_message,
)
from .ebay_client import EbayApiError, EbayClient
from .orders import BuyerGroup, fetch_labeled_orders, group_by_buyer
from .state import State

PROMPT = "[s]end  [v]ariant  [e]dit  [k]skip  [n]ever  [q]uit > "


def run(args) -> int:
    config = load_config()
    creds = load_credentials()
    warn_if_expiring(creds)
    client = EbayClient(config.api_base, lambda: get_access_token(config, creds))
    days = args.days or config.days_back
    template = load_template()
    state = State.load(config.config_dir)

    print(f"Fetching orders labeled in the last {days} days...")
    labeled, unlabeled = fetch_labeled_orders(client, days)

    already = [o for o in labeled if state.is_handled(o.order_id)]
    if args.include_messaged:
        pending = labeled
    else:
        pending = [o for o in labeled if not state.is_handled(o.order_id)]
    groups = group_by_buyer(pending)

    parts = [f"{len(labeled)} labeled order{'s' if len(labeled) != 1 else ''}"]
    if already and not args.include_messaged:
        parts.append(f"{len(already)} already handled")
    if unlabeled:
        parts.append(f"{len(unlabeled)} awaiting label")
    parts.append(f"{len(groups)} buyer{'s' if len(groups) != 1 else ''} to review")
    print("; ".join(parts) + ".")

    if not groups:
        print("Nothing to send.")
        return 0
    if args.dry_run:
        print("DRY RUN — nothing will be sent and nothing will be recorded.")

    counts = {"sent": 0, "skipped": 0, "never": 0, "dry-run": 0}
    for index, group in enumerate(groups, start=1):
        keep_going = _review_group(
            group, index, len(groups), client, state, config, template,
            args.dry_run, counts,
        )
        if not keep_going:
            print("Stopped.")
            break

    summary = ", ".join(f"{count} {label}" for label, count in counts.items() if count)
    print(f"\nDone: {summary or 'no messages sent'}.")
    return 0


def _review_group(
    group: BuyerGroup,
    index: int,
    total: int,
    client: EbayClient,
    state: State,
    config: Config,
    template: str,
    dry_run: bool,
    counts: dict,
) -> bool:
    """Returns False when the user quits."""
    if not group.buyer_username:
        print(
            f"\n[{index}/{total}] skipping order(s) {', '.join(group.order_ids)}: "
            "no buyer username on the order"
        )
        counts["skipped"] += 1
        return True

    _print_group(group, index, total)
    package_desc = guess_package_desc(group.line_items)
    message = _render(template, group, package_desc)
    if message is None:
        counts["skipped"] += 1
        return True

    while True:
        print(f'\nDraft (guessed "{package_desc}"):')
        print(indent(message, "  "))
        try:
            choice = input(PROMPT).strip().lower()
        except EOFError:
            return False
        if choice == "s":
            _send(group, message, client, state, config, dry_run, counts)
            return True
        if choice == "v":
            package_desc = _choose_variant(package_desc)
            message = _render(template, group, package_desc) or message
        elif choice == "e":
            edited = _edit_text(message)
            if len(edited) > MAX_MESSAGE_LEN:
                print(
                    f"  edited message is {len(edited)} characters "
                    f"(limit {MAX_MESSAGE_LEN}) — not applied"
                )
            else:
                message = edited
        elif choice == "k":
            counts["skipped"] += 1
            return True
        elif choice == "n":
            state.mark_never(group.order_ids, group.buyer_username)
            counts["never"] += 1
            print("  marked — this order won't be shown again")
            return True
        elif choice == "q":
            return False


def _print_group(group: BuyerGroup, index: int, total: int) -> None:
    print("\n" + "=" * 62)
    orders_word = "order" if len(group.orders) == 1 else "orders"
    print(f"[{index}/{total}] {group.buyer_username} — {len(group.orders)} {orders_word}")
    for order in group.orders:
        labeled = order.label_date.strftime("%b %d") if order.label_date else "date unknown"
        print(f"  Order {order.order_id} (labeled {labeled}):")
        for item in order.line_items:
            print(f"    {item.quantity}x {item.title}")
        for fulfillment in order.fulfillments:
            pieces = " ".join(
                p for p in (fulfillment.carrier_code, fulfillment.tracking_number) if p
            )
            if pieces:
                print(f"    -> {pieces}")


def _render(template: str, group: BuyerGroup, package_desc: str) -> str | None:
    tracking = group.first_tracking
    try:
        return render_message(
            template,
            package_desc=package_desc,
            buyer_username=group.buyer_username,
            tracking_number=(tracking.tracking_number if tracking else "") or "",
            carrier=(tracking.carrier_code if tracking else "") or "",
        )
    except DraftError as exc:
        print(f"  can't draft this message: {exc}")
        return None


def _choose_variant(current: str) -> str:
    for number, desc in enumerate(PACKAGE_DESCS, start=1):
        marker = "  (current)" if desc == current else ""
        print(f"  {number}) {desc}{marker}")
    try:
        raw = input("  variant number (or type your own, e.g. 'the envelope'): ").strip()
    except EOFError:
        return current
    if raw.isdigit() and 1 <= int(raw) <= len(PACKAGE_DESCS):
        return PACKAGE_DESCS[int(raw) - 1]
    return raw or current


def _edit_text(current: str) -> str:
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        print("  $EDITOR is not set — type a replacement (single line, blank keeps current):")
        try:
            line = input("  > ").strip()
        except EOFError:
            line = ""
        return line or current
    fd, path = tempfile.mkstemp(suffix=".txt", text=True)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(current)
        subprocess.run([*shlex.split(editor), path], check=False)
        edited = Path(path).read_text().strip()
    finally:
        os.unlink(path)
    return edited or current


def _send(
    group: BuyerGroup,
    message: str,
    client: EbayClient,
    state: State,
    config: Config,
    dry_run: bool,
    counts: dict,
) -> None:
    if dry_run:
        print(f"  DRY RUN — would send to {group.buyer_username}")
        counts["dry-run"] += 1
        return
    items = group.line_items
    legacy_item_id = items[0].legacy_item_id if len(items) == 1 else None
    while True:
        try:
            message_id = client.send_message(
                message,
                group.buyer_username,
                legacy_item_id=legacy_item_id,
                email_copy=config.email_copy_to_sender,
            )
        except EbayApiError as exc:
            print(f"  send failed: {exc}")
            try:
                retry = input("  [r]etry  [k]skip > ").strip().lower()
            except EOFError:
                retry = "k"
            if retry == "r":
                continue
            counts["skipped"] += 1
            return
        state.mark_sent(group.order_ids, group.buyer_username, message_id)
        counts["sent"] += 1
        suffix = f" (message {message_id})" if message_id else ""
        print(f"  sent to {group.buyer_username}{suffix}")
        return
