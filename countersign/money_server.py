"""Countersign money tools, served over MCP stdio behind the gateway.

These are the only tools that move money. Each one refuses to run unless the
gateway stamped an intent that Countersign allowed or a human approved, and the
intent matches the arguments exactly. PayPal sees the same request and batch
IDs on every attempt at an intent, so a retry after a lost response can never
pay twice.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from countersign.money import fmt, parse_amount, parse_currency
from countersign.paypal import make_backend
from countersign.paypal.types import PayPalError, PayPalUnavailable
from countersign.settings import load_settings
from countersign.store import Intent, Store

settings = load_settings()
store = Store(settings.db_path)
backend = make_backend(settings)

mcp = FastMCP(
    "countersign",
    instructions=(
        "Countersign moves money through PayPal on behalf of a person or business. Every money move has a "
        "`reference`: a stable ID such as a ticket number. Retrying with the same arguments never pays twice. "
        "Some moves are held until a human approves them; if a call says a move is held, tell the person, "
        "and retry with exactly the same arguments after they approve. Never invent references or amounts "
        "that the person did not ask for."
    ),
)


class MoneyMoveError(Exception):
    pass


def _execute(intent_id: str, action: str, target: str, amount: str, currency: str, reference: str, note: str) -> dict[str, Any]:
    intent = store.get_intent(intent_id) if intent_id else None
    if intent is None:
        raise MoneyMoveError("This tool only runs through the Countersign gateway. Nothing was paid.")
    expected = (action, target.strip().lower(), fmt(parse_amount(amount)), parse_currency(currency), reference.strip())
    actual = (intent.action, intent.target.lower(), intent.amount, intent.currency, intent.reference)
    if expected != actual:
        raise MoneyMoveError("The approved money move does not match these arguments. Nothing was paid.")
    if intent.status == "executed":
        return _receipt(intent, already_done=True)
    if intent.status not in ("allowed", "approved", "executing", "failed"):
        raise MoneyMoveError(f"This money move is {intent.status}, not approved. Nothing was paid.")

    store.update_intent(intent.id, "execution_started", status="executing")
    try:
        if action == "refund":
            result = backend.refund(intent.target, intent.amount, intent.currency, intent.request_id, note or None)
        else:
            result = backend.payout(
                intent.target, intent.amount, intent.currency, intent.request_id, intent.reference, note or None
            )
    except PayPalError as exc:
        if exc.status >= 500:
            raise _unconfirmed(intent, exc, exc.debug_id) from exc
        store.update_intent(
            intent.id, "execution_failed", status="failed", error=f"{exc.name}: {exc.message}", paypal_debug_id=exc.debug_id
        )
        raise MoneyMoveError(
            f"PayPal refused this {action}: {exc.name} {exc.message} (debug id {exc.debug_id}). Nothing was paid."
        ) from exc
    except PayPalUnavailable as exc:
        raise _unconfirmed(intent, exc) from exc

    done = store.update_intent(
        intent.id,
        "execution_succeeded",
        status="executed",
        paypal_id=result.paypal_id,
        paypal_status=result.status,
        paypal_debug_id=result.debug_id,
        error=None,
        result={
            "status": "executed",
            "intent": intent.id,
            "action": action,
            "amount": intent.amount,
            "currency": intent.currency,
            "target": intent.target,
            "reference": intent.reference,
            "paypal_id": result.paypal_id,
            "paypal_status": result.status,
            "backend": backend.label,
        },
    )
    return _receipt(done)


def _unconfirmed(intent: Intent, exc: Exception, debug_id: str | None = None) -> MoneyMoveError:
    """The money may have moved, so the intent stays executing and the agent must not be told nothing was paid."""
    store.update_intent(intent.id, "execution_unconfirmed", error=str(exc), paypal_debug_id=debug_id)
    return MoneyMoveError(
        f"PayPal did not confirm this {intent.action} ({exc}). It is safe to retry with exactly the same arguments: "
        "Countersign sends PayPal the same IDs, so it cannot pay twice."
    )


def _receipt(intent: Intent, already_done: bool = False) -> dict[str, Any]:
    receipt = dict(intent.result or {})
    receipt["attempts"] = intent.attempts
    if already_done:
        receipt["countersign_note"] = "Already done earlier. Nothing was paid twice."
    return receipt


@mcp.tool()
def refund_payment(
    capture_id: str,
    amount: str,
    reference: str,
    currency: str = "USD",
    reason: str = "",
    countersign_intent: str = "",
) -> dict[str, Any]:
    """Refund part or all of a captured PayPal payment to the buyer.

    capture_id: the PayPal capture ID of the original payment.
    amount: decimal string, e.g. "12.50". Never more than the person asked for.
    reference: a stable ID for this refund, e.g. the support ticket number. The same reference is never paid twice.
    reason: short note shown to the buyer.
    Larger or unusual refunds wait for a human to countersign.
    """
    return _execute(countersign_intent, "refund", capture_id, amount, currency, reference, reason)


@mcp.tool()
def send_payout(
    recipient_email: str,
    amount: str,
    reference: str,
    currency: str = "USD",
    note: str = "",
    countersign_intent: str = "",
) -> dict[str, Any]:
    """Send money to someone's PayPal account by email (a PayPal Payout).

    recipient_email: who receives the money.
    amount: decimal string, e.g. "20.00".
    reference: a stable ID for this transfer, e.g. "split-dinner-2026-11-02". The same reference is never paid twice.
    note: message shown to the recipient.
    New recipients and larger amounts wait for a human to countersign.
    """
    return _execute(countersign_intent, "payout", recipient_email, amount, currency, reference, note)


@mcp.tool()
def get_payment(capture_id: str) -> dict[str, Any]:
    """Look up a captured PayPal payment: amount, status and how much can still be refunded."""
    info = backend.get_payment(capture_id)
    return {
        "capture_id": info.capture_id,
        "status": info.status,
        "amount": fmt(info.amount),
        "currency": info.currency,
        "refunded": fmt(info.refunded),
        "refundable": fmt(info.refundable),
        "backend": backend.label,
    }


@mcp.tool()
def check_money_move(intent_id: str) -> dict[str, Any]:
    """Check a money move Countersign held or executed, by its intent ID (cs_...)."""
    intent = store.get_intent(intent_id)
    if intent is None:
        return {"intent": intent_id, "status": "unknown"}
    return {
        "intent": intent.id,
        "status": intent.status,
        "action": intent.action,
        "amount": intent.amount,
        "currency": intent.currency,
        "target": intent.target,
        "reference": intent.reference,
        "hold_reason": intent.hold_reason,
        "decided_by": intent.decided_by,
        "paypal_id": intent.paypal_id,
        "next_step": {
            "held": "Waiting for a human. Retry with the same arguments after they approve.",
            "expired": "Nobody approved it in time. If the human approves it in Countersign, retry with the same arguments.",
            "approved": "Approved. Retry the original call with the same arguments to execute it.",
            "denied": "A human denied it. Do not retry.",
            "executed": "Done.",
            "failed": "PayPal refused it. Check the error before trying anything else.",
        }.get(intent.status, ""),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
