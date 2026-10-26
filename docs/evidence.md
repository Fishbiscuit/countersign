# What has been verified

This page separates what has actually been run from what is still pending. Dates are 2026, Singapore time.

## Verified

| What | How | Result |
| --- | --- | --- |
| Rules, simulator semantics, money trail | `make test` (31 tests) | Pass, 27 Oct |
| A refund through the real agent endpoint, retried, with a fresh nonce in the reference | `tests/test_acceptance.py`: `/mcp/{key}/` → proxy → gateway → money server → simulator | Pass, 27 Oct. One intent, two attempts, one PayPal id, 7.00 refunded once |
| A held move waits for a human, runs after approval | acceptance test | Pass, 27 Oct |
| A denied move pays nothing, and a retry stays denied | acceptance test | Pass, 27 Oct |
| Unknown agent key | acceptance test | 401, 27 Oct |
| Six failure scenarios with and without Countersign | `make bench` (simulator) | Should not have moved: 631.00 directly vs 0.00 through Countersign, 27 Oct |
| Console screens: live, holds and decisions, money trail, agents and connect, bench, timeline, phone | Driven in a browser against a local server, with activity created through real agent URLs | Reviewed 27 Oct |
| OpenEdison gateway holds money calls (amount rule, lethal trifecta) | Kill test T1 in the lab | Pass, 27 Oct |

## Pending

| What | Needs | How to run |
| --- | --- | --- |
| Refunds and payouts against the real PayPal Sandbox | Sandbox app credentials | `COUNTERSIGN_BACKEND=sandbox make serve`, `uv run python demo/seed.py`, then a connected agent |
| `PayPal-Request-Id` idempotency in the sandbox | Sandbox credentials | `uv run python -m bench.sandbox_check --output docs/sandbox-check.json` |
| Claude hold explanations and "Ask the money trail" live | `ANTHROPIC_API_KEY` | Hold a move with the key set; ask the trail a question |
| Real clients: Claude Code, claude.ai, ChatGPT, OpenClaw | A running Countersign (public HTTPS for cloud clients) | Agents → Connect an agent |
| Render deployment | A Render account | Blueprint from `render.yaml` |
