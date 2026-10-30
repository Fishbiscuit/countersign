"""Shared types for the PayPal backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol


class PayPalError(Exception):
    """PayPal answered with an error. A 4xx moved no money; after a 5xx it may have."""

    def __init__(self, status: int, name: str, message: str, debug_id: str | None = None, details: Any = None):
        self.status = status
        self.name = name
        self.message = message
        self.debug_id = debug_id
        self.details = details
        super().__init__(f"PayPal {status} {name}: {message}")


class PayPalUnavailable(Exception):
    """No answer from PayPal. The money may or may not have moved; retry with the same request id."""


@dataclass
class MoneyResult:
    paypal_id: str
    status: str
    amount: str
    currency: str
    debug_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaymentInfo:
    capture_id: str
    status: str
    amount: Decimal
    currency: str
    refunded: Decimal

    @property
    def refundable(self) -> Decimal:
        return max(self.amount - self.refunded, Decimal("0"))


@dataclass
class Checkout:
    order_id: str
    status: str
    approve_url: str | None
    capture_id: str | None = None


class PaymentsBackend(Protocol):
    name: str
    label: str

    def get_payment(self, capture_id: str) -> PaymentInfo: ...

    def refund(self, capture_id: str, amount: str, currency: str, request_id: str, note: str | None) -> MoneyResult: ...

    def payout(
        self, email: str, amount: str, currency: str, request_id: str, reference: str, note: str | None
    ) -> MoneyResult: ...

    def money_status(self, action: str, paypal_id: str) -> str: ...

    def create_checkout(self, amount: str, currency: str, description: str) -> Checkout: ...

    def capture_checkout(self, order_id: str) -> Checkout: ...
