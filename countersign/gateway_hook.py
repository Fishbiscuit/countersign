"""Countersign's checkpoint inside the gateway.

The patched Open Edison session tracker calls `guard_call` before any
Countersign tool runs. For money tools it turns the call into an intent,
evaluates the agent's mandate, and either lets it through (stamping the intent
id into the arguments), blocks it, waits for a human, or replays an earlier
result for a retry of the same intent.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from functools import cache
from typing import Any, Literal

from countersign.money import MoneyError, fmt, parse_amount, parse_currency
from countersign.paypal import make_backend
from countersign.paypal.types import PaymentsBackend, PayPalError
from countersign.policy import Facts, MoveRequest, evaluate, normalize_mandate
from countersign.settings import Settings, load_settings
from countersign.store import Intent, Store, fingerprint, iso, now

SERVER_PREFIX = "countersign_"
AGENT_HEADER = "x-countersign-agent"
INTENT_ARG = "countersign_intent"
MONEY_TOOLS = {"refund_payment": "refund", "send_payout": "payout"}
TARGET_ARG = {"refund": "capture_id", "payout": "recipient_email"}
POLL_SECONDS = 0.4


def sign_agent(agent_id: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), agent_id.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{agent_id}.{digest}"


def verify_agent(header_value: str | None, secret: str) -> str | None:
    if not header_value or "." not in header_value:
        return None
    agent_id, _ = header_value.rsplit(".", 1)
    return agent_id if hmac.compare_digest(sign_agent(agent_id, secret), header_value) else None


def is_countersign_tool(tool_name: str) -> bool:
    return tool_name.startswith(SERVER_PREFIX)


def money_action(tool_name: str) -> str | None:
    return MONEY_TOOLS.get(tool_name.removeprefix(SERVER_PREFIX)) if is_countersign_tool(tool_name) else None


@dataclass
class Outcome:
    kind: Literal["allow", "block", "replay"]
    message: str = ""
    intent_id: str | None = None
    result: dict[str, Any] | None = None


class Guard:
    def __init__(self, settings: Settings, store: Store, backend: PaymentsBackend, secret: str):
        self.settings = settings
        self.store = store
        self.backend = backend
        self.secret = secret

    async def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        headers: dict[str, str],
        session_id: str,
        private_seen: bool,
        trifecta: str | None,
    ) -> Outcome:
        agent_id = verify_agent(headers.get(AGENT_HEADER), self.secret)
        arguments.pop(INTENT_ARG, None)
        if agent_id is None:
            return Outcome(
                "block", "Countersign: this connection has no valid agent key. Connect through your agent's Countersign URL."
            )
        agent = self.store.get_agent(agent_id)
        if agent is None or not agent["active"]:
            return Outcome("block", "Countersign: this agent is paused or has been removed. Nothing was paid.")
        self.store.touch_agent(agent_id, session_id)

        action = money_action(tool_name)
        if action is None:
            return Outcome("allow")
        return await self._money(agent, action, arguments, session_id, private_seen, trifecta)

    async def _money(
        self,
        agent: dict[str, Any],
        action: str,
        arguments: dict[str, Any],
        session_id: str,
        private_seen: bool,
        trifecta: str | None,
    ) -> Outcome:
        target = str(arguments.get(TARGET_ARG[action], "")).strip()
        reference = str(arguments.get("reference", "")).strip()
        if not target:
            return Outcome("block", f"Countersign: {TARGET_ARG[action]} is required. Nothing was paid.")
        if not reference:
            return Outcome(
                "block",
                "Countersign: `reference` is required. Use a stable ID for this money move (for example the ticket "
                "number), so a retry can never pay twice. Nothing was paid.",
            )
        try:
            amount = parse_amount(arguments.get("amount"))
            currency = parse_currency(arguments.get("currency") or "USD")
        except MoneyError as exc:
            return Outcome("block", f"Countersign: {exc}. Nothing was paid.")

        fp = fingerprint(agent["id"], action, target, fmt(amount), currency, reference)
        existing = self.store.find_by_fingerprint(fp)
        if existing:
            return await self._resume(existing)

        mandate = normalize_mandate(agent["mandate"])
        context = self.store.session_context(session_id)
        untrusted = [c for c in context if c["kind"] == "untrusted"]
        facts = Facts(
            agent_active=agent["active"],
            mandate=mandate,
            spent_today=Decimal(self.store.spent_since(agent["id"], currency, now() - timedelta(hours=24))),
            moves_last_minute=self.store.moves_since(agent["id"], now() - timedelta(seconds=60)),
            recent_moves_to_target=self.store.moves_to_target(
                agent["id"], action, target, now() - timedelta(minutes=mandate["repeat_target_window_minutes"])
            ),
            untrusted_sources=[c["tool"] for c in untrusted],
            private_data_seen=private_seen,
        )
        if action == "refund":
            await self._refund_facts(facts, target, currency)

        decision = evaluate(MoveRequest(agent["id"], action, amount, currency, target, reference), facts)
        intent = self.store.create_intent(
            agent_id=agent["id"],
            session_id=session_id,
            action=action,
            amount=fmt(amount),
            currency=currency,
            target=target,
            reference=reference,
            fingerprint=fp,
            request_id="cs-" + fp[:40],
            backend=self.settings.backend,
            context={
                "agent_name": agent["name"],
                "client": agent["client"],
                "note": str(arguments.get("reason") or arguments.get("note") or "")[:500],
                "untrusted": [{"tool": c["tool"], "excerpt": c["excerpt"][:800], "at": c["at"]} for c in untrusted[-5:]],
                "private_data_seen": private_seen,
                "gateway_trifecta": trifecta,
            },
        )
        rules = decision.as_dicts()
        if decision.outcome == "block":
            self.store.update_intent(
                intent.id, "intent_blocked", status="blocked", rules=rules, error="; ".join(decision.reasons)
            )
            return Outcome("block", _blocked_message(intent, decision.reasons), intent.id)
        if decision.outcome == "hold":
            held = self.store.update_intent(
                intent.id,
                "intent_held",
                status="held",
                rules=rules,
                hold_reason="; ".join(decision.reasons),
                hold_expires_at=self._expiry(),
            )
            return await self._wait(held)
        self.store.update_intent(intent.id, "intent_allowed", status="allowed", rules=rules)
        return Outcome("allow", intent_id=intent.id)

    async def _refund_facts(self, facts: Facts, capture_id: str, currency: str) -> None:
        try:
            info = await asyncio.to_thread(self.backend.get_payment, capture_id)
        except PayPalError as exc:
            facts.refundable_error = f"{exc.name}: {exc.message}"
            if exc.status == 404:
                facts.refundable = Decimal("0")
            return
        except Exception as exc:  # noqa: BLE001 - any lookup failure means a human must check
            facts.refundable_error = str(exc)
            return
        if info.currency != currency:
            facts.refundable = Decimal("0")
            facts.refundable_error = f"payment is in {info.currency}"
            return
        in_flight = Decimal(self.store.refunds_in_flight(capture_id, currency))
        facts.refundable = max(info.refundable - in_flight, Decimal("0"))

    async def _resume(self, intent: Intent) -> Outcome:
        """A retry of an intent Countersign has already seen."""
        intent = self.store.bump_attempt(intent.id)
        if intent.status == "executed":
            return Outcome(
                "replay",
                intent_id=intent.id,
                result={
                    **(intent.result or {}),
                    "countersign_note": (
                        f"Already done: this exact {intent.action} was executed earlier (retry #{intent.attempts - 1} absorbed). "
                        "Nothing was paid twice."
                    ),
                },
            )
        if intent.status in ("allowed", "approved", "executing", "failed"):
            return Outcome("allow", intent_id=intent.id)
        if intent.status == "held":
            return await self._wait(intent)
        if intent.status == "expired":
            rearmed = self.store.update_intent(intent.id, "intent_rearmed", status="held", hold_expires_at=self._expiry())
            return await self._wait(rearmed)
        if intent.status == "denied":
            return Outcome(
                "block",
                (
                    f"Countersign: a human denied this exact {intent.action} (intent {intent.id}). Nothing was paid. "
                    "Do not retry; tell the person it needs manual review."
                ),
                intent.id,
            )
        return Outcome("block", _blocked_message(intent, [intent.error or intent.hold_reason or "blocked earlier"]), intent.id)

    async def _wait(self, intent: Intent) -> Outcome:
        deadline = asyncio.get_running_loop().time() + self.settings.approval_timeout_s
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(POLL_SECONDS)
            current = self.store.get_intent(intent.id)
            if current is None:
                break
            if current.status == "approved":
                return Outcome("allow", intent_id=intent.id)
            if current.status == "denied":
                return Outcome(
                    "block",
                    (
                        f"Countersign: a human denied this {intent.action} (intent {intent.id}). Nothing was paid. "
                        "Do not retry; tell the person it needs manual review."
                    ),
                    intent.id,
                )
        expired = self.store.get_intent(intent.id)
        if expired and expired.status == "held":
            self.store.update_intent(intent.id, "intent_expired", status="expired")
        return Outcome(
            "block",
            (
                f"Countersign held this {intent.action} for a human (intent {intent.id}): {intent.hold_reason}. "
                f"Nobody approved it within {self.settings.approval_timeout_s:.0f}s, so nothing was paid. If the human approves it "
                "in Countersign, call this tool again with exactly the same arguments and it will go through. "
                "Use check_money_move to see its status."
            ),
            intent.id,
        )

    def _expiry(self) -> str:
        return iso(now() + timedelta(seconds=self.settings.approval_timeout_s))

    def record_context(self, session_id: str, tool_name: str, kind: str, text: str) -> None:
        if text.strip():
            self.store.add_context(session_id, tool_name, kind, text)


def _blocked_message(intent: Intent, reasons: list[str]) -> str:
    return f"Countersign blocked this {intent.action} (intent {intent.id}): {'; '.join(reasons)}. Nothing was paid."


@cache
def get_guard() -> Guard:
    settings = load_settings()
    store = Store(settings.db_path)
    secret = os.environ.get("COUNTERSIGN_GATEWAY_SECRET", "")
    if not secret:
        raise RuntimeError("COUNTERSIGN_GATEWAY_SECRET is not set for the gateway")
    return Guard(settings, store, make_backend(settings), secret)


def result_text(result: Any) -> str:
    """Plain text of a tool result, for remembering untrusted content an agent read."""
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    structured = getattr(result, "structured_content", None)
    if not parts and structured:
        parts.append(json.dumps(structured, default=str))
    return "\n".join(parts)
