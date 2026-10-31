from decimal import Decimal

import pytest

from countersign.money import MoneyError
from countersign.policy import DEFAULT_MANDATE, Facts, MoveRequest, evaluate, normalize_mandate


def facts(**overrides):
    base = {
        "agent_active": True,
        "mandate": normalize_mandate({**DEFAULT_MANDATE, "payout_allowlist": ["friend@example.com"]}),
        "spent_today": Decimal("0"),
        "moves_last_minute": 0,
        "refundable": Decimal("100.00"),
    }
    return Facts(**{**base, **overrides})


def refund(amount: str) -> MoveRequest:
    return MoveRequest("agt_1", "refund", Decimal(amount), "USD", "CAP1", "T-1")


def payout(amount: str, to: str = "friend@example.com") -> MoveRequest:
    return MoveRequest("agt_1", "payout", Decimal(amount), "USD", to, "ref-1")


def rule(decision, name):
    return next(r for r in decision.rules if r.rule == name)


def test_small_refund_passes():
    assert evaluate(refund("12.00"), facts()).outcome == "pass"


def test_refund_over_auto_limit_is_held():
    decision = evaluate(refund("40.00"), facts())
    assert decision.outcome == "hold"
    assert rule(decision, "amount.auto_approve").outcome == "hold"


def test_refund_over_hard_limit_is_blocked():
    assert evaluate(refund("600.00"), facts(refundable=Decimal("900"))).outcome == "block"


def test_refund_beyond_refundable_is_blocked():
    decision = evaluate(refund("20.00"), facts(refundable=Decimal("10.00")))
    assert decision.outcome == "block"
    assert rule(decision, "refund.verified").outcome == "block"


def test_unverifiable_payment_is_held_not_allowed():
    decision = evaluate(refund("5.00"), facts(refundable=None, refundable_error="timeout"))
    assert decision.outcome == "hold"


def test_disallowed_action_is_blocked():
    mandate = normalize_mandate({**DEFAULT_MANDATE, "allowed_actions": ["refund"]})
    assert evaluate(payout("5.00"), facts(mandate=mandate)).outcome == "block"


def test_new_payout_recipient_is_held_and_allowlisted_passes():
    assert evaluate(payout("5.00", "stranger@example.com"), facts()).outcome == "hold"
    assert evaluate(payout("5.00"), facts()).outcome == "pass"


def test_daily_limit_holds():
    decision = evaluate(refund("20.00"), facts(spent_today=Decimal("190.00")))
    assert rule(decision, "budget.daily").outcome == "hold"


def test_velocity_holds():
    decision = evaluate(payout("5.00"), facts(moves_last_minute=5))
    assert rule(decision, "velocity").outcome == "hold"


def test_untrusted_context_lowers_the_auto_limit():
    seen = facts(untrusted_sources=["demo_shop_read_ticket"], private_data_seen=True)
    assert evaluate(refund("12.00"), seen).outcome == "pass"
    held = evaluate(refund("20.00"), seen)
    assert held.outcome == "hold"
    assert "untrusted content" in rule(held, "context.lethal_trifecta").detail


def test_inactive_agent_is_blocked():
    assert evaluate(refund("1.00"), facts(agent_active=False)).outcome == "block"


@pytest.mark.parametrize(
    "bad",
    [
        {"auto_approve_up_to": "600.00"},
        {"daily_limit": "-5"},
        {"velocity_per_minute": 0},
        {"untrusted_auto_approve_up_to": "100.00"},
        {"currencies": ["dollars"]},
    ],
)
def test_malformed_mandates_are_rejected(bad):
    with pytest.raises((MoneyError, ValueError)):
        normalize_mandate({**DEFAULT_MANDATE, **bad})


def test_second_move_to_same_target_is_held_as_possible_duplicate():
    decision = evaluate(payout("10.00"), facts(recent_moves_to_target=1))
    assert decision.outcome == "hold"
    assert rule(decision, "duplicate.same_target").outcome == "hold"
    off = normalize_mandate({**DEFAULT_MANDATE, "payout_allowlist": ["friend@example.com"], "repeat_target_window_minutes": 0})
    assert evaluate(payout("10.00"), facts(mandate=off, recent_moves_to_target=1)).outcome == "pass"


def test_a_move_another_agent_already_paid_is_refused():
    decision = evaluate(refund("12.00"), facts(same_move_paid_by="Claude Code"))
    assert decision.outcome == "block"
    assert "Claude Code already paid" in rule(decision, "duplicate.same_reference").detail


def test_another_amount_under_a_used_reference_waits_for_a_human_whatever_the_duplicate_window():
    off = normalize_mandate({**DEFAULT_MANDATE, "repeat_target_window_minutes": 0})
    decision = evaluate(refund("5.00"), facts(mandate=off, same_reference_moves=1))
    assert decision.outcome == "hold"
    assert rule(decision, "duplicate.same_reference").outcome == "hold"
