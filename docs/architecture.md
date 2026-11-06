# Architecture

Countersign is three processes, started by one command (`countersign serve`):

| Process | Listens | Job |
| --- | --- | --- |
| Console (FastAPI + React) | `0.0.0.0:$PORT` (8484 locally) | Agent endpoint `/mcp/{key}/`, console UI and API, PayPal webhooks, background reconciliation and hold explanations |
| Gateway (OpenEdison fork) | `127.0.0.1:3410` (MCP), `:3411` (API) | MCP aggregation, session tracking, lethal-trifecta flags, the Countersign checkpoint |
| Money server (MCP over stdio) | child of the gateway | The only code that moves money |

They share one SQLite file (WAL mode): agents, intents, events, and what each session read.

## A money move, step by step

1. **Agent → console.** `POST /mcp/csk_…/`. The console looks up the key (stored as a SHA-256 hash), then forwards the request to the gateway with `x-countersign-agent: <agent id>.<HMAC>`. Unknown or paused keys get 401.
2. **Gateway session.** OpenEdison identifies the MCP session and its trifecta flags. Tools are classified in `tool_permissions.json`, which Countersign regenerates on every start: ticket reads are untrusted, order and payment lookups are private, refunds and payouts are writes.
3. **Checkpoint** (`countersign/gateway_hook.py`). For `countersign_*` tools the gateway calls the checkpoint before the tool runs:
   - verifies the HMAC agent identity;
   - for money tools, parses amount and currency exactly (decimal strings, never floats) and requires a `reference`;
   - fingerprints the intent: agent, action, target, amount, currency, reference;
   - **known fingerprint (a retry):** executed → replay the earlier receipt; allowed, approved, executing or failed → let it through again with the *same* PayPal-Request-Id; held → wait on the same hold; expired → re-arm the hold; denied or blocked → refuse;
   - **new intent:** gather facts (spend in the last 24 hours, moves in the last minute, earlier moves by any agent to the same target or under the same reference, untrusted content read in this session, private data seen, what is still refundable according to PayPal), evaluate the agent's rules (`countersign/policy.py`), and record the intent with its rule receipt. The `PayPal-Request-Id` comes from the money move and leaves the agent out, so two agents that race past the rules still send PayPal one id.
4. **Decision.** Block → the agent gets a plain refusal. Pass → the intent id is stamped into the tool arguments. Hold → the call waits, polling the intent until a human approves or denies it, or the hold expires (fail closed).
5. **Money server** (`countersign/money_server.py`). Refuses any call whose stamped intent is missing, not approved, or does not match the arguments exactly. Marks the intent `executing`, calls PayPal with the intent's `PayPal-Request-Id`, and records `executed` with PayPal's id and status, or `failed` with PayPal's error and debug id. A lost response or a PayPal 5xx leaves it `executing`, because the money may have moved, and the next retry asks PayPal again with the same id. PayPal replays a repeated refund but refuses a repeated payout batch, so a payout retry reads back the batch that already paid.
6. **Reconciliation.** Every few seconds the console asks PayPal for the status of executed moves (refund status; payout item status) and records it as `confirmed_status`, separate from what the agent was told. Sandbox webhooks are accepted only after PayPal's `verify-webhook-signature` says so.
7. **Explanation.** For each new hold, Claude receives the move, the reasons, and the untrusted content fenced as `<untrusted>` data, and returns structured JSON: risk, headline, signals, suggested decision. The console shows it as advice next to the rule receipt. `COUNTERSIGN_EXPLAINER` chooses where Claude comes from, and Countersign never switches on its own:
   - `anthropic`: the Anthropic API with `ANTHROPIC_API_KEY`;
   - `claude-code`: the local Claude Code CLI on its own sign-in, started with `--tools ""`, `--safe-mode`, `--strict-mcp-config` and `--setting-sources ""`, in an empty temporary folder, with only `PATH`, `HOME` and a few locale variables in its environment. The prompt goes in on stdin, the answer must match the JSON schema, and a call that takes over 60 s is killed;
   - `off`: no notes, and "Ask the money trail" is disabled.

## Why approvals bind to intents, not tools

OpenEdison's own approvals are per session and tool name: approving `refund` lets the next refund through. For money that is too coarse. Countersign's holds are rows in the money trail. The waiting call polls its own intent, and a human decision can be made once, only on a held or expired intent. Approving one 40.00 refund cannot release a different 450.00 one.

## Backends

`COUNTERSIGN_BACKEND` must be `sandbox` or `simulated`; Countersign refuses to start otherwise and never falls back.

- `sandbox` — `countersign/paypal/sandbox.py`, fixed to `https://api-m.sandbox.paypal.com`.
- `simulated` — `countersign/paypal/simulator.py`, labelled "Simulated PayPal" in every view. It enforces refund limits and `PayPal-Request-Id` replay like PayPal, and accepts scripted faults (`lost_response`, `server_error`, `no_answer`) for the chaos bench.

## Changes to OpenEdison

See [gateway/NOTICE.md](../gateway/NOTICE.md), or run `git diff d5a29a3 -- gateway/`.
