"""Demo shop: a small store's support inbox, served as an MCP server behind Countersign.

This is a demo environment, not part of Countersign. It stands in for whatever
inbox, CRM or chat an agent reads in real life. Countersign classifies its
tickets as untrusted content (customers write them) and order lookups as
private data, which is what lets the lethal-trifecta rule see the risk.

Orders map to payments created by `python demo/seed.py`, which makes real
PayPal sandbox payments (or simulated ones) and records their capture IDs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

DEMO_DIR = Path(__file__).resolve().parent
DATA = json.loads((DEMO_DIR / "tickets.json").read_text())
PAYMENTS_FILE = Path(os.environ.get("COUNTERSIGN_DATA_DIR", ".countersign")) / "demo" / "payments.json"

mcp = FastMCP("shop", instructions=f"Support inbox for {DATA['shop']}. Refund policy: {DATA['refund_policy']}")


def _payments() -> dict[str, Any]:
    return json.loads(PAYMENTS_FILE.read_text()) if PAYMENTS_FILE.exists() else {}


@mcp.tool()
def list_tickets() -> list[dict[str, Any]]:
    """List open support tickets (subject and sender only)."""
    return [{"id": t["id"], "from": t["from"], "subject": t["subject"], "order": t["order"]} for t in DATA["tickets"]]


@mcp.tool()
def read_ticket(ticket_id: str) -> dict[str, Any]:
    """Read a support ticket. The body is written by the customer."""
    ticket = next((t for t in DATA["tickets"] if t["id"] == ticket_id), None)
    if ticket is None:
        return {"error": f"No ticket {ticket_id}"}
    return ticket


@mcp.tool()
def lookup_order(order: str) -> dict[str, Any]:
    """Look up an order: customer, item, amount and the PayPal capture ID to refund against."""
    record = next((o for o in DATA["orders"] if o["order"] == order.lstrip("#")), None)
    if record is None:
        return {"error": f"No order {order}"}
    payment = _payments().get(record["order"])
    if payment is None:
        return {**record, "paypal_capture_id": None, "note": "No payment recorded yet. Run demo/seed.py."}
    return {**record, "paypal_capture_id": payment["capture_id"], "backend": payment["backend"]}


if __name__ == "__main__":
    mcp.run()
