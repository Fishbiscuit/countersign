"""The sandbox backend against PayPal's recorded answers, with no network."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from countersign.paypal import sandbox
from countersign.paypal.sandbox import SandboxBackend
from countersign.paypal.types import PayPalError, PayPalUnavailable

BATCH = "5RGBPUYM5T6LL"
BATCH_URL = f"https://api.sandbox.paypal.com/v1/payments/payouts/{BATCH}"
REPEATED_BATCH = {
    "name": "USER_BUSINESS_ERROR",
    "message": "User business error.",
    "debug_id": "f116663a4b785",
    "information_link": "https://developer.paypal.com/docs/api/payments.payouts-batch/#errors",
    "details": [
        {
            "field": "SENDER_BATCH_ID",
            "location": "body",
            "issue": "Batch with given sender_batch_id already exists",
            "link": [{"href": BATCH_URL, "rel": "self", "method": "GET", "encType": "application/json"}],
        }
    ],
    "links": [],
}
ORIGINAL_BATCH = {"batch_header": {"payout_batch_id": BATCH, "batch_status": "SUCCESS"}, "items": [{}]}


class FakePayPal:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, *responses: httpx.Response):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        monkeypatch.setattr(sandbox.httpx, "request", self.request)
        monkeypatch.setattr(SandboxBackend, "_access_token", lambda _: "test-token")

    def request(self, method: str, url: str, **_: Any) -> httpx.Response:
        self.calls.append((method, url.removeprefix(sandbox.SANDBOX_API)))
        return self.responses.pop(0)


def send_payout() -> Any:
    return SandboxBackend("id", "secret").payout("a@example.com", "5.00", "SGD", "cs-request", "ref", None)


def test_a_repeated_payout_returns_the_batch_that_already_paid(monkeypatch):
    paypal = FakePayPal(monkeypatch, httpx.Response(400, json=REPEATED_BATCH), httpx.Response(200, json=ORIGINAL_BATCH))
    result = send_payout()
    assert (result.paypal_id, result.status, result.amount, result.currency) == (BATCH, "SUCCESS", "5.00", "SGD")
    assert paypal.calls == [("POST", "/v1/payments/payouts"), ("GET", f"/v1/payments/payouts/{BATCH}")]


def test_a_payout_refused_for_another_reason_stays_refused(monkeypatch):
    refused = {"name": "INSUFFICIENT_FUNDS", "message": "Sender does not have sufficient funds."}
    paypal = FakePayPal(monkeypatch, httpx.Response(422, json=refused))
    with pytest.raises(PayPalError) as error:
        send_payout()
    assert error.value.name == "INSUFFICIENT_FUNDS"
    assert len(paypal.calls) == 1


@pytest.mark.parametrize(
    "responses",
    [
        pytest.param(
            [httpx.Response(400, json=REPEATED_BATCH), httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})],
            id="batch-unreadable",
        ),
        pytest.param(
            [httpx.Response(400, json={**REPEATED_BATCH, "details": [{"field": "SENDER_BATCH_ID"}]})],
            id="no-link",
        ),
    ],
)
def test_a_repeated_payout_never_reads_as_a_refusal(monkeypatch, responses):
    """PayPal already has this batch, so "refused, nothing was paid" would be false even if it can't be read back."""
    FakePayPal(monkeypatch, *responses)
    with pytest.raises(PayPalUnavailable):
        send_payout()
