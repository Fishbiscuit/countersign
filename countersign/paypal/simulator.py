"""Simulated PayPal: no PayPal calls, no money, clearly labelled everywhere.

QZ asked for simulated transactions for development and offline demos. It
follows PayPal's semantics where Countersign depends on them: refunds cannot
exceed what was captured, and a repeated PayPal-Request-Id returns the original
result instead of moving money again. (PayPal itself refuses a repeated payout
batch; the sandbox backend turns that refusal into this same result.) It also
takes scripted faults ("chaos"), so the bench can reproduce the failures agents
cause in real systems.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import string
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from countersign.paypal.types import Checkout, MoneyResult, PaymentInfo, PayPalError, PayPalUnavailable

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, amount TEXT, currency TEXT, description TEXT, status TEXT, capture_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS captures (id TEXT PRIMARY KEY, order_id TEXT, amount TEXT, currency TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS refunds (id TEXT PRIMARY KEY, capture_id TEXT, amount TEXT, currency TEXT, status TEXT, note TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS payouts (id TEXT PRIMARY KEY, email TEXT, amount TEXT, currency TEXT, status TEXT, reference TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS idempotency (request_id TEXT PRIMARY KEY, operation TEXT, response TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS chaos (id INTEGER PRIMARY KEY AUTOINCREMENT, operation TEXT, mode TEXT, remaining INTEGER);
"""

CHAOS_MODES = ("lost_response", "server_error", "no_answer")


def _sim_id(prefix: str) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return f"SIM{prefix}" + "".join(secrets.choice(alphabet) for _ in range(13))


