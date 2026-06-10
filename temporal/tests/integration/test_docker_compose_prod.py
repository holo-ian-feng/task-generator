"""
Integration tests for docker-compose.prod.yml.

Validates service presence, healthcheck coverage, port assignments,
volume declarations, and dependency wiring without starting any containers.
"""
import pytest
import yaml
from collections import Counter
import paths

EXPECTED_SERVICES = {
    "supabase-db", "db-migrate", "supabase-auth", "supabase-rest",
    "supabase-kong", "temporal-db", "temporal", "temporal-ui",
    "temporal-worker", "frontend",
}


@pytest.fixture(scope="module")
def compose():
    with open(paths.DOCKER_COMPOSE_PROD) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def services(compose):
    return compose["services"]


def _parse_env(env_block):
    """Parse a docker-compose environment block into a key→value dict.

    Handles both list format (- KEY=value) and dict format (KEY: value).
    """
    if isinstance(env_block, dict):
        return {str(k): (str(v) if v is not None else None) for k, v in env_block.items()}
    result = {}
    for item in env_block or []:
        if isinstance(item, dict):
            result.update(item)
        elif "=" in str(item):
            k, v = str(item).split("=", 1)
            result[k.strip()] = v.strip()
        else:
            result[str(item).strip()] = None
    return result


def _host_ports(services):
    """Extract all published host ports from all services, handling all compose port formats."""
    ports = []
    for svc in services.values():
        for port in svc.get("ports", []):
            if isinstance(port, dict):
                published = port.get("published")
                if published is not None:
                    ports.append(str(published))
            elif isinstance(port, int):
                # Container-only port (no host binding) — skip
                pass
            else:
                # "HOST:CONTAINER" or "IP:HOST:CONTAINER" string
                parts = str(port).split(":")
                if len(parts) >= 2:
                    ports.append(parts[-2])
    return ports


class TestServicePresence:
    def test_all_expected_services_defined(self, services):
        assert set(services.keys()) == EXPECTED_SERVICES

    def test_supabase_stack_complete(self, services):
        supabase = {"supabase-db", "supabase-auth", "supabase-rest", "supabase-kong"}
        assert supabase.issubset(services.keys())

    def test_temporal_stack_complete(self, services):
        temporal = {"temporal-db", "temporal", "temporal-ui", "temporal-worker"}
        assert temporal.issubset(services.keys())


class TestHealthChecks:
    @pytest.mark.parametrize("svc", ["supabase-db", "supabase-auth", "temporal-db"])
    def test_dependency_target_has_healthcheck(self, services, svc):
        assert "healthcheck" in services[svc], (
            f"{svc} is a service_healthy target but has no healthcheck"
        )

    def test_supabase_kong_waits_for_healthy_auth(self, services):
        deps = services["supabase-kong"]["depends_on"]
        assert deps["supabase-auth"]["condition"] == "service_healthy"

    def test_supabase_auth_waits_for_healthy_db(self, services):
        deps = services["supabase-auth"]["depends_on"]
        assert deps["supabase-db"]["condition"] == "service_healthy"

    def test_supabase_rest_waits_for_healthy_db(self, services):
        deps = services["supabase-rest"]["depends_on"]
        assert deps["supabase-db"]["condition"] == "service_healthy"

    def test_db_migrate_waits_for_healthy_db(self, services):
        deps = services["db-migrate"]["depends_on"]
        assert deps["supabase-db"]["condition"] == "service_healthy"

    def test_temporal_worker_depends_on_temporal(self, services):
        deps = services["temporal-worker"].get("depends_on", {})
        assert "temporal" in deps, "temporal-worker has no depends_on entry for temporal"

    def test_temporal_ui_depends_on_temporal(self, services):
        deps = services["temporal-ui"].get("depends_on", {})
        assert "temporal" in deps, "temporal-ui has no depends_on entry for temporal"

    @pytest.mark.xfail(
        strict=True,
        reason="temporal healthcheck is ['CMD', 'true'] — always passes immediately, "
               "making it a non-functional health gate. Replace with a real TCP/gRPC check.",
    )
    def test_temporal_healthcheck_is_not_trivially_true(self, services):
        hc = services["temporal"].get("healthcheck", {})
        test_cmd = hc.get("test", [])
        assert test_cmd != ["CMD", "true"], (
            "temporal service healthcheck is 'CMD true' — it always exits 0 immediately."
        )


class TestPorts:
    def test_no_duplicate_host_ports(self, services):
        ports = _host_ports(services)
        duplicates = {p: c for p, c in Counter(ports).items() if c > 1}
        assert not duplicates, f"Duplicate host ports detected: {duplicates}"

    def test_kong_exposes_8000(self, services):
        ports = services["supabase-kong"]["ports"]
        assert any("8000" in str(p) for p in ports)

    def test_frontend_exposes_3000(self, services):
        ports = services["frontend"]["ports"]
        assert any("3000" in str(p) for p in ports)

    def test_temporal_ui_exposes_8080(self, services):
        ports = services["temporal-ui"]["ports"]
        assert any("8080" in str(p) for p in ports)

    def test_databases_have_no_host_ports(self, services):
        for db in ["supabase-db", "temporal-db"]:
            assert not services[db].get("ports"), f"{db} should not expose host ports"


class TestVolumes:
    def test_named_volumes_declared_at_top_level(self, compose):
        assert "volumes" in compose
        assert "supabase-db-data" in compose["volumes"]
        assert "temporal-db-data" in compose["volumes"]

    def test_supabase_db_mounts_named_volume(self, services):
        vols = services["supabase-db"].get("volumes", [])
        assert any("supabase-db-data" in str(v) for v in vols)

    def test_temporal_db_mounts_named_volume(self, services):
        vols = services["temporal-db"].get("volumes", [])
        assert any("temporal-db-data" in str(v) for v in vols)


class TestEnvironmentVariables:
    def test_supabase_db_requires_postgres_password(self, services):
        env = _parse_env(services["supabase-db"]["environment"])
        assert "POSTGRES_PASSWORD" in env
        assert "${POSTGRES_PASSWORD}" in str(env["POSTGRES_PASSWORD"])

    def test_supabase_db_receives_jwt_secret(self, services):
        env = _parse_env(services["supabase-db"]["environment"])
        assert "JWT_SECRET" in env

    def test_supabase_auth_receives_jwt_secret(self, services):
        env = _parse_env(services["supabase-auth"]["environment"])
        assert "GOTRUE_JWT_SECRET" in env

    def test_postgrest_receives_jwt_secret(self, services):
        env = _parse_env(services["supabase-rest"]["environment"])
        assert "PGRST_JWT_SECRET" in env

    def test_worker_temporal_address_is_internal_hostname(self, services):
        env = _parse_env(services["temporal-worker"]["environment"])
        assert env.get("TEMPORAL_ADDRESS") == "temporal:7233"

    def test_worker_supabase_url_points_to_kong(self, services):
        env = _parse_env(services["temporal-worker"]["environment"])
        assert env.get("SUPABASE_URL") == "http://supabase-kong:8000"

    def test_worker_receives_azure_ai_config(self, services):
        env = _parse_env(services["temporal-worker"]["environment"])
        assert "AZURE_AI_ENDPOINT" in env
        assert "AZURE_AI_KEY" in env
        assert "AZURE_AI_MODEL" in env
