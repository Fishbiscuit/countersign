"""Exact money parsing. Amounts travel as strings and are compared as Decimals."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

AMOUNT_PATTERN = re.compile(r"^\d{1,9}(\.\d{1,2})?$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


class MoneyError(ValueError):
    pass


def parse_amount(value: object) -> Decimal:
    text = str(value).strip()
    if not AMOUNT_PATTERN.match(text):
        raise MoneyError(f"Amount must be a positive number with at most 2 decimals, got {value!r}")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise MoneyError(f"Amount is not a number: {value!r}") from exc
    if amount <= 0:
        raise MoneyError(f"Amount must be greater than zero, got {text}")
    return amount


def parse_currency(value: object) -> str:
    text = str(value).strip().upper()
    if not CURRENCY_PATTERN.match(text):
        raise MoneyError(f"Currency must be a 3-letter ISO code, got {value!r}")
    return text


def fmt(amount: Decimal) -> str:
    return f"{amount:.2f}"
