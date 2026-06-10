"""
Unit tests for temporal/src/config.py.

Each test creates a fresh Settings() instance after adjusting env vars so
the module-level singleton in config.py does not interfere.
"""
import pytest
from config import Settings


ALL_VARS = [
    "TEMPORAL_ADDRESS",
    "TEMPORAL_NAMESPACE",
    "TEMPORAL_TASK_QUEUE",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "AZURE_AI_ENDPOINT",
    "AZURE_AI_KEY",
    "AZURE_AI_MODEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ALL_VARS:
        monkeypatch.delenv(var, raising=False)


class TestDefaults:
    def test_temporal_address(self):
        assert Settings().temporal_address == "temporal:7233"

    def test_temporal_namespace(self):
        assert Settings().temporal_namespace == "default"

    def test_temporal_task_queue(self):
        assert Settings().temporal_task_queue == "main"

    def test_supabase_url(self):
        assert Settings().supabase_url == "http://host.docker.internal:54321"

    def test_supabase_service_role_key_is_empty_string(self):
        # Must be empty string, not None — callers pass it to headers without None check
        key = Settings().supabase_service_role_key
        assert key == ""
        assert key is not None

    def test_azure_ai_model(self):
        assert Settings().azure_ai_model == "gpt-4o"

    def test_azure_credentials_default_to_empty_string(self):
        s = Settings()
        assert s.azure_ai_endpoint == ""
        assert s.azure_ai_key == ""


class TestEnvVarOverrides:
    def test_temporal_address(self, monkeypatch):
        monkeypatch.setenv("TEMPORAL_ADDRESS", "localhost:7233")
        assert Settings().temporal_address == "localhost:7233"

    def test_temporal_namespace(self, monkeypatch):
        monkeypatch.setenv("TEMPORAL_NAMESPACE", "production")
        assert Settings().temporal_namespace == "production"

    def test_temporal_task_queue(self, monkeypatch):
        monkeypatch.setenv("TEMPORAL_TASK_QUEUE", "high-priority")
        assert Settings().temporal_task_queue == "high-priority"

    def test_supabase_url(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "http://supabase-kong:8000")
        assert Settings().supabase_url == "http://supabase-kong:8000"

    def test_supabase_service_role_key(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "super-secret-key")
        assert Settings().supabase_service_role_key == "super-secret-key"

    def test_azure_ai_model(self, monkeypatch):
        monkeypatch.setenv("AZURE_AI_MODEL", "gpt-4-turbo")
        assert Settings().azure_ai_model == "gpt-4-turbo"

    def test_azure_ai_endpoint(self, monkeypatch):
        monkeypatch.setenv("AZURE_AI_ENDPOINT", "https://my-resource.openai.azure.com")
        assert Settings().azure_ai_endpoint == "https://my-resource.openai.azure.com"

    def test_azure_ai_key(self, monkeypatch):
        monkeypatch.setenv("AZURE_AI_KEY", "secret-azure-key-value")
        assert Settings().azure_ai_key == "secret-azure-key-value"
