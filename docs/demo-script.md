# Demo video script (about 3 minutes)

Record with a real person speaking. Use the PayPal Sandbox backend so PayPal ids are real. Before recording:
- Countersign is deployed (or running locally for Claude Code);
- `demo/seed.py` has created the shop's payments;
- the phone has the console's `/m` page open and signed in;
- the chaos bench has been run once.

| Time | On screen | Say |
| --- | --- | --- |
| 0:00 | Chaos bench page: **631.00** vs **0.00** | "AI agents can move money now. These are six ways that goes wrong, and how much money an agent with direct PayPal tools moved that it shouldn't have." |
| 0:20 | Agents → Connect an agent → Claude Code; paste the command in a terminal | "Countersign gives every agent its own URL and its own mandate. This is Claude Code connecting." |
| 0:40 | Terminal: `demo/support_agent.py` working the shop inbox. Console live wire: 12.00 refund **Paid**, PayPal id | "A small fair refund goes straight through. That's a real PayPal Sandbox refund." |
| 1:00 | Hold card: 450.00, prompt injection highlighted, Claude's risk note | "This ticket tells the AI a manager approved a full refund. The rules held it, and Claude explains why it looks wrong. Claude never decides; I do." |
| 1:20 | Phone: tap **Deny**; the DENIED seal lands | "From my phone: denied. Nothing was paid, and the agent is told not to retry." |
| 1:40 | Phone: 40.00 late-delivery refund → **Countersign**; seal; console shows it Paid, then "PayPal says COMPLETED" | "This one's fair. I countersign it, and PayPal confirms it independently." |
| 2:05 | Money trail drawer: PayPal-Request-Id, attempts | "Every money move gets one PayPal request id. If a response is lost and the agent retries, PayPal returns the first refund instead of paying twice." |
| 2:25 | Ask the money trail: "held payouts over $20" → AG Grid filters; Bryntum timeline | "Ask the trail in plain English. Claude turns it into a grid filter." |
| 2:45 | Live page, then the seal logo | "Countersign: a second signature on every money move an AI agent makes. Built on the open-source OpenEdison gateway, the PayPal Sandbox, Claude, AG Grid, Bryntum and Render." |
