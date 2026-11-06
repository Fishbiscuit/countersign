"""Runtime settings, read from the environment and an optional .env file.

The PayPal backend must be chosen explicitly. Countersign never falls back
from the real PayPal sandbox to the simulator on its own. The same goes for
where Claude's explanations come from.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKENDS = ("sandbox", "simulated")
# anthropic: the Anthropic API with ANTHROPIC_API_KEY (a deployment).
# claude-code: the local Claude Code CLI and its own sign-in, so a local demo needs no API key.
EXPLAINERS = ("anthropic", "claude-code", "off")


class SettingsError(RuntimeError):
    pass


def env(name: str, default: str = "") -> str:
    """An environment value, treating a blank `NAME=` line in .env the same as unset."""
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    backend: str
    paypal_client_id: str
    paypal_client_secret: str
    paypal_webhook_id: str
    host: str
    port: int
    public_url: str
    approval_timeout_s: float
    gateway_mcp_port: int
    gateway_api_port: int
    anthropic_api_key: str
    anthropic_model: str
    demo_shop: bool
    explainer: str = "off"
    claude_code_bin: str = ""
    claude_code_model: str = ""

    @property
    def db_path(self) -> Path:
        return self.data_dir / "countersign.db"

    @property
    def simulator_db_path(self) -> Path:
        return self.data_dir / "simulated-paypal.db"

    @property
    def gateway_dir(self) -> Path:
        return self.data_dir / "gateway"

    @property
    def backend_label(self) -> str:
        return "PayPal Sandbox" if self.backend == "sandbox" else "Simulated PayPal"


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or Path.cwd() / ".env", override=False)
    backend = env("COUNTERSIGN_BACKEND", "").lower()
    if backend not in BACKENDS:
        raise SettingsError(
            "Set COUNTERSIGN_BACKEND to 'sandbox' (real PayPal sandbox API) or 'simulated' "
            "(no PayPal calls). Countersign does not pick one for you."
        )
    client_id = env("PAYPAL_CLIENT_ID", "")
    client_secret = env("PAYPAL_CLIENT_SECRET", "")
    if backend == "sandbox" and not (client_id and client_secret):
        raise SettingsError("COUNTERSIGN_BACKEND=sandbox needs PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (sandbox app).")

    anthropic_api_key = env("ANTHROPIC_API_KEY", "")
    explainer = env("COUNTERSIGN_EXPLAINER", "anthropic" if anthropic_api_key else "off").lower()
    if explainer not in EXPLAINERS:
        raise SettingsError(
            "Set COUNTERSIGN_EXPLAINER to 'anthropic' (needs ANTHROPIC_API_KEY), 'claude-code' (the local Claude Code "
            "CLI, signed in) or 'off'."
        )
    if explainer == "anthropic" and not anthropic_api_key:
        raise SettingsError("COUNTERSIGN_EXPLAINER=anthropic needs ANTHROPIC_API_KEY.")
    claude_code_bin = (shutil.which("claude") or "") if explainer == "claude-code" else ""
    if explainer == "claude-code" and not claude_code_bin:
        raise SettingsError("COUNTERSIGN_EXPLAINER=claude-code needs the Claude Code CLI (`claude`) on PATH and signed in.")

    port = int(env("PORT", env("COUNTERSIGN_PORT", "8484")))
    host = env("COUNTERSIGN_HOST", "127.0.0.1")
    data_dir = Path(env("COUNTERSIGN_DATA_DIR", ".countersign")).expanduser().resolve()
    return Settings(
        data_dir=data_dir,
        backend=backend,
        paypal_client_id=client_id,
        paypal_client_secret=client_secret,
        paypal_webhook_id=env("PAYPAL_WEBHOOK_ID", ""),
        host=host,
        port=port,
        public_url=env("COUNTERSIGN_PUBLIC_URL", env("RENDER_EXTERNAL_URL", f"http://{host}:{port}")).rstrip("/"),
        approval_timeout_s=float(env("COUNTERSIGN_APPROVAL_TIMEOUT", "90")),
        gateway_mcp_port=int(env("COUNTERSIGN_GATEWAY_MCP_PORT", "3410")),
        gateway_api_port=int(env("COUNTERSIGN_GATEWAY_API_PORT", "3411")),
        anthropic_api_key=anthropic_api_key,
        anthropic_model=env("COUNTERSIGN_EXPLAINER_MODEL", "claude-opus-5-5"),
        demo_shop=env("COUNTERSIGN_DEMO_SHOP", "") in ("1", "true", "yes"),
        explainer=explainer,
        claude_code_bin=claude_code_bin,
        # Empty: Claude Code's own default model. The model that answered is recorded with each note.
        claude_code_model=env("COUNTERSIGN_CLAUDE_CODE_MODEL", ""),
    )


@dataclass(frozen=True)
class Secrets:
    admin_token: str
    gateway_secret: str
    gateway_api_key: str


def load_secrets(data_dir: Path) -> Secrets:
    """Per-installation secrets, created once and kept in the data directory (mode 600)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "secrets.json"
    if path.exists():
        values = json.loads(path.read_text())
    else:
        values = {
            "admin_token": os.environ.get("COUNTERSIGN_ADMIN_TOKEN") or secrets.token_urlsafe(24),
            "gateway_secret": secrets.token_urlsafe(32),
            "gateway_api_key": secrets.token_urlsafe(24),
        }
        path.write_text(json.dumps(values, indent=2) + "\n")
        path.chmod(0o600)
    if os.environ.get("COUNTERSIGN_ADMIN_TOKEN"):
        values["admin_token"] = os.environ["COUNTERSIGN_ADMIN_TOKEN"]
    return Secrets(**values)
