"""PayPal backends. Chosen explicitly by COUNTERSIGN_BACKEND; never swapped silently."""

from __future__ import annotations

from countersign.paypal.sandbox import SandboxBackend
from countersign.paypal.simulator import SimulatedBackend
from countersign.paypal.types import PaymentsBackend
from countersign.settings import Settings


def make_backend(settings: Settings) -> PaymentsBackend:
    if settings.backend == "sandbox":
        return SandboxBackend(settings.paypal_client_id, settings.paypal_client_secret)
    return SimulatedBackend(settings.simulator_db_path)
