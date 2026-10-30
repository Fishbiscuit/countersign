"""Check that the PayPal Sandbox keys in .env work, without printing them.

Usage: uv run python -m bench.check_keys
"""

from __future__ import annotations

import sys

from countersign.paypal.sandbox import SandboxBackend
from countersign.paypal.types import PayPalError, PayPalUnavailable
from countersign.settings import SettingsError, load_settings


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(exc)
        return 1
    if settings.backend != "sandbox":
        print(f"COUNTERSIGN_BACKEND is {settings.backend!r}, not 'sandbox'")
        return 1
    try:
        SandboxBackend(settings.paypal_client_id, settings.paypal_client_secret)._access_token()
    except (PayPalError, PayPalUnavailable) as exc:
        print(f"PayPal Sandbox rejected the keys: {exc}")
        return 1
    print("PayPal Sandbox accepted the keys (access token issued).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
