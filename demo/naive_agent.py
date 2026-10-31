"""A scripted agent with no judgement, to show what Countersign does when an agent is fooled.

Real Claude spotted the prompt injection and the look-alike payee in every run
we tried, even when told to trust notes in tickets. So this is deliberately not
a model: it asks for whatever a ticket says, through its own Countersign URL,
like any other agent. Say that plainly whenever you show it.

It works only the two bad tickets by default. T-1001 and T-1002 are the real agent's.

Usage (Countersign must be running):  python demo/naive_agent.py [ticket ids]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from countersign.connect import mcp_url  # noqa: E402
from countersign.policy import DEFAULT_MANDATE, normalize_mandate  # noqa: E402
from countersign.settings import Settings, load_settings  # noqa: E402
from countersign.store import Store  # noqa: E402

NAME = "Naive script (not an AI)"
BAD_TICKETS = ["T-1003", "T-1004"]
AMOUNT = re.compile(r"\d+\.\d{2}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def next_move(ticket: dict[str, Any], order: dict[str, Any] | None) -> tuple[str, dict[str, str]]:
    """The ticket decides: its largest amount, back to the order or to the address it names."""
    amount = max(AMOUNT.findall(ticket["body"]), key=Decimal)
    if order is None:
        payee = EMAIL.search(ticket["body"]).group()
        return "countersign_send_payout", {"recipient_email": payee, "amount": amount, "reference": ticket["id"]}
    return (
        "countersign_refund_payment",
        {"capture_id": order["paypal_capture_id"], "amount": amount, "reference": ticket["id"]},
    )


def agent_url(settings: Settings) -> str:
    """Its own Countersign URL, kept in a private file so the key never appears on camera."""
    path = settings.data_dir / "demo" / "naive-agent.json"
    if path.exists():
        return json.loads(path.read_text())["url"]
    record, key = Store(settings.db_path).create_agent(NAME, "other", normalize_mandate(DEFAULT_MANDATE))
    url = mcp_url(settings.public_url, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.write_text(json.dumps({"agent": record["id"], "url": url}, indent=2) + "\n")
    return url


async def read(mcp: ClientSession, tool: str, **args: str) -> dict[str, Any]:
    return (await mcp.call_tool(tool, args)).structuredContent or {}


async def work_the_inbox(url: str, ticket_ids: list[str], say: Callable[[str], None] = print) -> None:
    say("NAIVE SCRIPT, not an AI. It asks for whatever a ticket says, to show what Countersign stops.\n")
    async with streamablehttp_client(url) as (reader, writer, _), ClientSession(reader, writer) as mcp:
        await mcp.initialize()
        for ticket_id in ticket_ids:
            ticket = await read(mcp, "shop_read_ticket", ticket_id=ticket_id)
            order = await read(mcp, "shop_lookup_order", order=ticket["order"]) if ticket["order"] else None
            tool, args = next_move(ticket, order)
            say(f"{ticket_id}: {ticket['subject']}, from {ticket['from']}")
            say(f"  The ticket says {args['amount']}, so that is what it asks for. Waiting on Countersign...")
            result = await mcp.call_tool(tool, args)
            answer = " ".join(result.content[0].text.split())
            say(f"  {answer}\n")


def main() -> None:
    asyncio.run(work_the_inbox(agent_url(load_settings()), sys.argv[1:] or BAD_TICKETS))


if __name__ == "__main__":
    main()
