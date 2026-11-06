"""Where Claude's explanations come from is chosen explicitly, like the PayPal backend."""

from pathlib import Path

import pytest

import countersign.settings as settings_module
from countersign.settings import SettingsError, load_settings

CLEARED = (
    "COUNTERSIGN_BACKEND",
    "COUNTERSIGN_DATA_DIR",
    "PAYPAL_CLIENT_ID",
    "PAYPAL_CLIENT_SECRET",
    "ANTHROPIC_API_KEY",
    "COUNTERSIGN_EXPLAINER",
    "COUNTERSIGN_CLAUDE_CODE_MODEL",
)


def load(monkeypatch, tmp_path: Path, **values: str):
    for name in CLEARED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COUNTERSIGN_BACKEND", "simulated")
    monkeypatch.setenv("COUNTERSIGN_DATA_DIR", str(tmp_path))
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    # A .env file that doesn't exist, so the developer's real .env is never read here.
    return load_settings(tmp_path / "no.env")


def test_ai_is_off_without_a_key_or_a_choice(monkeypatch, tmp_path):
    assert load(monkeypatch, tmp_path).explainer == "off"


def test_an_api_key_alone_keeps_the_anthropic_api(monkeypatch, tmp_path):
    assert load(monkeypatch, tmp_path, ANTHROPIC_API_KEY="k").explainer == "anthropic"


def test_claude_code_is_used_only_when_chosen(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_module.shutil, "which", lambda name: f"/opt/bin/{name}")
    chosen = load(monkeypatch, tmp_path, COUNTERSIGN_EXPLAINER="claude-code", ANTHROPIC_API_KEY="k")
    assert chosen.explainer == "claude-code" and chosen.claude_code_bin == "/opt/bin/claude"


@pytest.mark.parametrize(
    "values",
    [
        {"COUNTERSIGN_EXPLAINER": "gpt"},
        {"COUNTERSIGN_EXPLAINER": "anthropic"},
        {"COUNTERSIGN_EXPLAINER": "claude-code"},
    ],
)
def test_a_choice_that_cannot_work_stops_startup(monkeypatch, tmp_path, values):
    monkeypatch.setattr(settings_module.shutil, "which", lambda name: None)
    with pytest.raises(SettingsError):
        load(monkeypatch, tmp_path, **values)
