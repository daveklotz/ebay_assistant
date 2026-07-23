"""Order domain model: fetch, parse, and group eBay orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .config import parse_datetime
from .ebay_client import EbayClient


@dataclass
class LineItem:
    title: str
    quantity: int
    legacy_item_id: str | None = None
    fulfillment_status: str = ""


@dataclass
class Fulfillment:
    tracking_number: str | None = None
    carrier_code: str | None = None
    shipped_date: datetime | None = None


@dataclass
class Order:
    order_id: str
    buyer_username: str
    creation_date: datetime | None
    line_items: list[LineItem]
    fulfillments: list[Fulfillment] = field(default_factory=list)

    @property
    def has_label(self) -> bool:
        return bool(self.fulfillments)

    @property
    def label_date(self) -> datetime | None:
        dates = [f.shipped_date for f in self.fulfillments if f.shipped_date]
        return max(dates) if dates else None


@dataclass
class BuyerGroup:
    """All pending orders for one buyer — combined shipping gets one message."""

    buyer_username: str
    orders: list[Order]

    @property
    def line_items(self) -> list[LineItem]:
        return [item for order in self.orders for item in order.line_items]

    @property
    def order_ids(self) -> list[str]:
        return [order.order_id for order in self.orders]

    @property
    def first_tracking(self) -> Fulfillment | None:
        for order in self.orders:
            for fulfillment in order.fulfillments:
                if fulfillment.tracking_number:
                    return fulfillment
        return None


def parse_order(raw: dict) -> Order:
    line_items = [
        LineItem(
            title=item.get("title", "(unknown item)"),
            quantity=int(item.get("quantity", 1)),
            legacy_item_id=item.get("legacyItemId"),
            fulfillment_status=item.get("lineItemFulfillmentStatus", ""),
        )
        for item in raw.get("lineItems", [])
    ]
    return Order(
        order_id=raw["orderId"],
        buyer_username=raw.get("buyer", {}).get("username", ""),
        creation_date=parse_datetime(raw.get("creationDate")),
        line_items=line_items,
    )


def parse_fulfillment(raw: dict) -> Fulfillment:
    return Fulfillment(
        tracking_number=raw.get("shipmentTrackingNumber"),
        carrier_code=raw.get("shippingCarrierCode"),
        shipped_date=parse_datetime(raw.get("shippedDate")),
    )


def fetch_labeled_orders(
    client: EbayClient, days_back: int, labeled_only: bool = True
) -> tuple[list[Order], list[Order], list[Order]]:
    """Return (labeled within the window, unlabeled, labeled before the window).

    The API can only be queried by lastmodifieddate, which also moves on
    payment, delivery-scan, and refund noise — so the label's own creation
    date (shippedDate) decides which bucket an order lands in. Orders whose
    fulfillment has no shippedDate count as recent rather than silently
    disappearing.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    recent: list[Order] = []
    unlabeled: list[Order] = []
    earlier: list[Order] = []
    for raw in client.get_orders(since, labeled_only=labeled_only):
        order = parse_order(raw)
        order.fulfillments = [
            parse_fulfillment(f)
            for f in client.get_shipping_fulfillments(order.order_id)
        ]
        if not order.has_label:
            unlabeled.append(order)
        elif order.label_date and order.label_date < since:
            earlier.append(order)
        else:
            recent.append(order)
    return recent, unlabeled, earlier


def group_by_buyer(orders: list[Order]) -> list[BuyerGroup]:
    by_buyer: dict[str, list[Order]] = {}
    for order in orders:
        by_buyer.setdefault(order.buyer_username, []).append(order)
    return [
        BuyerGroup(buyer, sorted(buyer_orders, key=lambda o: o.order_id))
        for buyer, buyer_orders in sorted(by_buyer.items())
    ]
