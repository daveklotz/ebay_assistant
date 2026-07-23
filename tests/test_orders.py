from __future__ import annotations

from datetime import datetime, timezone

from ebay_assistant.ebay_client import build_orders_filter
from ebay_assistant.orders import (
    LineItem,
    Order,
    group_by_buyer,
    parse_fulfillment,
    parse_order,
)


def test_parse_order(raw_order_single):
    order = parse_order(raw_order_single)
    assert order.order_id == "12-34567-89012"
    assert order.buyer_username == "cardfan_88"
    assert order.creation_date == datetime(2026, 7, 20, 14, 23, 1, tzinfo=timezone.utc)
    assert len(order.line_items) == 1
    item = order.line_items[0]
    assert item.title == "2023 Topps Chrome Jordan Walker RC #142"
    assert item.quantity == 1
    assert item.legacy_item_id == "256789012345"
    assert not order.has_label


def test_parse_fulfillment(raw_fulfillment):
    fulfillment = parse_fulfillment(raw_fulfillment)
    assert fulfillment.tracking_number == "9400111899223344556677"
    assert fulfillment.carrier_code == "USPS"
    assert fulfillment.shipped_date == datetime(
        2026, 7, 22, 15, 4, 5, tzinfo=timezone.utc
    )


def test_order_label_date(raw_order_single, raw_fulfillment):
    order = parse_order(raw_order_single)
    order.fulfillments = [parse_fulfillment(raw_fulfillment)]
    assert order.has_label
    assert order.label_date == datetime(2026, 7, 22, 15, 4, 5, tzinfo=timezone.utc)


def _order(order_id: str, buyer: str) -> Order:
    return Order(
        order_id=order_id,
        buyer_username=buyer,
        creation_date=None,
        line_items=[LineItem(title="Card", quantity=1)],
    )


def test_group_by_buyer_combines_orders():
    groups = group_by_buyer([_order("2", "beta"), _order("1", "alpha"), _order("3", "alpha")])
    assert [g.buyer_username for g in groups] == ["alpha", "beta"]
    assert groups[0].order_ids == ["1", "3"]
    assert len(groups[0].line_items) == 2


def test_build_orders_filter_encoding():
    since = datetime(2026, 7, 16, tzinfo=timezone.utc)
    assert build_orders_filter(since) == (
        "lastmodifieddate:%5B2026-07-16T00:00:00.000Z..%5D,"
        "orderfulfillmentstatus:%7BFULFILLED%7CIN_PROGRESS%7D"
    )


def test_build_orders_filter_without_status():
    since = datetime(2026, 7, 16, tzinfo=timezone.utc)
    assert build_orders_filter(since, labeled_only=False) == (
        "lastmodifieddate:%5B2026-07-16T00:00:00.000Z..%5D"
    )
