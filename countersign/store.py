"""The money trail: agents, intents, decisions, holds and PayPal results.

One SQLite file (WAL mode) shared by the gateway, the money server and the
console. Every write is a short transaction, so the three processes can work
on it at once.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    client TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    key_hint TEXT NOT NULL,
    mandate TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_seen_at TEXT
);
CREATE TABLE IF NOT EXISTS intents (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    session_id TEXT,
    action TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    target TEXT NOT NULL,
    reference TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    request_id TEXT NOT NULL,
    status TEXT NOT NULL,
    rules TEXT NOT NULL DEFAULT '[]',
    hold_reason TEXT,
    hold_expires_at TEXT,
    decided_by TEXT,
    decided_at TEXT,
    backend TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 1,
    paypal_id TEXT,
    paypal_status TEXT,
    paypal_debug_id TEXT,
    error TEXT,
    confirmed_status TEXT,
    confirmed_at TEXT,
    result TEXT,
    context TEXT NOT NULL DEFAULT '{}',
    explanation TEXT
);
CREATE INDEX IF NOT EXISTS intents_fingerprint ON intents(fingerprint, created_at);
CREATE INDEX IF NOT EXISTS intents_agent ON intents(agent_id, created_at);
CREATE INDEX IF NOT EXISTS intents_status ON intents(status);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    intent_id TEXT,
    agent_id TEXT,
    kind TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    at TEXT NOT NULL,
    tool TEXT NOT NULL,
    kind TEXT NOT NULL,
    excerpt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS session_context_session ON session_context(session_id, at);
"""

LIVE_STATUSES = ("allowed", "approved", "executing", "executed")
OPEN_STATUSES = ("held",)


