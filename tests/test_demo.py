"""The demo's scripted agent has no judgement, so the ticket alone decides what it asks for."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from bench.run import LOOKALIKE
from countersign.settings import Settings
from demo import naive_agent

SHOP = json.loads((Path(__file__).parent.parent / "demo" / "tickets.json").read_text())


def ticket(ticket_id: str) -> dict:
    return next(t for t in SHOP["tickets"] if t["id"] == ticket_id)


@pytest.mark.parametrize(
    ("ticket_id", "amount"),
    [("T-1001", "12.00"), ("T-1002", "40.00"), ("T-1003", "450.00")],
)
def test_it_refunds_the_amount_a_ticket_names(ticket_id, amount):
    tool, args = naive_agent.next_move(ticket(ticket_id), {"paypal_capture_id": "CAPTURE"})
    assert tool == "countersign_refund_payment"
    assert args["capture_id"] == "CAPTURE"
    assert args["amount"] == amount
    assert args["reference"] == ticket_id


def test_it_pays_the_address_a_ticket_names_without_checking_it():
    tool, args = naive_agent.next_move(ticket("T-1004"), None)
    assert tool == "countersign_send_payout"
    assert args["recipient_email"] == LOOKALIKE
    assert args["amount"] == "35.00"
    assert args["reference"] == "T-1004"


def test_its_url_is_kept_in_a_private_file_and_reused(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        backend="simulated",
        paypal_client_id="",
        paypal_client_secret="",
        paypal_webhook_id="",
        host="127.0.0.1",
        port=8484,
        public_url="http://127.0.0.1:8484",
        approval_timeout_s=1,
        gateway_mcp_port=1,
        gateway_api_port=2,
        anthropic_api_key="",
        anthropic_model="claude-opus-5-5",
        demo_shop=True,
    )
    first = naive_agent.agent_url(settings)
    assert naive_agent.agent_url(settings) == first
    assert first.startswith("http://127.0.0.1:8484/mcp/")
    saved = tmp_path / "demo" / "naive-agent.json"
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600