def _stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class SimulatedBackend:
    name = "simulated"
    label = "Simulated PayPal"

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        setup = sqlite3.connect(path, timeout=10)
        try:
            setup.execute("PRAGMA journal_mode=WAL")
            setup.executescript(SCHEMA)
        finally:
            setup.close()

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=10000")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    # Chaos ----------------------------------------------------------------------

    def inject(self, operation: str, mode: str, times: int = 1) -> None:
        """Make the next `times` calls of `operation` (refund/payout) fail in `mode`."""
        if mode not in CHAOS_MODES:
            raise ValueError(f"Unknown chaos mode {mode}")
        with self._db() as db:
            db.execute("INSERT INTO chaos (operation, mode, remaining) VALUES (?, ?, ?)", (operation, mode, times))

    def clear_chaos(self) -> None:
        with self._db() as db:
            db.execute("DELETE FROM chaos")

    def _chaos_before(self, operation: str) -> str | None:
        """Use up one scripted fault (its own transaction, so a raised error cannot restore it)."""
        with self._db() as db:
            row = db.execute(
                "SELECT id, mode FROM chaos WHERE operation = ? AND remaining > 0 ORDER BY id LIMIT 1", (operation,)
            ).fetchone()
            if row:
                db.execute("UPDATE chaos SET remaining = remaining - 1 WHERE id = ?", (row["id"],))
        mode = str(row["mode"]) if row else None
        if mode == "server_error":
            raise PayPalError(500, "INTERNAL_SERVER_ERROR", "Simulated PayPal server error", "SIM-DEBUG")
        if mode == "no_answer":
            raise PayPalUnavailable("Simulated: PayPal did not answer (request never processed)")
        return mode

    # Payments -------------------------------------------------------------------

    def get_payment(self, capture_id: str) -> PaymentInfo:
        with self._db() as db:
            capture = db.execute("SELECT * FROM captures WHERE id = ?", (capture_id,)).fetchone()
            if not capture:
                raise PayPalError(404, "RESOURCE_NOT_FOUND", f"Simulated capture {capture_id} does not exist")
            refunded = self._refunded(db, capture_id)
            return PaymentInfo(capture["id"], capture["status"], Decimal(capture["amount"]), capture["currency"], refunded)

    @staticmethod
    def _refunded(db: sqlite3.Connection, capture_id: str) -> Decimal:
        rows = db.execute("SELECT amount FROM refunds WHERE capture_id = ? AND status = 'COMPLETED'", (capture_id,)).fetchall()
        return sum((Decimal(r["amount"]) for r in rows), Decimal("0"))

    def refund(self, capture_id: str, amount: str, currency: str, request_id: str, note: str | None) -> MoneyResult:
        replay = self._replay(request_id)
        if replay:
            return replay
        chaos = self._chaos_before("refund")
        with self._db() as db:
            capture = db.execute("SELECT * FROM captures WHERE id = ?", (capture_id,)).fetchone()
            if not capture:
                raise PayPalError(404, "RESOURCE_NOT_FOUND", f"Simulated capture {capture_id} does not exist")
            if capture["currency"] != currency:
                raise PayPalError(422, "UNPROCESSABLE_ENTITY", "Refund currency must match the capture (CURRENCY_MISMATCH)")
            remaining = Decimal(capture["amount"]) - self._refunded(db, capture_id)
            if Decimal(amount) > remaining:
                raise PayPalError(
                    422, "UNPROCESSABLE_ENTITY", "Refund amount exceeds the refundable amount (REFUND_AMOUNT_EXCEEDED)"
                )
            refund_id = _sim_id("R")
            db.execute(
                "INSERT INTO refunds VALUES (?, ?, ?, ?, 'COMPLETED', ?, ?)",
                (refund_id, capture_id, amount, currency, note or "", _stamp()),
            )
            new_total = self._refunded(db, capture_id)
            status = "REFUNDED" if new_total >= Decimal(capture["amount"]) else "PARTIALLY_REFUNDED"
            db.execute("UPDATE captures SET status = ? WHERE id = ?", (status, capture_id))
            response = {"id": refund_id, "status": "COMPLETED", "amount": {"value": amount, "currency_code": currency}}
            self._remember(db, request_id, "refund", response)
        if chaos == "lost_response":
            raise PayPalUnavailable("Simulated: the refund went through but the response was lost")
        return MoneyResult(refund_id, "COMPLETED", amount, currency, raw=response)

    def payout(self, email: str, amount: str, currency: str, request_id: str, reference: str, note: str | None) -> MoneyResult:
        replay = self._replay(request_id)
        if replay:
            return replay
        chaos = self._chaos_before("payout")
        with self._db() as db:
            batch_id = _sim_id("B")
            db.execute(
                "INSERT INTO payouts VALUES (?, ?, ?, ?, 'SUCCESS', ?, ?)",
                (batch_id, email.lower(), amount, currency, reference, _stamp()),
            )
            response = {
                "batch_header": {"payout_batch_id": batch_id, "batch_status": "SUCCESS"},
                "amount": {"value": amount, "currency_code": currency},
            }
            self._remember(db, request_id, "payout", response)
        if chaos == "lost_response":
            raise PayPalUnavailable("Simulated: the payout went through but the response was lost")
        return MoneyResult(batch_id, "SUCCESS", amount, currency, raw=response)

    def money_status(self, action: str, paypal_id: str) -> str:
        table = "refunds" if action == "refund" else "payouts"
        with self._db() as db:
            row = db.execute(f"SELECT status FROM {table} WHERE id = ?", (paypal_id,)).fetchone()
        if not row:
            raise PayPalError(404, "RESOURCE_NOT_FOUND", f"Simulated {action} {paypal_id} does not exist")
        return str(row["status"])

    def money_moved(self) -> dict[str, Any]:
        """Exact totals the bench uses to measure what actually left the merchant."""
        totals: dict[str, Any] = {}
        with self._db() as db:
            for table in ("refunds", "payouts"):
                rows = db.execute(f"SELECT amount FROM {table}").fetchall()
                totals[table] = {"count": len(rows), "total": f"{sum((Decimal(r['amount']) for r in rows), Decimal('0')):.2f}"}
        return totals

    # Checkout (simulated buyer approves immediately) -----------------------------

    def create_checkout(self, amount: str, currency: str, description: str) -> Checkout:
        order_id = _sim_id("O")
        with self._db() as db:
            db.execute(
                "INSERT INTO orders VALUES (?, ?, ?, ?, 'APPROVED', NULL, ?)", (order_id, amount, currency, description, _stamp())
            )
        return Checkout(order_id, "APPROVED", None)

    def capture_checkout(self, order_id: str) -> Checkout:
        with self._db() as db:
            order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if not order:
                raise PayPalError(404, "RESOURCE_NOT_FOUND", f"Simulated order {order_id} does not exist")
            if order["capture_id"]:
                return Checkout(order_id, "COMPLETED", None, order["capture_id"])
            capture_id = _sim_id("C")
            db.execute(
                "INSERT INTO captures VALUES (?, ?, ?, ?, 'COMPLETED', ?)",
                (capture_id, order_id, order["amount"], order["currency"], _stamp()),
            )
            db.execute("UPDATE orders SET status = 'COMPLETED', capture_id = ? WHERE id = ?", (capture_id, order_id))
        return Checkout(order_id, "COMPLETED", None, capture_id)

    # Idempotency ----------------------------------------------------------------

    def _replay(self, request_id: str) -> MoneyResult | None:
        with self._db() as db:
            row = db.execute("SELECT response, operation FROM idempotency WHERE request_id = ?", (request_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row["response"])
        if row["operation"] == "refund":
            return MoneyResult(data["id"], data["status"], data["amount"]["value"], data["amount"]["currency_code"], raw=data)
        header = data["batch_header"]
        return MoneyResult(
            header["payout_batch_id"], header["batch_status"], data["amount"]["value"], data["amount"]["currency_code"], raw=data
        )

    @staticmethod
    def _remember(db: sqlite3.Connection, request_id: str, operation: str, response: dict[str, Any]) -> None:
        db.execute("INSERT INTO idempotency VALUES (?, ?, ?, ?)", (request_id, operation, json.dumps(response), _stamp()))
