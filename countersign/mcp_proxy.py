"""Authenticated MCP endpoint: /mcp/{agent_key}/ → the local gateway.

The key in the path identifies the agent, so clients that only accept a URL
(claude.ai, ChatGPT) work without OAuth. The proxy signs each forwarded
request with the agent id; the gateway trusts nothing else.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from countersign.gateway_hook import AGENT_HEADER, sign_agent
from countersign.settings import Secrets, Settings
from countersign.store import Store

FORWARD_HEADERS = {"accept", "content-type", "mcp-session-id", "mcp-protocol-version", "last-event-id", "user-agent"}
RETURN_HEADERS = {"content-type", "mcp-session-id", "cache-control"}


def make_router(settings: Settings, secrets: Secrets, store: Store) -> APIRouter:
    router = APIRouter()
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5, read=None, write=30, pool=5))
    upstream = f"http://127.0.0.1:{settings.gateway_mcp_port}/mcp/"

    async def forward(key: str, request: Request) -> Response:
        agent = store.agent_by_key(key)
        if agent is None:
            return JSONResponse({"error": "Unknown or revoked Countersign agent key"}, status_code=401)
        headers = {k: v for k, v in request.headers.items() if k.lower() in FORWARD_HEADERS}
        headers[AGENT_HEADER] = sign_agent(agent["id"], secrets.gateway_secret)
        body = await request.body()
        try:
            upstream_request = client.build_request(request.method, upstream, headers=headers, content=body)
            upstream_response = await client.send(upstream_request, stream=True)
        except httpx.HTTPError:
            return JSONResponse({"error": "Countersign gateway is starting or unavailable"}, status_code=503)
        session_id = upstream_response.headers.get("mcp-session-id") or request.headers.get("mcp-session-id")
        store.touch_agent(agent["id"], session_id)
        return StreamingResponse(
            upstream_response.aiter_raw(),
            status_code=upstream_response.status_code,
            headers={k: v for k, v in upstream_response.headers.items() if k.lower() in RETURN_HEADERS},
            background=BackgroundTask(upstream_response.aclose),
        )

    @router.api_route("/mcp/{key}", methods=["GET", "POST", "DELETE"], include_in_schema=False)
    @router.api_route("/mcp/{key}/", methods=["GET", "POST", "DELETE"], include_in_schema=False)
    async def mcp_endpoint(key: str, request: Request) -> Response:
        return await forward(key, request)

    return router
