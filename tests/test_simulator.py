from decimal import Decimal

import pytest

from countersign.paypal.simulator import SimulatedBackend
from countersign.paypal.types import PayPalError, PayPalUnavailable


@pytest.fixture
def sim(tmp_path):
    return SimulatedBackend(tmp_path / "sim.db")


def payment(sim, amount="50.00"):
    checkout = sim.create_checkout(amount, "USD", "test")
    return sim.capture_checkout(checkout.order_id).capture_id


def test_same_request_id_never_refunds_twice(sim):
    capture = payment(sim)
    first = sim.refund(capture, "10.00", "USD", "req-1", None)
    again = sim.refund(capture, "10.00", "USD", "req-1", None)
    assert first.paypal_id == again.paypal_id
    assert sim.get_payment(capture).refunded == Decimal("10.00")


def test_fresh_request_ids_do_refund_twice(sim):
    capture = payment(sim)
    sim.refund(capture, "10.00", "USD", "a", None)
    sim.refund(capture, "10.00", "USD", "b", None)
    assert sim.get_payment(capture).refunded == Decimal("20.00")


def test_cannot_refund_more_than_captured(sim):
    capture = payment(sim, "20.00")
    with pytest.raises(PayPalError) as error:
        sim.refund(capture, "25.00", "USD", "req", None)
    assert "REFUND_AMOUNT_EXCEEDED" in error.value.message


def test_lost_response_commits_and_retry_with_same_id_returns_it(sim):
    capture = payment(sim)
    sim.inject("refund", "lost_response")
    with pytest.raises(PayPalUnavailable):
        sim.refund(capture, "10.00", "USD", "req-lost", None)
    assert sim.get_payment(capture).refunded == Decimal("10.00")
    retried = sim.refund(capture, "10.00", "USD", "req-lost", None)
    assert retried.status == "COMPLETED"
    assert sim.get_payment(capture).refunded == Decimal("10.00")


def test_server_error_moves_nothing_and_is_used_up(sim):
    capture = payment(sim)
    sim.inject("refund", "server_error")
    with pytest.raises(PayPalError):
        sim.refund(capture, "10.00", "USD", "req-err", None)
    assert sim.get_payment(capture).refunded == Decimal("0")
    assert sim.refund(capture, "10.00", "USD", "req-err", None).status == "COMPLETED"


def test_payout_idempotency(sim):
    first = sim.payout("a@example.com", "5.00", "USD", "pay-1", "ref", None)
    again = sim.payout("a@example.com", "5.00", "USD", "pay-1", "ref", None)
    assert first.paypal_id == again.paypal_id
    assert sim.money_moved()["payouts"] == {"count": 1, "total": "5.00"}
