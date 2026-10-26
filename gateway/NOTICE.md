# Gateway provenance

This directory is a fork of **OpenEdison** by Edison Watch (now SealGate):
https://github.com/Edison-Watch/open-edison, commit `3e0e53bc3e8bc83b5d4afd71f38293a7325d8c48`
(archived upstream). License: GPL-3.0 (see `LICENSE`). Upstream readme: `UPSTREAM_README.md`.

The first commit of this repository imports that commit unmodified. Every Countersign change
to these files is in later commits, so `git diff d5a29a3 -- gateway/` shows exactly what was
changed for the PayPal AI Hackathon:

- `src/middleware/session_tracking.py`: calls Countersign's checkpoint for every Countersign tool;
  money moves become intents with per-agent rules and human holds; the lethal trifecta on a money
  tool becomes a hold on that exact call; untrusted tool output is remembered for the human;
  the internal intent argument is hidden from agents.
- `src/middleware/data_access_tracker.py`: block messages are plain text. Upstream asked the agent
  to "print the following ASCII art", which is itself an instruction injected into its context.
- `src/single_user_mcp.py`: built-in demo tools can be switched off (`COUNTERSIGN_HIDE_BUILTINS=1`).

Thanks to the SealGate / Edison Watch team for open-sourcing it.
