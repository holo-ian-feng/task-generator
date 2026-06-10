import pytest

# Settings env vars that tests may set or clear
SETTINGS_ENV_VARS = [
    "TEMPORAL_ADDRESS",
    "TEMPORAL_NAMESPACE",
    "TEMPORAL_TASK_QUEUE",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "AZURE_AI_ENDPOINT",
    "AZURE_AI_KEY",
    "AZURE_AI_MODEL",
]


@pytest.fixture
def clear_settings_env(monkeypatch):
    """Remove all Settings-related env vars so each test starts from defaults."""
    for var in SETTINGS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
