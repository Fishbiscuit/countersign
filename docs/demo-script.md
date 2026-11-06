# Demo video script (about 3 minutes)

Record with a real person speaking. Use the PayPal Sandbox backend so PayPal ids are real. Before recording:
- Countersign is deployed (or running locally for Claude Code);
- `COUNTERSIGN_EXPLAINER=claude-code` is in `.env` and Claude Code is signed in, so Claude's risk note and Ask the money trail work with no API key;
- `demo/seed.py` has created the shop's payments;
- the phone has the console's `/m` page open and signed in;
- the chaos bench has been run once.

A phone can't reach a local server on `127.0.0.1`, so on a local run use the console's Holds page for the phone steps.

On a local run, give each take its own data folder for a clean money trail. Your existing trail stays where it is. Run these in the terminal that starts the server:

```bash
export COUNTERSIGN_DATA_DIR=.countersign/take-1
```

```bash
mkdir -p "$COUNTERSIGN_DATA_DIR/demo" && cp .countersign/demo/payments.json "$COUNTERSIGN_DATA_DIR/demo/"
```

```bash
make serve
```

Sign in with the link from this command, in a second terminal that also has `COUNTERSIGN_DATA_DIR` set:

```bash
uv run countersign token
```

The payments are reused, so a new folder needs no new checkouts. The shop's sandbox orders have enough left for two more takes (1042 has 24.00 refundable, and each take uses 12.00). After that, run `demo/seed.py` in a new folder.

| Time | On screen | Say |
| --- | --- | --- |
| 0:00 | Chaos bench page: **631.00** vs **0.00** | "AI agents can move money now. These are six ways that goes wrong, and how much money an agent with direct PayPal tools moved that it shouldn't have." |
| 0:20 | Agents → Connect an agent → Claude Code; paste the command in a terminal | "Countersign gives every agent its own URL and its own mandate. This is Claude Code connecting." |
| 0:40 | Terminal: `demo/support_agent.py` working the shop inbox. Console live wire: 12.00 refund **Paid**, PayPal id | "A small fair refund goes straight through. That's a real PayPal Sandbox refund." |
| 1:00 | Phone: 40.00 late-delivery refund → **Countersign**; seal; console shows it Paid, then "PayPal says COMPLETED" | "This one's over the limit, so it waits for me. It's fair, so I countersign it, and PayPal confirms it independently." |
| 1:20 | Terminal: Claude's summary flags T-1003 and T-1004 | "Two of these tickets were attacks: a fake manager's note and a look-alike payee. Claude caught both itself. Countersign can't depend on that, so here's a script with no judgement. It isn't an AI. It asks for whatever a ticket says." |
| 1:35 | Terminal: `uv run python demo/naive_agent.py`. Hold card: 450.00, prompt injection highlighted, Claude's risk note | "It went straight for the whole 450. The rules held it, and Claude explains why it looks wrong. Claude never decides; I do." |
| 1:50 | Phone: tap **Deny**; the DENIED seal lands. Next hold: 35.00 to the look-alike address; **Deny** | "From my phone: denied. Nothing was paid, and the agent is told not to retry. The look-alike payout held too, because that address has never been paid." |
| 2:05 | Money trail drawer: PayPal-Request-Id, attempts | "Every money move gets one PayPal request id. If a response is lost and the agent retries, PayPal returns the first refund instead of paying twice." |
| 2:25 | Ask the money trail: "held payouts over $20" → AG Grid filters; Bryntum timeline | "Ask the trail in plain English. Claude turns it into a grid filter." |
| 2:45 | Live page, then the seal logo | "Countersign: a second signature on every money move an AI agent makes. Built on the open-source OpenEdison gateway, the PayPal Sandbox, Claude, AG Grid, Bryntum and Render." |

Each hold waits 90 seconds, then expires with nothing paid. The agent waits at the hold, so decide within that time. `demo/naive_agent.py` works only T-1003 and T-1004 unless you name others.