def now() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def fingerprint(agent_id: str, action: str, target: str, amount: str, currency: str, reference: str) -> str:
    """Same agent + same money move + same reference = same intent, however often it is retried."""
    raw = "|".join([agent_id, action, target.strip().lower(), amount, currency, reference.strip()])
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class Intent:
    id: str
    created_at: str
    updated_at: str
    agent_id: str
    session_id: str | None
    action: str
    amount: str
    currency: str
    target: str
    reference: str
    fingerprint: str
    request_id: str
    status: str
    rules: list[dict[str, Any]]
    hold_reason: str | None
    hold_expires_at: str | None
    decided_by: str | None
    decided_at: str | None
    backend: str
    attempts: int
    paypal_id: str | None
    paypal_status: str | None
    paypal_debug_id: str | None
    error: str | None
    confirmed_status: str | None
    confirmed_at: str | None
    result: dict[str, Any] | None
    context: dict[str, Any]
    explanation: dict[str, Any] | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Intent:
        data = dict(row)
        data["rules"] = json.loads(data["rules"] or "[]")
        data["context"] = json.loads(data["context"] or "{}")
        data["result"] = json.loads(data["result"]) if data["result"] else None
        data["explanation"] = json.loads(data["explanation"]) if data["explanation"] else None
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=10000")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    # Events -----------------------------------------------------------------

    def _event(self, db: sqlite3.Connection, kind: str, intent_id: str | None, agent_id: str | None, **data: Any) -> None:
        db.execute(
            "INSERT INTO events (at, intent_id, agent_id, kind, data) VALUES (?, ?, ?, ?, ?)",
            (iso(now()), intent_id, agent_id, kind, json.dumps(data, default=str)),
        )

    def add_event(self, kind: str, intent_id: str | None = None, agent_id: str | None = None, **data: Any) -> None:
        with self._tx() as db:
            self._event(db, kind, intent_id, agent_id, **data)

    def events_after(self, last_id: int, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM events WHERE id > ? ORDER BY id LIMIT ?", (last_id, limit)).fetchall()
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]

    def last_event_id(self) -> int:
        with self._connect() as db:
            row = db.execute("SELECT COALESCE(MAX(id), 0) AS id FROM events").fetchone()
        return int(row["id"])

    # Agents -----------------------------------------------------------------

    def create_agent(self, name: str, client: str, mandate: dict[str, Any]) -> tuple[dict[str, Any], str]:
        key = "csk_" + secrets.token_urlsafe(24)
        agent = {
            "id": new_id("agt"),
            "name": name.strip()[:60] or "Agent",
            "client": client,
            "key_hash": hash_key(key),
            "key_hint": key[-4:],
            "mandate": json.dumps(mandate),
            "active": 1,
            "created_at": iso(now()),
        }
        with self._tx() as db:
            db.execute(
                "INSERT INTO agents (id, name, client, key_hash, key_hint, mandate, active, created_at) "
                "VALUES (:id, :name, :client, :key_hash, :key_hint, :mandate, :active, :created_at)",
                agent,
            )
            self._event(db, "agent_created", None, agent["id"], name=agent["name"], client=client)
        return self.get_agent(agent["id"]) or {}, key

    def rotate_agent_key(self, agent_id: str) -> str | None:
        key = "csk_" + secrets.token_urlsafe(24)
        with self._tx() as db:
            updated = db.execute(
                "UPDATE agents SET key_hash = ?, key_hint = ? WHERE id = ?", (hash_key(key), key[-4:], agent_id)
            ).rowcount
            if updated:
                self._event(db, "agent_key_rotated", None, agent_id)
        return key if updated else None

    def agent_by_key(self, key: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM agents WHERE key_hash = ? AND active = 1", (hash_key(key),)).fetchone()
        return self._agent_dict(row) if row else None

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return self._agent_dict(row) if row else None

    def list_agents(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM agents ORDER BY created_at").fetchall()
        return [self._agent_dict(row) for row in rows]

    def update_mandate(self, agent_id: str, mandate: dict[str, Any]) -> dict[str, Any] | None:
        with self._tx() as db:
            db.execute("UPDATE agents SET mandate = ? WHERE id = ?", (json.dumps(mandate), agent_id))
            self._event(db, "mandate_updated", None, agent_id, mandate=mandate)
        return self.get_agent(agent_id)

    def set_agent_active(self, agent_id: str, active: bool) -> None:
        with self._tx() as db:
            db.execute("UPDATE agents SET active = ? WHERE id = ?", (1 if active else 0, agent_id))
            self._event(db, "agent_paused" if not active else "agent_resumed", None, agent_id)

    def touch_agent(self, agent_id: str, session_id: str | None) -> None:
        stamp = iso(now())
        with self._tx() as db:
            db.execute("UPDATE agents SET last_seen_at = ? WHERE id = ?", (stamp, agent_id))
            if session_id:
                db.execute(
                    "INSERT INTO sessions (session_id, agent_id, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(session_id) DO UPDATE SET last_seen_at = excluded.last_seen_at",
                    (session_id, agent_id, stamp, stamp),
                )

    @staticmethod
    def _agent_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data.pop("key_hash", None)
        data["mandate"] = json.loads(data["mandate"])
        data["active"] = bool(data["active"])
        return data

    # Session context (what untrusted content an agent saw) ----------------------

    def add_context(self, session_id: str, tool: str, kind: str, excerpt: str) -> None:
        with self._tx() as db:
            db.execute(
                "INSERT INTO session_context (session_id, at, tool, kind, excerpt) VALUES (?, ?, ?, ?, ?)",
                (session_id, iso(now()), tool, kind, excerpt[:4000]),
            )

    def session_context(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT tool, kind, excerpt, at FROM session_context WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    # Intents ----------------------------------------------------------------

    def create_intent(self, **fields: Any) -> Intent:
        stamp = iso(now())
        record = {
            "id": new_id("cs"),
            "created_at": stamp,
            "updated_at": stamp,
            "status": "evaluating",
            "rules": "[]",
            "context": json.dumps(fields.pop("context", {}), default=str),
            **fields,
        }
        columns = ", ".join(record)
        params = ", ".join(f":{name}" for name in record)
        with self._tx() as db:
            db.execute(f"INSERT INTO intents ({columns}) VALUES ({params})", record)
            self._event(
                db,
                "intent_created",
                record["id"],
                record["agent_id"],
                action=record["action"],
                amount=record["amount"],
                currency=record["currency"],
                target=record["target"],
            )
        intent = self.get_intent(record["id"])
        assert intent is not None
        return intent

    def get_intent(self, intent_id: str) -> Intent | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM intents WHERE id = ?", (intent_id,)).fetchone()
        return Intent.from_row(row) if row else None

    def find_by_fingerprint(self, fp: str) -> Intent | None:
        """The intent a retry belongs to, at any age. A payment or a human decision outranks a later undecided attempt."""
        with self._connect() as db:
            row = db.execute(
                """SELECT * FROM intents WHERE fingerprint = ?
                   ORDER BY CASE status WHEN 'executed' THEN 0 WHEN 'denied' THEN 1 WHEN 'approved' THEN 2 ELSE 3 END,
                            created_at DESC
                   LIMIT 1""",
                (fp,),
            ).fetchone()
        return Intent.from_row(row) if row else None

    def list_intents(self, limit: int = 500, status: str | None = None) -> list[Intent]:
        query, params = "SELECT * FROM intents", []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [Intent.from_row(row) for row in rows]

    def update_intent(self, intent_id: str, event: str | None = None, **fields: Any) -> Intent:
        for name in ("rules", "result", "context", "explanation"):
            if name in fields and not isinstance(fields[name], str | None):
                fields[name] = json.dumps(fields[name], default=str)
        fields["updated_at"] = iso(now())
        assignments = ", ".join(f"{name} = :{name}" for name in fields)
        with self._tx() as db:
            db.execute(f"UPDATE intents SET {assignments} WHERE id = :intent_id", {**fields, "intent_id": intent_id})
            if event:
                row = db.execute("SELECT agent_id, status FROM intents WHERE id = ?", (intent_id,)).fetchone()
                self._event(db, event, intent_id, row["agent_id"] if row else None, status=row["status"] if row else None)
        intent = self.get_intent(intent_id)
        assert intent is not None
        return intent

    def bump_attempt(self, intent_id: str) -> Intent:
        with self._tx() as db:
            db.execute("UPDATE intents SET attempts = attempts + 1, updated_at = ? WHERE id = ?", (iso(now()), intent_id))
            row = db.execute("SELECT agent_id, attempts FROM intents WHERE id = ?", (intent_id,)).fetchone()
            self._event(db, "retry_absorbed", intent_id, row["agent_id"], attempts=row["attempts"])
        intent = self.get_intent(intent_id)
        assert intent is not None
        return intent

    def decide(self, intent_id: str, approve: bool, decided_by: str) -> Intent | None:
        """A human decision. Only a held or expired intent can be decided, and only once."""
        status = "approved" if approve else "denied"
        stamp = iso(now())
        with self._tx() as db:
            changed = db.execute(
                "UPDATE intents SET status = ?, decided_by = ?, decided_at = ?, updated_at = ? "
                "WHERE id = ? AND status IN ('held', 'expired')",
                (status, decided_by, stamp, stamp, intent_id),
            ).rowcount
            if changed:
                row = db.execute("SELECT agent_id FROM intents WHERE id = ?", (intent_id,)).fetchone()
                self._event(db, f"intent_{status}", intent_id, row["agent_id"], by=decided_by)
        return self.get_intent(intent_id) if changed else None

    def spent_since(self, agent_id: str, currency: str, since: datetime) -> str:
        with self._connect() as db:
            rows = db.execute(
                "SELECT amount FROM intents WHERE agent_id = ? AND currency = ? AND created_at >= ? AND status IN "
                "('allowed', 'approved', 'executing', 'executed')",
                (agent_id, currency, iso(since)),
            ).fetchall()
        return f"{sum((Decimal(row['amount']) for row in rows), Decimal('0')):.2f}"

    def moves_since(self, agent_id: str, since: datetime) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM intents WHERE agent_id = ? AND created_at >= ?", (agent_id, iso(since))
            ).fetchone()
        return int(row["n"])

    def moves_to_target(self, agent_id: str, action: str, target: str, since: datetime) -> int:
        """Money moves this agent already made (or has under way) to the same payment or recipient."""
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM intents WHERE agent_id = ? AND action = ? AND lower(target) = lower(?) "
                "AND created_at >= ? AND status IN ('allowed', 'approved', 'executing', 'executed')",
                (agent_id, action, target, iso(since)),
            ).fetchone()
        return int(row["n"])

    def refunds_in_flight(self, capture_id: str, currency: str) -> str:
        """Refunds Countersign has let through that PayPal may not have recorded yet."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT amount FROM intents WHERE action = 'refund' AND lower(target) = lower(?) AND currency = ? "
                "AND status IN ('allowed', 'approved', 'executing')",
                (capture_id, currency),
            ).fetchall()
        return f"{sum((Decimal(row['amount']) for row in rows), Decimal('0')):.2f}"

    def expire_due_holds(self) -> list[str]:
        stamp = iso(now())
        with self._tx() as db:
            rows = db.execute(
                "SELECT id, agent_id FROM intents WHERE status = 'held' AND hold_expires_at IS NOT NULL AND hold_expires_at < ?",
                (stamp,),
            ).fetchall()
            for row in rows:
                db.execute("UPDATE intents SET status = 'expired', updated_at = ? WHERE id = ?", (stamp, row["id"]))
                self._event(db, "intent_expired", row["id"], row["agent_id"])
        return [row["id"] for row in rows]

    def summary(self, since: datetime) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT status, COUNT(*) AS n, SUM(CAST(amount AS REAL)) AS total, SUM(attempts - 1) AS retries "
                "FROM intents WHERE created_at >= ? GROUP BY status",
                (iso(since),),
            ).fetchall()
        by_status = {row["status"]: {"count": row["n"], "total": round(row["total"] or 0, 2)} for row in rows}
        retries = sum(int(row["retries"] or 0) for row in rows)
        return {"by_status": by_status, "retries_absorbed": retries}
