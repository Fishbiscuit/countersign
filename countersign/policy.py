"""Deterministic money rules, evaluated for every move an agent asks to make.

Each agent has a mandate: what it may do, how much, to whom, and how fast.
Every rule returns pass, hold (a human must countersign) or block. AI never
makes these decisions; it only helps the human read a hold.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Literal

from countersign.money import MoneyError, fmt, parse_amount, parse_currency

ACTIONS = ("refund", "payout")

DEFAULT_MANDATE: dict[str, Any] = {
    "allowed_actions": ["refund", "payout"],
    "currencies": ["USD"],
    "auto_approve_up_to": "25.00",
    "max_per_move": "500.00",
    "daily_limit": "200.00",
    "payout_allowlist": [],
    "velocity_per_minute": 5,
    "repeat_target_window_minutes": 60,
    "untrusted_auto_approve_up_to": "15.00",
}

Outcome = Literal["pass", "hold", "block"]


def normalize_mandate(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Fill defaults and reject malformed limits, so a typo cannot silently widen a mandate."""
    mandate = {**DEFAULT_MANDATE, **(raw or {})}
    actions = [a for a in mandate["allowed_actions"] if a in ACTIONS]
    currencies = [parse_currency(c) for c in mandate["currencies"]] or ["USD"]
    limits = {name: fmt(parse_amount(mandate[name])) for name in ("auto_approve_up_to", "max_per_move", "daily_limit")}
    if Decimal(limits["auto_approve_up_to"]) > Decimal(limits["max_per_move"]):
        raise MoneyError("auto_approve_up_to cannot exceed max_per_move")
    untrusted_limit = Decimal(str(mandate["untrusted_auto_approve_up_to"]).strip() or "0")
    if untrusted_limit < 0 or untrusted_limit > Decimal(limits["auto_approve_up_to"]):
        raise MoneyError("untrusted_auto_approve_up_to must be between 0 and auto_approve_up_to")
    allowlist = sorted({str(email).strip().lower() for email in mandate["payout_allowlist"] if str(email).strip()})
    velocity = int(mandate["velocity_per_minute"])
    if velocity < 1:
        raise MoneyError("velocity_per_minute must be at least 1")
    repeat_window = int(mandate["repeat_target_window_minutes"])
    if repeat_window < 0:
        raise MoneyError("repeat_target_window_minutes cannot be negative")
    return {
        "allowed_actions": actions,
        "currencies": currencies,
        **limits,
        "payout_allowlist": allowlist,
        "velocity_per_minute": velocity,
        "repeat_target_window_minutes": repeat_window,
        "untrusted_auto_approve_up_to": fmt(untrusted_limit),
    }


@dataclass
class MoveRequest:
    agent_id: str
    action: str
    amount: Decimal
    currency: str
    target: str
    reference: str


@dataclass
class Facts:
    agent_active: bool
    mandate: dict[str, Any]
    spent_today: Decimal
    moves_last_minute: int
    recent_moves_to_target: int = 0
    same_reference_moves: int = 0
    same_move_paid_by: str | None = None
    refundable: Decimal | None = None
    refundable_error: str | None = None
    untrusted_sources: list[str] = field(default_factory=list)
    private_data_seen: bool = False


@dataclass
class RuleResult:
    rule: str
    outcome: Outcome
    detail: str


@dataclass
class Decision:
    outcome: Outcome
    rules: list[RuleResult]

    @property
    def reasons(self) -> list[str]:
        return [r.detail for r in self.rules if r.outcome == self.outcome]

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(r) for r in self.rules]


