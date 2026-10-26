"""How each AI client connects to its Countersign URL.

Every client gets the same thing: a streamable-HTTP MCP endpoint whose path
carries that agent's key. Clients that run in the cloud (claude.ai, ChatGPT,
Muse, Dots) can only reach a public HTTPS URL, so the console says so when
Countersign is running on localhost.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import quote

CLIENTS: list[dict[str, Any]] = [
    {"id": "claude-code", "name": "Claude Code", "cloud": False},
    {"id": "claude", "name": "Claude (claude.ai and Desktop)", "cloud": True},
    {"id": "chatgpt", "name": "ChatGPT", "cloud": True},
    {"id": "openclaw", "name": "OpenClaw", "cloud": False},
    {"id": "cursor", "name": "Cursor", "cloud": False},
    {"id": "grok", "name": "Grok", "cloud": True},
    {"id": "vscode", "name": "VS Code (Copilot agent mode)", "cloud": False},
    {"id": "goose", "name": "Goose", "cloud": False},
    {"id": "other", "name": "Any other MCP client (Muse, Dots, your own)", "cloud": True},
]
CLIENT_IDS = {c["id"] for c in CLIENTS}


def mcp_url(public_url: str, key: str) -> str:
    return f"{public_url}/mcp/{key}/"


def instructions(client: str, url: str, is_public: bool) -> dict[str, Any]:
    """Copy-ready steps for one client. `url` already contains the agent's key."""
    meta = next((c for c in CLIENTS if c["id"] == client), CLIENTS[-1])
    steps: list[str] = []
    command: str | None = None
    link: str | None = None
    if client == "claude-code":
        command = f"claude mcp add --transport http countersign {url}"
        steps = ["Run the command in your project.", "Then run /mcp inside Claude Code to check it is connected."]
    elif client == "claude":
        steps = [
            "Settings → Connectors → Add custom connector.",
            "Name: Countersign. Remote MCP server URL: the URL below. No OAuth needed: the key is in the URL.",
            "Turn the connector on in a chat from the tools menu.",
        ]
    elif client == "chatgpt":
        steps = [
            "Settings → Apps & Connectors → Advanced settings → turn on Developer mode.",
            "Back in Connectors, choose Create. MCP server URL: the URL below. Authentication: No authentication.",
            "Start a new chat and enable Countersign from the tools menu.",
        ]
    elif client == "openclaw":
        command = f"openclaw mcp add countersign --url {url} --transport streamable-http"
        steps = [
            "Run the command, then `openclaw mcp doctor countersign --probe`.",
            "Restart the OpenClaw gateway if it was running.",
        ]
    elif client == "cursor":
        config = base64.b64encode(json.dumps({"url": url}).encode()).decode()
        link = f"https://cursor.com/en/install-mcp?name=countersign&config={quote(config)}"
        steps = ["Open the install link, or add the URL under Settings → MCP → Add server."]
    elif client == "vscode":
        config = quote(json.dumps({"type": "http", "url": url}))
        link = f"https://vscode.dev/redirect/mcp/install?name=countersign&config={config}"
        steps = ["Open the install link (needs Copilot agent mode)."]
    elif client == "goose":
        link = f"https://block.github.io/goose/extension?url={quote(url)}&type=streamable_http&id=countersign&name=Countersign"
        steps = ["Open the install link in Goose."]
    elif client == "grok":
        steps = ["Add a remote MCP server over streamable HTTP with the URL below."]
    else:
        steps = [
            "Add a remote MCP server, transport streamable HTTP, with the URL below.",
            "Agents that build their own MCP client (for example Muse) can be told: connect to this MCP server URL.",
        ]
    warning = None
    if meta["cloud"] and not is_public:
        warning = (
            f"{meta['name']} runs in the cloud and cannot reach this computer. Deploy Countersign "
            "(for example the Render blueprint) or expose it on a public HTTPS URL first."
        )
    return {
        "client": meta["id"],
        "name": meta["name"],
        "url": url,
        "command": command,
        "link": link,
        "steps": steps,
        "warning": warning,
    }
