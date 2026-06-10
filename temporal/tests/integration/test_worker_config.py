"""
Integration tests verifying that Settings field names and defaults align
with the env var names and values in docker-compose.prod.yml.

These tests catch drift between what docker-compose sets and what Settings reads.
"""
import pytest
import yaml
import paths
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


@pytest.fixture(scope="module")
def worker_env():
    """Parse the temporal-worker env block from docker-compose.prod.yml into a dict."""
    with open(paths.DOCKER_COMPOSE_PROD) as f:
        compose = yaml.safe_load(f)
    env_list = compose["services"]["temporal-worker"]["environment"]
    result = {}
    for item in env_list:
        if "=" in item:
            k, v = item.split("=", 1)
            result[k] = v
        else:
            result[item] = None
    return result


class TestEnvVarCoverage:
    """Every Settings field must be explicitly set in the worker service, with correct values."""

    def test_temporal_address_value(self, worker_env):
        assert worker_env.get("TEMPORAL_ADDRESS") == "temporal:7233"

    def test_temporal_namespace_present(self, worker_env):
        # Value uses ${:-default} interpolation; assert key exists and is non-empty
        assert "TEMPORAL_NAMESPACE" in worker_env
        assert worker_env["TEMPORAL_NAMESPACE"]

    def test_temporal_task_queue_present(self, worker_env):
        assert "TEMPORAL_TASK_QUEUE" in worker_env
        assert worker_env["TEMPORAL_TASK_QUEUE"]

    def test_supabase_url_value(self, worker_env):
        assert worker_env.get("SUPABASE_URL") == "http://supabase-kong:8000"

    def test_supabase_service_role_key_is_secret_ref(self, worker_env):
        # Must be a ${SECRET} reference, not a hardcoded value
        val = worker_env.get("SUPABASE_SERVICE_ROLE_KEY", "")
        assert val.startswith("${") and val.endswith("}"), (
            f"SUPABASE_SERVICE_ROLE_KEY should be a secret reference, got: {val!r}"
        )

    def test_azure_ai_endpoint_is_secret_ref(self, worker_env):
        val = worker_env.get("AZURE_AI_ENDPOINT", "")
        assert val.startswith("${") and val.endswith("}"), (
            f"AZURE_AI_ENDPOINT should be a secret reference, got: {val!r}"
        )

    def test_azure_ai_key_is_secret_ref(self, worker_env):
        val = worker_env.get("AZURE_AI_KEY", "")
        assert val.startswith("${") and val.endswith("}"), (
            f"AZURE_AI_KEY should be a secret reference, got: {val!r}"
        )

    def test_azure_ai_model_present(self, worker_env):
        assert "AZURE_AI_MODEL" in worker_env
        assert worker_env["AZURE_AI_MODEL"]


class TestDefaultAlignment:
    """Hardcoded defaults in docker-compose must match Settings defaults."""

    def test_temporal_address_default_matches_compose(self, worker_env):
        # docker-compose sets TEMPORAL_ADDRESS=temporal:7233, matching Settings default
        assert Settings().temporal_address == worker_env["TEMPORAL_ADDRESS"]

    def test_temporal_task_queue_default_matches_compose(self, worker_env, monkeypatch):
        # Strip the ${..:-main} default syntax if present
        raw = worker_env["TEMPORAL_TASK_QUEUE"]
        if raw.startswith("${"):
            # e.g. ${TEMPORAL_TASK_QUEUE:-main} → extract default "main"
            default = raw.split(":-")[-1].rstrip("}")
        else:
            default = raw
        assert Settings().temporal_task_queue == default

    def test_supabase_url_in_compose_points_to_internal_kong(self, worker_env):
        assert worker_env["SUPABASE_URL"] == "http://supabase-kong:8000"

    def test_settings_supabase_url_differs_from_compose_value(self):
        # The Settings default (host.docker.internal) is for local dev;
        # in production the compose value (supabase-kong:8000) overrides it.
        assert Settings().supabase_url != "http://supabase-kong:8000"

    def test_settings_supabase_url_override_simulates_compose(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "http://supabase-kong:8000")
        assert Settings().supabase_url == "http://supabase-kong:8000"
