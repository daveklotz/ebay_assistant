from __future__ import annotations

import copy

import pytest

RAW_ORDER_SINGLE = {
    "orderId": "12-34567-89012",
    "creationDate": "2026-07-20T14:23:01.000Z",
    "orderFulfillmentStatus": "FULFILLED",
    "buyer": {"username": "cardfan_88"},
    "lineItems": [
        {
            "lineItemId": "111",
            "legacyItemId": "256789012345",
            "title": "2023 Topps Chrome Jordan Walker RC #142",
            "quantity": 1,
            "lineItemFulfillmentStatus": "FULFILLED",
        }
    ],
}

RAW_FULFILLMENT = {
    "fulfillmentId": "9400111899223344556677",
    "shipmentTrackingNumber": "9400111899223344556677",
    "shippingCarrierCode": "USPS",
    "shippedDate": "2026-07-22T15:04:05.000Z",
    "lineItems": [{"lineItemId": "111"}],
}


@pytest.fixture
def raw_order_single():
    return copy.deepcopy(RAW_ORDER_SINGLE)


@pytest.fixture
def raw_fulfillment():
    return copy.deepcopy(RAW_FULFILLMENT)
