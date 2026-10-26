# Contributing

```bash
make install     # Python (uv) and console (npm) dependencies
cp .env.example .env
make serve       # console + gateway on http://127.0.0.1:8484
make dev         # console with hot reload (in a second terminal)
make verify      # lint, console typecheck, tests, acceptance tests
make bench       # chaos bench
```

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- A change to the rules or the money path must keep `make bench` at **0.00** moved that should not have, and both fair refunds paid.
- Tests drive the real code paths. Only network edges (PayPal, Anthropic) may be stubbed, and the simulator is a labelled backend, not a test double hidden in product code.
- Never commit keys, tokens, `.env`, or real customer data. Use the demo shop's tickets for examples.
- Changes under `gateway/` are changes to a GPL-3.0 fork of OpenEdison; note them in `gateway/NOTICE.md`.
