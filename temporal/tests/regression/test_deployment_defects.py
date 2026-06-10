"""
Regression tests for confirmed adversarial findings in the deployment pipeline.

Each test is xfail(strict=True): it MUST fail until the defect is fixed.
When a defect is fixed, pytest reports XPASS — remove the xfail mark at that point
to graduate the test into the permanent suite.

Defect references map to the adversarial finding numbers from the Step 4 report.
"""
import re
import pytest
import yaml
import paths


@pytest.fixture(scope="module")
def workflow():
    with open(paths.GITHUB_WORKFLOW) as f:
        data = yaml.safe_load(f)
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


@pytest.fixture(scope="module")
def deploy_job(workflow):
    return workflow["jobs"]["deploy"]


@pytest.fixture(scope="module")
def compose():
    with open(paths.DOCKER_COMPOSE_PROD) as f:
        return yaml.safe_load(f)


def _parse_env(env_block):
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


# ── Defect #1 ─────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="DEFECT #1: Migration step uses '| true' (pipe) not '|| true' (logical OR). "
           "The pipeline exit code is always 0 regardless of az failure, so migrations "
           "silently never run while CI stays green. Fix: replace '| true' with '|| true'.",
)
def test_migration_step_no_silent_pipe_suppression(deploy_job):
    migration_step = next(
        (s for s in deploy_job["steps"] if "migration" in s.get("name", "").lower()),
        None,
    )
    assert migration_step is not None, "Could not find migration step in deploy job"
    run = migration_step.get("run", "")
    # Detect bare '| true' (pipe to true) — must NOT be preceded by another '|'
    silent_pipe = re.search(r"(?<!\|)\| true", run)
    assert not silent_pipe, (
        "Migration step pipes az output into 'true', discarding all errors. "
        "The step always exits 0. Migrations are never applied."
    )


# ── Defect #2 ─────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="DEFECT #2: Migration job is created with --trigger-type Manual but never started. "
           "No 'az containerapp job start' call exists in the workflow. "
           "The job definition is registered but never fires — the database schema is never applied. "
           "Fix: add 'az containerapp job start --name db-migrate-... --resource-group ...' "
           "after the job creation step, followed by a poll for job completion.",
)
def test_migration_job_is_explicitly_started(deploy_job):
    all_run = "\n".join(s.get("run", "") for s in deploy_job["steps"])
    assert "containerapp job start" in all_run, (
        "No 'az containerapp job start' found in deploy job. "
        "The migration job is created (with --trigger-type Manual) but never triggered."
    )


# ── Defect #3 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("service", [
    "supabase-db",
    "supabase-auth",
    "supabase-rest",
    "temporal-worker",
])
@pytest.mark.xfail(
    strict=True,
    reason="DEFECT #3: 'az containerapp update' fallback omits --env-vars. On every re-deploy "
           "(when the container already exists) secrets are not re-applied. After rotating "
           "JWT_SECRET, SERVICE_ROLE_KEY, or AZURE_AI_KEY, the running service keeps stale "
           "credentials and authentication breaks silently. "
           "Fix: add --env-vars to every update fallback, mirroring the create block.",
)
def test_secret_bearing_update_fallback_includes_env_vars(deploy_job, service):
    # Find the deploy step for this service (matched by step name or --name in run script)
    step = next(
        (
            s for s in deploy_job["steps"]
            if service in s.get("name", "").lower().replace(" ", "-")
            or f"--name {service}" in s.get("run", "")
        ),
        None,
    )
    assert step is not None, f"Could not find deploy step for service '{service}'"

    run = step.get("run", "")
    # Locate the update fallback block (from 'az containerapp update' to end of run script)
    update_idx = run.find("az containerapp update")
    assert update_idx != -1, (
        f"No 'az containerapp update' found in step for '{service}' — "
        f"is the create-or-update pattern missing?"
    )
    update_block = run[update_idx:]
    assert "--env-vars" in update_block or "--set-env-vars" in update_block, (
        f"'az containerapp update --name {service}' does not pass --env-vars. "
        f"Secret rotation will not propagate to this service."
    )


# ── Defect #5 ─────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="DEFECT #5: PGRST_DB_SCHEMAS is 'public,storage,graphql_public' in docker-compose.prod.yml "
           "but only 'public' in deploy.yml. Storage API and GraphQL calls work locally but fail "
           "in the ACA production deployment. Fix: update deploy.yml to match the compose value.",
)
def test_pgrst_db_schemas_consistent_across_environments(compose):
    # Value from docker-compose.prod.yml
    compose_env = _parse_env(compose["services"]["supabase-rest"]["environment"])
    compose_schemas = compose_env.get("PGRST_DB_SCHEMAS", "")

    # Value from deploy.yml (raw text search in non-comment lines)
    lines = []
    with open(paths.GITHUB_WORKFLOW) as f:
        for line in f:
            if not line.strip().startswith("#"):
                lines.append(line)
    deploy_text = "".join(lines)
    match = re.search(r"PGRST_DB_SCHEMAS=([^\s\\\"']+)", deploy_text)
    deploy_schemas = match.group(1) if match else "<not found>"

    assert compose_schemas == deploy_schemas, (
        f"PGRST_DB_SCHEMAS mismatch between environments:\n"
        f"  docker-compose.prod.yml : {compose_schemas!r}\n"
        f"  deploy.yml              : {deploy_schemas!r}\n"
        f"Storage API and GraphQL calls will fail in production (ACA) but pass locally."
    )


# ── Defect #8 ─────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="DEFECT #8: db-migrate uses restart:on-failure with non-idempotent SQL migrations. "
           "If a migration partially completes then fails, the restart re-runs all SQL from the top, "
           "hitting 'relation already exists' errors on already-applied statements, failing again, "
           "and restarting indefinitely. Fix: change to restart:'no' for one-shot containers, "
           "and add IF NOT EXISTS guards to migration SQL.",
)
def test_db_migrate_does_not_use_restart_on_failure(compose):
    restart_policy = compose["services"]["db-migrate"].get("restart", "no")
    assert restart_policy != "on-failure", (
        f"db-migrate restart policy is '{restart_policy}'. "
        f"Non-idempotent migrations under restart:on-failure create an infinite restart loop."
    )
