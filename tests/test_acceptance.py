"""Acceptance: drive the real agent entrypoint (/mcp/{key}/ → proxy → gateway → money server).

A fresh nonce goes into each money move's reference and must come back out of
the money trail API, so a stale or hard-coded result cannot pass. Only the
payment backend is the simulator; everything else is the shipped code path.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
import uuid
from pathlib import Path

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from bench.run import LOOKALIKE, Bench, free_port, wait_ready
from countersign.console_api import create_app
from countersign.paypal.simulator import SimulatedBackend
from countersign.settings import Settings, load_secrets
from demo import naive_agent

pytestmark = pytest.mark.acceptance


@contextlib.asynccontextmanager
async def running_countersign(demo_shop: bool = False):
    with tempfile.TemporaryDirectory(prefix="countersign-accept-") as tmp:
        port = free_port()
        settings = Settings(
            data_dir=Path(tmp),
            backend="simulated",
            paypal_client_id="",
            paypal_client_secret="",
            paypal_webhook_id="",
            host="127.0.0.1",
            port=port,
            public_url=f"http://127.0.0.1:{port}",
            approval_timeout_s=15,
            gateway_mcp_port=free_port(),
            gateway_api_port=free_port(),
            anthropic_api_key="",
            anthropic_model="claude-opus-5-5",
            demo_shop=demo_shop,
        )
        server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
        task = asyncio.create_task(server.serve())
        try:
            bench = Bench(
                settings.public_url,
                load_secrets(settings.data_dir).admin_token,
                SimulatedBackend(settings.simulator_db_path),
                settings.data_dir,
            )
            await wait_ready(bench)
            yield bench
        finally:
            server.should_exit = True
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def connect(bench: Bench, mandate: dict | None = None):
    async with bench.api() as api:
        body = {"name": "Acceptance agent", "client": "claude-code", **({"mandate": mandate} if mandate else {})}
        return (await api.post("/api/agents", json=body)).json()


async def test_agent_refund_flows_through_every_layer_with_a_fresh_nonce():
    async with running_countersign() as bench:
        nonce = f"T-{uuid.uuid4().hex[:10]}"
        agent = await connect(bench)
        async with bench.api() as api:
            capture = (await api.post("/api/test-payments", json={"amount": "30.00"})).json()["capture_id"]
        url = f"{bench.base}/mcp/{agent['key']}/"
        async with streamablehttp_client(url) as (read, write, _), ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name: t for t in (await session.list_tools()).tools}
            assert "countersign_intent" not in tools["countersign_refund_payment"].inputSchema["properties"]
            args = {"capture_id": capture, "amount": "7.00", "reference": nonce}
            first = await session.call_tool("countersign_refund_payment", args)
            again = await session.call_tool("countersign_refund_payment", args)
        assert not first.isError and not again.isError
        assert first.structuredContent["paypal_id"] == again.structuredContent["paypal_id"]
        async with bench.api() as api:
            trail = [i for i in (await api.get("/api/intents")).json() if i["reference"] == nonce]
        assert len(trail) == 1 and trail[0]["status"] == "executed" and trail[0]["attempts"] == 2
        assert bench.sim.get_payment(capture).refunded == 7


async def test_held_move_waits_for_a_human_and_runs_after_approval():
    async with running_countersign() as bench:
        nonce = f"T-{uuid.uuid4().hex[:10]}"
        agent = await connect(bench)
        async with bench.api() as api:
            capture = (await api.post("/api/test-payments", json={"amount": "100.00"})).json()["capture_id"]

        async def approve_when_held():
            async with bench.api() as api:
                for _ in range(100):
                    held = [
                        i for i in (await api.get("/api/intents", params={"status": "held"})).json() if i["reference"] == nonce
                    ]
                    if held:
                        assert any(r["rule"] == "amount.auto_approve" and r["outcome"] == "hold" for r in held[0]["rules"])
                        return (await api.post(f"/api/intents/{held[0]['id']}/decision", json={"approve": True})).status_code
                    await asyncio.sleep(0.1)

        url = f"{bench.base}/mcp/{agent['key']}/"
        async with streamablehttp_client(url) as (read, write, _), ClientSession(read, write) as session:
            await session.initialize()
            approver = asyncio.create_task(approve_when_held())
            result = await session.call_tool(
                "countersign_refund_payment", {"capture_id": capture, "amount": "60.00", "reference": nonce}
            )
        assert await approver == 200
        assert not result.isError
        assert bench.sim.get_payment(capture).refunded == 60


async def test_denied_move_moves_nothing_and_stays_denied():
    async with running_countersign() as bench:
        nonce = f"T-{uuid.uuid4().hex[:10]}"
        agent = await connect(bench)

        async def deny_when_held():
            async with bench.api() as api:
                for _ in range(100):
                    held = [
                        i for i in (await api.get("/api/intents", params={"status": "held"})).json() if i["reference"] == nonce
                    ]
                    if held:
                        return (await api.post(f"/api/intents/{held[0]['id']}/decision", json={"approve": False})).status_code
                    await asyncio.sleep(0.1)

        url = f"{bench.base}/mcp/{agent['key']}/"
        args = {"recipient_email": "stranger@example.com", "amount": "20.00", "reference": nonce}
        async with streamablehttp_client(url) as (read, write, _), ClientSession(read, write) as session:
            await session.initialize()
            denier = asyncio.create_task(deny_when_held())
            denied = await session.call_tool("countersign_send_payout", args)
            retried = await session.call_tool("countersign_send_payout", args)
        assert await denier == 200
        assert denied.isError and "denied" in denied.content[0].text
        assert retried.isError and "denied" in retried.content[0].text
        assert bench.sim.money_moved()["payouts"]["count"] == 0


async def refund_as(bench: Bench, agent: dict, args: dict):
    url = f"{bench.base}/mcp/{agent['key']}/"
    async with streamablehttp_client(url) as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        return await session.call_tool("countersign_refund_payment", args)


async def test_a_second_agent_cannot_pay_a_ticket_the_first_already_paid():
    async with running_countersign() as bench:
        nonce = f"T-{uuid.uuid4().hex[:10]}"
        first, second = await connect(bench), await connect(bench)
        async with bench.api() as api:
            capture = (await api.post("/api/test-payments", json={"amount": "30.00"})).json()["capture_id"]
        args = {"capture_id": capture, "amount": "7.00", "reference": nonce}

        paid = await refund_as(bench, first, args)
        refused = await refund_as(bench, second, args)
        refused_again = await refund_as(bench, second, args)

        assert not paid.isError
        assert refused.isError and "already paid" in refused.content[0].text
        assert refused_again.isError and "already paid" in refused_again.content[0].text
        assert bench.sim.get_payment(capture).refunded == 7
        async with bench.api() as api:
            trail = [i for i in (await api.get("/api/intents")).json() if i["reference"] == nonce]
        assert sorted(i["status"] for i in trail) == ["blocked", "executed"]
        assert len({i["request_id"] for i in trail}) == 1


async def test_two_agents_racing_on_one_ticket_pay_once():
    async with running_countersign() as bench:
        first, second = await connect(bench), await connect(bench)
        async with bench.api() as api:
            capture = (await api.post("/api/test-payments", json={"amount": "30.00"})).json()["capture_id"]
        args = {"capture_id": capture, "amount": "7.00", "reference": f"T-{uuid.uuid4().hex[:10]}"}

        await asyncio.gather(refund_as(bench, first, args), refund_as(bench, second, args))

        assert bench.sim.get_payment(capture).refunded == 7


async def test_the_naive_script_is_held_on_both_bad_tickets_and_pays_nothing():
    async with running_countersign(demo_shop=True) as bench:
        agent = await connect(bench)
        bench.publish_order("1044", await bench.fresh_payment("1044"))

        async def deny_two_holds():
            denied = []
            async with bench.api() as api:
                while len(denied) < 2:
                    for held in (await api.get("/api/intents", params={"status": "held"})).json():
                        await api.post(f"/api/intents/{held['id']}/decision", json={"approve": False})
                        denied.append(held)
                    await asyncio.sleep(0.1)
            return denied

        denier = asyncio.create_task(deny_two_holds())
        lines: list[str] = []
        await naive_agent.work_the_inbox(f"{bench.base}/mcp/{agent['key']}/", ["T-1003", "T-1004"], lines.append)
        refund, payout = await denier

        assert refund["action"] == "refund" and refund["amount"] == "450.00" and refund["reference"] == "T-1003"
        assert any(r["rule"] == "context.lethal_trifecta" and r["outcome"] == "hold" for r in refund["rules"])
        assert payout["action"] == "payout" and payout["target"] == LOOKALIKE
        assert any(r["rule"] == "payout.recipient" and r["outcome"] == "hold" for r in payout["rules"])

        totals = bench.sim.money_moved()
        assert totals["refunds"]["count"] == 0 and totals["payouts"]["count"] == 0
        assert "not an AI" in lines[0]
        assert sum("denied" in line for line in lines) == 2
        assert not any(agent["key"] in line for line in lines)


@pytest.mark.parametrize("fault", ["lost_response", "server_error", "no_answer"])
async def test_an_unconfirmed_payout_is_never_reported_as_unpaid(fault):
    async with running_countersign() as bench:
        nonce = f"T-{uuid.uuid4().hex[:10]}"
        agent = await connect(bench, {"payout_allowlist": ["supplier@example.com"]})
        bench.sim.inject("payout", fault)
        url = f"{bench.base}/mcp/{agent['key']}/"
        args = {"recipient_email": "supplier@example.com", "amount": "9.00", "reference": nonce}
        async with streamablehttp_client(url) as (read, write, _), ClientSession(read, write) as session:
            await session.initialize()
            first = await session.call_tool("countersign_send_payout", args)
            again = await session.call_tool("countersign_send_payout", args)
        assert first.isError and "safe to retry" in first.content[0].text
        assert "Nothing was paid" not in first.content[0].text
        assert not again.isError
        async with bench.api() as api:
            trail = [i for i in (await api.get("/api/intents")).json() if i["reference"] == nonce]
        assert len(trail) == 1 and trail[0]["status"] == "executed" and trail[0]["attempts"] == 2
        assert bench.sim.money_moved()["payouts"] == {"count": 1, "total": "9.00"}


async def test_unknown_key_is_rejected():
    async with running_countersign() as bench:
        async with bench.api() as api:
            response = await api.post("/mcp/csk_not-a-real-key/", json={})
        assert response.status_code == 401
