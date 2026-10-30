"""PayPal Sandbox backend: real PayPal REST API calls, test money only.

The base URL is fixed to the sandbox. There is no setting that points this at
live PayPal.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

import httpx

from countersign.paypal.types import Checkout, MoneyResult, PaymentInfo, PayPalError, PayPalUnavailable

SANDBOX_API = "https://api-m.sandbox.paypal.com"


class SandboxBackend:
    name = "sandbox"
    label = "PayPal Sandbox"

    def __init__(self, client_id: str, client_secret: str, timeout_s: float = 30.0):
        self._auth = (client_id, client_secret)
        self._timeout = timeout_s
        self._token: str | None = None
        self._token_expires_at = 0.0

    # Transport ----------------------------------------------------------------

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        try:
            response = httpx.post(
                f"{SANDBOX_API}/v1/oauth2/token",
                auth=self._auth,
                data={"grant_type": "client_credentials"},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise PayPalUnavailable(f"PayPal token request failed: {exc}") from exc
        if response.status_code != 200:
            raise _error(response)
        data = response.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + float(data["expires_in"])
        return self._token

    def call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        request_id: str | None = None,
        mock_code: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        if mock_code:
            headers["PayPal-Mock-Response"] = json.dumps({"mock_application_codes": mock_code})
        try:
            response = httpx.request(method, SANDBOX_API + path, headers=headers, json=body, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise PayPalUnavailable(f"PayPal did not answer in {self._timeout:.0f}s") from exc
        except httpx.HTTPError as exc:
            raise PayPalUnavailable(f"Could not reach PayPal: {exc}") from exc
        if response.status_code >= 400:
            raise _error(response)
        return response.json() if response.content else {}

    # Payments -----------------------------------------------------------------

    def get_payment(self, capture_id: str) -> PaymentInfo:
        capture = self.call("GET", f"/v2/payments/captures/{capture_id}")
        amount = Decimal(capture["amount"]["value"])
        currency = capture["amount"]["currency_code"]
        refunded = Decimal("0")
        order_id = capture.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
        if order_id:
            order = self.call("GET", f"/v2/checkout/orders/{order_id}")
            for unit in order.get("purchase_units", []):
                for refund in unit.get("payments", {}).get("refunds", []):
                    if refund.get("status") in ("COMPLETED", "PENDING"):
                        refunded += Decimal(refund["amount"]["value"])
        elif capture["status"] == "REFUNDED":
            refunded = amount
        return PaymentInfo(capture["id"], capture["status"], amount, currency, refunded)

    def refund(self, capture_id: str, amount: str, currency: str, request_id: str, note: str | None) -> MoneyResult:
        body: dict[str, Any] = {"amount": {"value": amount, "currency_code": currency}}
        if note:
            body["note_to_payer"] = note[:255]
        data = self.call("POST", f"/v2/payments/captures/{capture_id}/refund", body, request_id=request_id)
        return MoneyResult(data["id"], data["status"], data["amount"]["value"], data["amount"]["currency_code"], raw=data)

    def payout(self, email: str, amount: str, currency: str, request_id: str, reference: str, note: str | None) -> MoneyResult:
        body = {
            "sender_batch_header": {
                "sender_batch_id": request_id[:30],
                "email_subject": "You have a payment",
                "recipient_type": "EMAIL",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "receiver": email,
                    "amount": {"value": amount, "currency": currency},
                    "note": (note or f"Countersign payout {reference}")[:4000],
                    "sender_item_id": reference[:63] or request_id[:30],
                }
            ],
        }
        try:
            data = self.call("POST", "/v1/payments/payouts", body, request_id=request_id)
        except PayPalError as exc:
            if not _repeats_batch(exc):
                raise
            data = self._original_batch(exc)
        batch = data["batch_header"]
        return MoneyResult(batch["payout_batch_id"], batch["batch_status"], amount, currency, raw=data)

    def _original_batch(self, refused: PayPalError) -> dict[str, Any]:
        """PayPal refuses a repeated payout batch instead of replaying it, and links the batch that already paid."""
        links = [link["href"] for detail in refused.details for link in detail.get("link", [])]
        if not links:
            raise PayPalUnavailable("PayPal says this payout batch already exists but did not link it")
        try:
            return self.call("GET", f"/v1/payments/payouts/{links[0].rsplit('/', 1)[-1]}")
        except PayPalError as exc:
            raise PayPalUnavailable(f"PayPal says this payout batch already exists but would not show it: {exc}") from exc

    def money_status(self, action: str, paypal_id: str) -> str:
        if action == "refund":
            return self.call("GET", f"/v2/payments/refunds/{paypal_id}")["status"]
        batch = self.call("GET", f"/v1/payments/payouts/{paypal_id}")
        items = batch.get("items") or []
        return items[0]["transaction_status"] if items else batch["batch_header"]["batch_status"]

    # Checkout (used to create real sandbox payments for demos and tests) ----------

    def create_checkout(self, amount: str, currency: str, description: str) -> Checkout:
        data = self.call(
            "POST",
            "/v2/checkout/orders",
            {
                "intent": "CAPTURE",
                "purchase_units": [{"amount": {"currency_code": currency, "value": amount}, "description": description[:127]}],
                "payment_source": {
                    "paypal": {
                        "experience_context": {
                            "return_url": "https://example.com/countersign/return",
                            "cancel_url": "https://example.com/countersign/cancel",
                            "user_action": "PAY_NOW",
                            "shipping_preference": "NO_SHIPPING",
                        }
                    }
                },
            },
        )
        link = next((x["href"] for x in data.get("links", []) if x["rel"] in ("payer-action", "approve")), None)
        return Checkout(data["id"], data["status"], link)

    def capture_checkout(self, order_id: str) -> Checkout:
        status = self.call("GET", f"/v2/checkout/orders/{order_id}")["status"]
        if status != "APPROVED":
            return Checkout(order_id, status, None)
        data = self.call("POST", f"/v2/checkout/orders/{order_id}/capture", {}, request_id=f"cs-capture-{order_id}")
        capture = data["purchase_units"][0]["payments"]["captures"][0]
        return Checkout(order_id, data["status"], None, capture["id"])

    # Webhooks -----------------------------------------------------------------

    def verify_webhook(self, headers: dict[str, str], event: dict[str, Any], webhook_id: str) -> bool:
        body = {
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": webhook_id,
            "webhook_event": event,
        }
        return self.call("POST", "/v1/notifications/verify-webhook-signature", body).get("verification_status") == "SUCCESS"


def _repeats_batch(exc: PayPalError) -> bool:
    return exc.name == "USER_BUSINESS_ERROR" and any(d.get("field") == "SENDER_BATCH_ID" for d in exc.details or [])


def _error(response: httpx.Response) -> PayPalError:
    try:
        data = response.json()
    except ValueError:
        data = {"name": "UNKNOWN", "message": response.text[:300]}
    name = data.get("name") or data.get("error") or "UNKNOWN"
    message = data.get("message") or data.get("error_description") or ""
    details = data.get("details")
    if details and isinstance(details, list):
        issue = details[0].get("issue") or details[0].get("description")
        if issue:
            message = f"{message} ({issue})".strip()
    return PayPalError(response.status_code, name, message, response.headers.get("paypal-debug-id"), details)
