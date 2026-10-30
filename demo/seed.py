"""Create the demo shop's payments through Countersign's own test-payment API.

PayPal Sandbox: each order needs one buyer approval in a browser (log in with
your sandbox *personal* account); the script waits, then captures it.
Simulated: payments are created and captured immediately.

Usage (Countersign must be running):  python demo/seed.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from countersign.settings import load_secrets, load_settings  # noqa: E402

DEMO_DIR = Path(__file__).resolve().parent


def main() -> int:
    settings = load_settings()
    token = load_secrets(settings.data_dir).admin_token
    api = httpx.Client(base_url=settings.public_url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    shop = json.loads((DEMO_DIR / "tickets.json").read_text())
    out_file = settings.data_dir / "demo" / "payments.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payments = json.loads(out_file.read_text()) if out_file.exists() else {}

    for order in shop["orders"]:
        if order["order"] in payments:
            print(f"Order {order['order']}: already has capture {payments[order['order']]['capture_id']}")
            continue
        body = {"amount": order["amount"], "currency": order["currency"], "description": f"{shop['shop']} order {order['order']}"}
        checkout = api.post("/api/test-payments", json=body).raise_for_status().json()
        if not checkout.get("capture_id"):
            print(f"\nOrder {order['order']} ({order['amount']} {order['currency']}): approve it as the sandbox buyer:")
            print(f"  {checkout['approve_url']}")
            for _ in range(360):
                time.sleep(5)
                checkout = api.post(f"/api/test-payments/{checkout['order_id']}/capture").raise_for_status().json()
                if checkout.get("capture_id"):
                    break
            else:
                print("  Not approved within 30 minutes; skipping.")
                continue
        payments[order["order"]] = {
            "capture_id": checkout["capture_id"],
            "order_id": checkout["order_id"],
            "backend": settings.backend,
        }
        out_file.write_text(json.dumps(payments, indent=2) + "\n")
        print(f"Order {order['order']}: captured {checkout['capture_id']} ({settings.backend_label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
