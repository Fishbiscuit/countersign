"""Idempotency against the real PayPal Sandbox (needs sandbox app credentials in .env).

Creates one sandbox payment (you approve it once as the sandbox buyer), then:

  A  retry a 1.00 refund without a PayPal-Request-Id   → expect two refunds (the failure mode)
  B  retry a 1.00 refund with the same PayPal-Request-Id → expect the same refund back
  C  force a failure with PayPal-Mock-Response, then retry with the same id → record PayPal's behaviour

Usage: uv run python -m bench.sandbox_check [--output docs/sandbox-check.json] [--capture <existing capture id>]
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from countersign.paypal.sandbox import SandboxBackend
from countersign.paypal.types import PayPalError
from countersign.settings import load_settings


def fresh_capture(paypal: SandboxBackend) -> str:
    checkout = paypal.create_checkout("20.00", "USD", "Countersign sandbox idempotency check")
    print(f"Approve this sandbox checkout as the sandbox buyer:\n  {checkout.approve_url}", flush=True)
    for _ in range(360):
        time.sleep(5)
        captured = paypal.capture_checkout(checkout.order_id)
        if captured.capture_id:
            return captured.capture_id
    raise SystemExit("Checkout was not approved within 30 minutes")


def refund_id(paypal: SandboxBackend, capture: str, request_id: str | None, mock: str | None = None) -> str:
    return str(
        paypal.call(
            "POST",
            f"/v2/payments/captures/{capture}/refund",
            {"amount": {"value": "1.00", "currency_code": "USD"}},
            request_id=request_id,
            mock_code=mock,
        )["id"]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--capture", help="Use an existing sandbox capture with at least 4.00 refundable")
    args = parser.parse_args()

    settings = load_settings()
    if settings.backend != "sandbox":
        raise SystemExit("Set COUNTERSIGN_BACKEND=sandbox with PayPal sandbox credentials first.")
    paypal = SandboxBackend(settings.paypal_client_id, settings.paypal_client_secret)
    capture = args.capture or fresh_capture(paypal)
    run = uuid.uuid4().hex[:8]
    report: dict[str, Any] = {"checked_at": datetime.now(UTC).isoformat(timespec="seconds"), "capture_id": capture}

    a1, a2 = refund_id(paypal, capture, None), refund_id(paypal, capture, None)
    report["A_no_request_id"] = {"refund_ids": [a1, a2], "paid_twice": a1 != a2}

    key_b = f"cs-check-b-{run}"
    b1, b2 = refund_id(paypal, capture, key_b), refund_id(paypal, capture, key_b)
    report["B_same_request_id"] = {"refund_ids": [b1, b2], "paid_once": b1 == b2}

    key_c = f"cs-check-c-{run}"
    try:
        refund_id(paypal, capture, key_c, mock="INTERNAL_SERVER_ERROR")
        mocked: dict[str, Any] = {"error": None}
    except PayPalError as exc:
        mocked = {"status": exc.status, "name": exc.name, "debug_id": exc.debug_id}
    try:
        c1, c2 = refund_id(paypal, capture, key_c), refund_id(paypal, capture, key_c)
        retry: dict[str, Any] = {"refund_ids": [c1, c2], "paid_once": c1 == c2}
    except PayPalError as exc:
        retry = {"error": f"{exc.status} {exc.name}: {exc.message}", "debug_id": exc.debug_id}
    report["C_mocked_failure_then_retry"] = {"mocked_attempt": mocked, "retry_with_same_id": retry}
    report["capture_status_after"] = paypal.get_payment(capture).status

    print(json.dumps(report, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    ok = report["A_no_request_id"]["paid_twice"] and report["B_same_request_id"]["paid_once"]
    print("SANDBOX CHECK PASS" if ok else "SANDBOX CHECK: unexpected result, see above")


if __name__ == "__main__":
    main()