def evaluate(request: MoveRequest, facts: Facts) -> Decision:
    m = facts.mandate
    results: list[RuleResult] = []

    def add(rule: str, outcome: Outcome, detail: str) -> None:
        results.append(RuleResult(rule, outcome, detail))

    if not facts.agent_active:
        add("agent.active", "block", "This agent is paused or unknown in Countersign")
    else:
        add("agent.active", "pass", "Agent is active")

    if request.action not in m["allowed_actions"]:
        add("mandate.action", "block", f"This agent may not make {request.action}s")
    else:
        add("mandate.action", "pass", f"{request.action.capitalize()}s are allowed")

    if request.currency not in m["currencies"]:
        add("mandate.currency", "block", f"{request.currency} is not an allowed currency ({', '.join(m['currencies'])})")
    else:
        add("mandate.currency", "pass", f"{request.currency} allowed")

    max_per_move = Decimal(m["max_per_move"])
    if request.amount > max_per_move:
        add("amount.max_per_move", "block", f"{fmt(request.amount)} is over the hard limit of {fmt(max_per_move)} per move")
    else:
        add("amount.max_per_move", "pass", f"Within the {fmt(max_per_move)} hard limit")

    if request.action == "refund":
        if facts.refundable is None:
            add(
                "refund.verified",
                "hold",
                f"Could not confirm the payment with PayPal: {facts.refundable_error or 'unknown error'}",
            )
        elif request.amount > facts.refundable:
            add(
                "refund.verified",
                "block",
                f"Refund {fmt(request.amount)} exceeds the {fmt(facts.refundable)} still refundable on {request.target}",
            )
        else:
            add("refund.verified", "pass", f"{fmt(facts.refundable)} still refundable on this payment")

    if request.action == "payout":
        if request.target.strip().lower() in m["payout_allowlist"]:
            add("payout.recipient", "pass", f"{request.target} is on this agent's allowlist")
        else:
            add("payout.recipient", "hold", f"First payout to {request.target}: not on this agent's allowlist")

    auto_limit = Decimal(m["auto_approve_up_to"])
    if request.amount > auto_limit:
        add("amount.auto_approve", "hold", f"{fmt(request.amount)} is over the {fmt(auto_limit)} auto-approve limit")
    else:
        add("amount.auto_approve", "pass", f"Under the {fmt(auto_limit)} auto-approve limit")

    daily = Decimal(m["daily_limit"])
    if facts.spent_today + request.amount > daily:
        add(
            "budget.daily",
            "hold",
            f"Would bring the last 24 hours to {fmt(facts.spent_today + request.amount)}, over the {fmt(daily)} limit",
        )
    else:
        add("budget.daily", "pass", f"{fmt(facts.spent_today)} of {fmt(daily)} used in the last 24 hours")

    if facts.moves_last_minute >= m["velocity_per_minute"]:
        add(
            "velocity",
            "hold",
            f"{facts.moves_last_minute} money moves in the last minute (limit {m['velocity_per_minute']}): possible loop",
        )
    else:
        add("velocity", "pass", f"{facts.moves_last_minute} moves in the last minute")

    window = m["repeat_target_window_minutes"]
    if window and facts.recent_moves_to_target > 0:
        add(
            "duplicate.same_target",
            "hold",
            f"Possible duplicate: {facts.recent_moves_to_target} earlier move(s) to {request.target} in the last {window} minutes "
            "under a different reference",
        )
    else:
        add("duplicate.same_target", "pass", "No recent move to this target under another reference")

    if facts.same_move_paid_by:
        add(
            "duplicate.same_reference",
            "block",
            f"{facts.same_move_paid_by} already paid this exact {request.action} under reference {request.reference}, "
            "so a second one is refused",
        )
    elif facts.same_reference_moves:
        add(
            "duplicate.same_reference",
            "hold",
            f"Possible duplicate: {facts.same_reference_moves} other move(s) to {request.target} under reference "
            f"{request.reference}, for a different amount or not finished yet",
        )
    else:
        add("duplicate.same_reference", "pass", "Nothing else to this target under this reference")

    untrusted_limit = Decimal(m["untrusted_auto_approve_up_to"])
    if facts.untrusted_sources:
        sources = ", ".join(sorted(set(facts.untrusted_sources)))
        trifecta = " and private data" if facts.private_data_seen else ""
        if request.amount > untrusted_limit:
            add(
                "context.lethal_trifecta",
                "hold",
                f"Agent read untrusted content ({sources}){trifecta}, and {fmt(request.amount)} is over the "
                f"{fmt(untrusted_limit)} limit that applies after untrusted content",
            )
        else:
            add(
                "context.lethal_trifecta",
                "pass",
                f"Untrusted content read ({sources}), but {fmt(request.amount)} is within the {fmt(untrusted_limit)} limit for that case",
            )
    else:
        add("context.lethal_trifecta", "pass", "No untrusted content in this session")

    if any(r.outcome == "block" for r in results):
        outcome: Outcome = "block"
    elif any(r.outcome == "hold" for r in results):
        outcome = "hold"
    else:
        outcome = "pass"
    return Decision(outcome, results)
