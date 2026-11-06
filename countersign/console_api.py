"""The Countersign console: approvals, money trail, agents, bench, and the agent-facing MCP endpoint."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger as log
from pydantic import BaseModel, Field

from countersign import __version__
from countersign.connect import CLIENT_IDS, CLIENTS, instructions, mcp_url
from countersign.explainer import EXPLAINER_ERRORS, Explainer
from countersign.gateway_runner import REPO_ROOT, start_gateway
from countersign.mcp_proxy import make_router
from countersign.money import MoneyError, fmt, parse_amount
from countersign.paypal import make_backend
from countersign.paypal.sandbox import SandboxBackend
from countersign.paypal.types import PayPalError, PayPalUnavailable
from countersign.policy import DEFAULT_MANDATE, normalize_mandate
from countersign.settings import Settings, load_secrets, load_settings
from countersign.store import Store, now

CONSOLE_DIST = REPO_ROOT / "console" / "dist"
FINAL_PAYPAL_STATUSES = {"COMPLETED", "SUCCESS", "FAILED", "CANCELLED", "RETURNED", "REFUNDED", "UNCLAIMED", "DENIED"}
COOKIE = "countersign_admin"


class NewAgent(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    client: str
    mandate: dict[str, Any] | None = None


class AgentUpdate(BaseModel):
    mandate: dict[str, Any] | None = None
    active: bool | None = None


class Decision(BaseModel):
    approve: bool
    via: str = "console"


class Login(BaseModel):
    token: str


class TestPayment(BaseModel):
    amount: str = "50.00"
    currency: str = "USD"
    description: str = "Countersign test payment"


class GridQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=500)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    secrets = load_secrets(settings.data_dir)
    store = Store(settings.db_path)
    backend = make_backend(settings)
    explainer = Explainer(settings)
    state: dict[str, Any] = {"gateway": None}

    def is_public() -> bool:
        return settings.public_url.startswith("https://")

    def require_admin(request: Request) -> None:
        supplied = request.cookies.get(COOKIE) or request.query_params.get("token")
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth[7:]
        if supplied != secrets.admin_token:
            raise HTTPException(401, "Sign in to Countersign with the admin token")

    admin = [Depends(require_admin)]

    async def sweep_holds() -> None:
        while True:
            store.expire_due_holds()
            await asyncio.sleep(2)

    async def reconcile() -> None:
        """Ask PayPal what actually happened to each executed move, separately from what the agent was told."""
        while True:
            await asyncio.sleep(8)
            for intent in store.list_intents(limit=50, status="executed"):
                if not intent.paypal_id or (intent.confirmed_status in FINAL_PAYPAL_STATUSES):
                    continue
                try:
                    status = await asyncio.to_thread(backend.money_status, intent.action, intent.paypal_id)
                except (PayPalError, PayPalUnavailable) as exc:
                    log.warning(f"reconcile {intent.id}: {exc}")
                    continue
                if status != intent.confirmed_status:
                    store.update_intent(intent.id, "paypal_confirmed", confirmed_status=status, confirmed_at=now().isoformat())

    async def explain_holds() -> None:
        if not explainer.enabled:
            return
        while True:
            await asyncio.sleep(1)
            for intent in store.list_intents(limit=20, status="held"):
                if intent.explanation is not None:
                    continue
                try:
                    explanation = await explainer.explain(intent)
                except EXPLAINER_ERRORS as exc:
                    explanation = {"error": f"AI explanation unavailable: {type(exc).__name__}"}
                store.update_intent(intent.id, "hold_explained", explanation=explanation or {"error": "No explanation returned"})

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if os.environ.get("COUNTERSIGN_EXTERNAL_GATEWAY") != "1":
            state["gateway"] = await start_gateway(settings, secrets)
            log.info(f"Gateway started (pid {state['gateway'].pid}), MCP on 127.0.0.1:{settings.gateway_mcp_port}")
        tasks = [asyncio.create_task(job()) for job in (sweep_holds, reconcile, explain_holds)]
        log.info(f"Countersign {__version__} on {settings.public_url} — backend: {settings.backend_label}")
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            gateway = state["gateway"]
            if gateway and gateway.returncode is None:
                gateway.terminate()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(gateway.wait(), 10)

    app = FastAPI(
        title="Countersign", version=__version__, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.include_router(make_router(settings, secrets, store))

    # Session ----------------------------------------------------------------------

    @app.post("/api/login")
    async def login(body: Login, response: Response) -> dict[str, bool]:
        if body.token != secrets.admin_token:
            raise HTTPException(401, "Wrong admin token")
        response.set_cookie(COOKIE, body.token, httponly=True, samesite="lax", secure=is_public(), max_age=60 * 60 * 24 * 30)
        return {"ok": True}

    @app.post("/api/logout")
    async def logout(response: Response) -> dict[str, bool]:
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/status")
    async def status(request: Request) -> dict[str, Any]:
        gateway = state["gateway"]
        signed_in = request.cookies.get(COOKIE) == secrets.admin_token
        return {
            "name": "Countersign",
            "version": __version__,
            "backend": settings.backend,
            "backend_label": settings.backend_label,
            "gateway_running": gateway is None or gateway.returncode is None,
            "public_url": settings.public_url,
            "public": is_public(),
            "ai_explanations": explainer.enabled,
            "ai_model": explainer.model if explainer.enabled else None,
            "approval_timeout_s": settings.approval_timeout_s,
            "demo_shop": settings.demo_shop,
            "signed_in": signed_in,
        }

    # Money trail -------------------------------------------------------------------

    def intent_view(intent: Any) -> dict[str, Any]:
        data = intent.to_dict()
        agent = store.get_agent(intent.agent_id)
        data["agent_name"] = agent["name"] if agent else intent.context.get("agent_name", "Unknown agent")
        data["client"] = agent["client"] if agent else intent.context.get("client")
        data["amount_value"] = float(intent.amount) if intent.amount.replace(".", "", 1).isdigit() else None
        return data

    @app.get("/api/intents", dependencies=admin)
    async def list_intents(status: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        return [intent_view(i) for i in store.list_intents(limit=min(limit, 2000), status=status)]

    @app.get("/api/intents/{intent_id}", dependencies=admin)
    async def get_intent(intent_id: str) -> dict[str, Any]:
        intent = store.get_intent(intent_id)
        if intent is None:
            raise HTTPException(404, "No such intent")
        return intent_view(intent)

    @app.post("/api/intents/{intent_id}/decision", dependencies=admin)
    async def decide(intent_id: str, body: Decision) -> dict[str, Any]:
        via = body.via if body.via in ("console", "phone") else "console"
        decided = store.decide(intent_id, body.approve, decided_by=f"human via {via}")
        if decided is None:
            current = store.get_intent(intent_id)
            raise HTTPException(409, f"This move is {current.status if current else 'unknown'} and can no longer be decided")
        return intent_view(decided)

    @app.get("/api/summary", dependencies=admin)
    async def summary() -> dict[str, Any]:
        data = store.summary(now() - timedelta(hours=24))
        data["agents"] = len([a for a in store.list_agents() if a["active"]])
        data["held_now"] = len(store.list_intents(limit=200, status="held"))
        return data

    @app.post("/api/ask-grid", dependencies=admin)
    async def ask_grid(body: GridQuestion) -> dict[str, Any]:
        if not explainer.enabled:
            raise HTTPException(503, "AI search is off: set COUNTERSIGN_EXPLAINER (see Setup)")
        try:
            result = await explainer.grid_filter(body.question)
        except EXPLAINER_ERRORS as exc:
            raise HTTPException(502, f"AI search failed: {type(exc).__name__}") from exc
        if result is None:
            raise HTTPException(422, "Claude could not turn that into a filter")
        return result

    @app.get("/api/stream", dependencies=admin)
    async def stream(request: Request) -> StreamingResponse:
        async def events() -> AsyncIterator[bytes]:
            last = store.last_event_id()
            yield b": connected\n\n"
            ticks = 0
            while not await request.is_disconnected():
                batch = store.events_after(last)
                for event in batch:
                    last = event["id"]
                    yield f"data: {json.dumps(event, default=str)}\n\n".encode()
                ticks += 1
                if ticks % 30 == 0:
                    yield b": heartbeat\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    # Agents ------------------------------------------------------------------------

    @app.get("/api/clients", dependencies=admin)
    async def clients() -> list[dict[str, Any]]:
        return CLIENTS

    @app.get("/api/agents", dependencies=admin)
    async def agents() -> list[dict[str, Any]]:
        since = now() - timedelta(hours=24)
        result = []
        for agent in store.list_agents():
            currencies = agent["mandate"].get("currencies") or ["USD"]
            agent["spent_24h"] = {c: store.spent_since(agent["id"], c, since) for c in currencies}
            result.append(agent)
        return result

    @app.post("/api/agents", dependencies=admin)
    async def create_agent(body: NewAgent) -> dict[str, Any]:
        if body.client not in CLIENT_IDS:
            raise HTTPException(422, f"Unknown client {body.client}")
        try:
            mandate = normalize_mandate(body.mandate or DEFAULT_MANDATE)
        except (MoneyError, ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        agent, key = store.create_agent(body.name, body.client, mandate)
        url = mcp_url(settings.public_url, key)
        return {"agent": agent, "key": key, "connect": instructions(body.client, url, is_public())}

    @app.patch("/api/agents/{agent_id}", dependencies=admin)
    async def update_agent(agent_id: str, body: AgentUpdate) -> dict[str, Any]:
        if store.get_agent(agent_id) is None:
            raise HTTPException(404, "No such agent")
        if body.mandate is not None:
            try:
                store.update_mandate(agent_id, normalize_mandate(body.mandate))
            except (MoneyError, ValueError, KeyError) as exc:
                raise HTTPException(422, str(exc)) from exc
        if body.active is not None:
            store.set_agent_active(agent_id, body.active)
        return store.get_agent(agent_id) or {}

    @app.post("/api/agents/{agent_id}/rotate", dependencies=admin)
    async def rotate(agent_id: str) -> dict[str, Any]:
        agent = store.get_agent(agent_id)
        key = store.rotate_agent_key(agent_id)
        if agent is None or key is None:
            raise HTTPException(404, "No such agent")
        return {
            "agent": agent,
            "key": key,
            "connect": instructions(agent["client"], mcp_url(settings.public_url, key), is_public()),
        }

    # Test payments (real sandbox checkout, or simulated) ------------------------------

    @app.post("/api/test-payments", dependencies=admin)
    async def create_test_payment(body: TestPayment) -> dict[str, Any]:
        try:
            amount = fmt(parse_amount(body.amount))
            checkout = await asyncio.to_thread(backend.create_checkout, amount, body.currency.upper(), body.description)
            if checkout.status == "APPROVED":
                checkout = await asyncio.to_thread(backend.capture_checkout, checkout.order_id)
        except (MoneyError, PayPalError, PayPalUnavailable) as exc:
            raise HTTPException(502, str(exc)) from exc
        store.add_event(
            "test_payment_created", order_id=checkout.order_id, capture_id=checkout.capture_id, backend=settings.backend
        )
        return checkout.__dict__ | {"backend": settings.backend_label}

    @app.post("/api/test-payments/{order_id}/capture", dependencies=admin)
    async def capture_test_payment(order_id: str) -> dict[str, Any]:
        try:
            checkout = await asyncio.to_thread(backend.capture_checkout, order_id)
        except (PayPalError, PayPalUnavailable) as exc:
            raise HTTPException(502, str(exc)) from exc
        if checkout.capture_id:
            store.add_event("test_payment_captured", order_id=order_id, capture_id=checkout.capture_id)
        return checkout.__dict__

    # Chaos bench ---------------------------------------------------------------------

    bench_file = settings.data_dir / "bench" / "latest.json"

    @app.get("/api/bench", dependencies=admin)
    async def bench_latest() -> dict[str, Any]:
        return json.loads(bench_file.read_text()) if bench_file.exists() else {"status": "not_run"}

    @app.post("/api/bench/run", dependencies=admin)
    async def bench_run() -> dict[str, Any]:
        bench_file.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "bench.run",
            "--output",
            str(bench_file),
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output, _ = await process.communicate()
        if process.returncode != 0:
            raise HTTPException(500, f"Bench failed: {output.decode()[-800:]}")
        return json.loads(bench_file.read_text())

    # PayPal webhooks (sandbox) ---------------------------------------------------------

    @app.post("/webhooks/paypal")
    async def paypal_webhook(request: Request) -> JSONResponse:
        if not isinstance(backend, SandboxBackend) or not settings.paypal_webhook_id:
            return JSONResponse({"ignored": "webhooks need COUNTERSIGN_BACKEND=sandbox and PAYPAL_WEBHOOK_ID"}, status_code=202)
        event = await request.json()
        headers = {k.lower(): v for k, v in request.headers.items()}
        try:
            verified = await asyncio.to_thread(backend.verify_webhook, headers, event, settings.paypal_webhook_id)
        except (PayPalError, PayPalUnavailable):
            verified = False
        if not verified:
            return JSONResponse({"error": "signature not verified"}, status_code=400)
        resource = event.get("resource", {})
        paypal_id = resource.get("id") or resource.get("payout_batch_id")
        status_value = resource.get("status") or resource.get("transaction_status")
        for intent in store.list_intents(limit=500):
            if paypal_id and intent.paypal_id == paypal_id:
                store.update_intent(intent.id, "paypal_webhook", confirmed_status=status_value, confirmed_at=now().isoformat())
        store.add_event("paypal_webhook", event_type=event.get("event_type"), paypal_id=paypal_id)
        return JSONResponse({"ok": True})

    # Console (single-page app) ---------------------------------------------------------

    if (CONSOLE_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=CONSOLE_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> Response:
        if path.startswith(("api/", "mcp/", "webhooks/")):
            raise HTTPException(404)
        candidate = (CONSOLE_DIST / path).resolve()
        if path and candidate.is_file() and CONSOLE_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        index = CONSOLE_DIST / "index.html"
        if index.exists():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"error": "Console not built. Run `make console`."}, status_code=503)

    return app


def run(settings: Settings | None = None) -> None:
    import uvicorn

    settings = settings or load_settings()
    secrets = load_secrets(settings.data_dir)
    print(f"\n  Countersign console: {settings.public_url}/?token={secrets.admin_token}")
    print(f"  Backend: {settings.backend_label}\n")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")
