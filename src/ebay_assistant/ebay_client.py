"""Thin HTTP client for the handful of eBay REST calls this tool needs."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import quote

import requests

MAX_ATTEMPTS = 4
BACKOFF_SECONDS = (1, 2, 4)


class EbayApiError(Exception):
    def __init__(
        self, status: int, message: str, errors: list | None = None, body: str = ""
    ):
        super().__init__(message)
        self.status = status
        self.errors = errors or []
        self.body = body


def build_orders_filter(since: datetime, labeled_only: bool = True) -> str:
    since_iso = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    raw = f"lastmodifieddate:[{since_iso}..]"
    if labeled_only:
        raw += ",orderfulfillmentstatus:{FULFILLED|IN_PROGRESS}"
    return quote(raw, safe=":,")


class EbayClient:
    def __init__(self, base_url: str, token_provider: Callable[[], str]):
        self.base_url = base_url.rstrip("/")
        self._token = token_provider
        self._session = requests.Session()

    def get_orders(self, since: datetime, labeled_only: bool = True) -> list[dict]:
        url = (
            f"{self.base_url}/sell/fulfillment/v1/order"
            f"?filter={build_orders_filter(since, labeled_only)}&limit=50"
        )
        orders: list[dict] = []
        while url:
            page = self._request("GET", url)
            orders.extend(page.get("orders", []))
            url = page.get("next")
        return orders

    def count_recent_orders(self) -> int:
        """Cheapest possible authenticated call; used to validate setup."""
        page = self._request("GET", f"{self.base_url}/sell/fulfillment/v1/order?limit=1")
        return int(page.get("total", 0))

    def get_shipping_fulfillments(self, order_id: str) -> list[dict]:
        url = (
            f"{self.base_url}/sell/fulfillment/v1/order/"
            f"{quote(order_id, safe='')}/shipping_fulfillment"
        )
        return self._request("GET", url).get("fulfillments", [])

    def send_message(
        self,
        message_text: str,
        other_party_username: str,
        legacy_item_id: str | None = None,
        email_copy: bool = False,
    ) -> str:
        body: dict = {
            "messageText": message_text,
            "otherPartyUsername": other_party_username,
        }
        if legacy_item_id:
            body["reference"] = {
                "referenceType": "LISTING",
                "referenceId": str(legacy_item_id),
            }
        if email_copy:
            body["emailCopyToSender"] = True
        result = self._request(
            "POST", f"{self.base_url}/commerce/message/v1/send_message", json_body=body
        )
        return str(result.get("messageId", ""))

    def _request(self, method: str, url: str, json_body: dict | None = None) -> dict:
        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                time.sleep(BACKOFF_SECONDS[attempt - 1])
            headers = {
                "Authorization": f"Bearer {self._token()}",
                "Accept": "application/json",
            }
            try:
                resp = self._session.request(
                    method, url, headers=headers, json=json_body, timeout=30
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                continue
            if resp.status_code >= 500:
                last_error = EbayApiError(
                    resp.status_code,
                    f"eBay server error (HTTP {resp.status_code})",
                    body=resp.text[:500],
                )
                continue
            if resp.status_code >= 400:
                raise _client_error(resp)
            if not resp.content:
                return {}
            return resp.json()
        if isinstance(last_error, EbayApiError):
            raise last_error
        raise EbayApiError(0, f"network error after {MAX_ATTEMPTS} attempts: {last_error}")


def _client_error(resp: requests.Response) -> EbayApiError:
    try:
        errors = resp.json().get("errors", [])
    except ValueError:
        errors = []
    details = "; ".join(
        e.get("longMessage") or e.get("message", "")
        for e in errors
        if isinstance(e, dict)
    ).strip("; ")
    message = f"HTTP {resp.status_code}"
    if details:
        message += f": {details}"
    return EbayApiError(resp.status_code, message, errors=errors, body=resp.text[:500])
