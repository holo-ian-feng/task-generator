"""
Regression tests for confirmed adversarial findings in config.py.

Each test is xfail(strict=True): it MUST fail until the defect is fixed.
When a defect is fixed, pytest reports XPASS — remove the xfail mark at that point
to graduate the test into the permanent suite.
"""
import pytest
from config import Settings

ALL_VARS = [
    "TEMPORAL_ADDRESS", "TEMPORAL_NAMESPACE", "TEMPORAL_TASK_QUEUE",
    "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
    "AZURE_AI_ENDPOINT", "AZURE_AI_KEY", "AZURE_AI_MODEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ALL_VARS:
        monkeypatch.delenv(var, raising=False)


# ── Defect #6 ─────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="DEFECT #6a: Settings accepts empty string for SUPABASE_SERVICE_ROLE_KEY. "
           "The Temporal worker starts successfully, registers with the Temporal server, "
           "then silently fails every Supabase API call with 401. Jobs pile up in 'pending' "
           "indefinitely with no startup error or alert. "
           "Fix: add a pydantic field_validator that raises ValidationError when this field is empty, "
           "so the worker crashes immediately at startup with a clear misconfiguration message.",
)
def test_empty_service_role_key_raises_at_startup(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    with pytest.raises(Exception):
        Settings()


@pytest.mark.xfail(
    strict=True,
    reason="DEFECT #6b: Settings accepts empty string for AZURE_AI_KEY. "
           "The worker starts and registers workflows, but every call_ai_for_tickets activity "
           "fails at runtime. The misconfiguration is only discovered when the first AI call "
           "is attempted, not at startup. "
           "Fix: add a pydantic field_validator that raises ValidationError when this field is empty.",
)
def test_empty_azure_ai_key_raises_at_startup(monkeypatch):
    monkeypatch.setenv("AZURE_AI_KEY", "")
    with pytest.raises(Exception):
        Settings()


# ── Defect #9 ─────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="DEFECT #9: Settings does not validate that TEMPORAL_ADDRESS includes a port. "
           "Setting TEMPORAL_ADDRESS=temporal (no :7233) causes Client.connect() to attempt "
           "gRPC on port 443 (TLS default), producing a deep stack trace with no mention of "
           "'missing port'. Operators cannot diagnose the misconfiguration from the error alone. "
           "Fix: add a field_validator that raises ValueError if ':' is not in the address value.",
)
def test_temporal_address_without_port_raises_at_startup(monkeypatch):
    monkeypatch.setenv("TEMPORAL_ADDRESS", "temporal")  # missing :7233
    with pytest.raises(Exception):
        Settings()
