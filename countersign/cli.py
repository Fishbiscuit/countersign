"""Command line: `countersign serve | agent | token`."""

from __future__ import annotations

import argparse
import json
import sys

from countersign.settings import SettingsError, load_secrets, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="countersign", description="A second signature on every money move an AI agent makes.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="Run the console, the agent endpoint and the gateway")
    sub.add_parser("token", help="Print the console sign-in link")
    agent = sub.add_parser("agent", help="Create an agent and print its connection URL")
    agent.add_argument("name")
    agent.add_argument("--client", default="claude-code")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"countersign: {exc}", file=sys.stderr)
        return 2

    if args.command == "serve":
        from countersign.console_api import run

        run(settings)
        return 0
    if args.command == "token":
        print(f"{settings.public_url}/?token={load_secrets(settings.data_dir).admin_token}")
        return 0
    if args.command == "agent":
        from countersign.connect import instructions, mcp_url
        from countersign.policy import DEFAULT_MANDATE, normalize_mandate
        from countersign.store import Store

        store = Store(settings.db_path)
        record, key = store.create_agent(args.name, args.client, normalize_mandate(DEFAULT_MANDATE))
        url = mcp_url(settings.public_url, key)
        print(
            json.dumps(
                {"agent": record["id"], "url": url, "connect": instructions(args.client, url, url.startswith("https://"))},
                indent=2,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
