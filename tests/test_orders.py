from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ebay_assistant.ebay_client import build_orders_filter
from ebay_assistant.orders import (
    LineItem,
    Order,
    fetch_labeled_orders,
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


class FakeClient:
    """Duck-typed EbayClient for fetch tests."""

    def __init__(self, raw_orders, fulfillments_by_order):
        self._raw_orders = raw_orders
        self._fulfillments = fulfillments_by_order

    def get_orders(self, since, labeled_only=True):
        return self._raw_orders

    def get_shipping_fulfillments(self, order_id):
        return self._fulfillments.get(order_id, [])


def _raw_order(order_id):
    return {
        "orderId": order_id,
        "buyer": {"username": "buyer"},
        "lineItems": [{"title": "Card", "quantity": 1}],
    }


def _raw_label(shipped_date):
    return {
        "shipmentTrackingNumber": "9400",
        "shippingCarrierCode": "USPS",
        "shippedDate": shipped_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }


def test_fetch_buckets_by_label_date():
    now = datetime.now(timezone.utc)
    client = FakeClient(
        [_raw_order("fresh"), _raw_order("stale"), _raw_order("nolabel")],
        {
            "fresh": [_raw_label(now - timedelta(days=1))],
            "stale": [_raw_label(now - timedelta(days=10))],
        },
    )
    recent, unlabeled, earlier = fetch_labeled_orders(client, days_back=7)
    assert [o.order_id for o in recent] == ["fresh"]
    assert [o.order_id for o in unlabeled] == ["nolabel"]
    assert [o.order_id for o in earlier] == ["stale"]


def test_fetch_keeps_undated_labels_as_recent():
    client = FakeClient(
        [_raw_order("undated")],
        {"undated": [{"shipmentTrackingNumber": "9400"}]},
    )
    recent, unlabeled, earlier = fetch_labeled_orders(client, days_back=7)
    assert [o.order_id for o in recent] == ["undated"]
    assert not unlabeled
    assert not earlier


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
