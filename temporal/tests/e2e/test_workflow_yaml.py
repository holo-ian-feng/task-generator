"""
E2E tests for .github/workflows/deploy.yml.

Validates workflow structure, job dependencies, required secrets,
and build outputs without running the workflow.
"""
import re
import pytest
import yaml
import paths


@pytest.fixture(scope="module")
def workflow():
    with open(paths.GITHUB_WORKFLOW) as f:
        data = yaml.safe_load(f)
    # PyYAML 1.1 parses bare `on:` as boolean True; normalise to string key.
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


@pytest.fixture(scope="module")
def workflow_text():
    """Raw file text for pattern searches, comment lines stripped."""
    lines = []
    with open(paths.GITHUB_WORKFLOW) as f:
        for line in f:
            if not line.strip().startswith("#"):
                lines.append(line)
    return "".join(lines)


@pytest.fixture(scope="module")
def build_job(workflow):
    return workflow["jobs"]["build"]


@pytest.fixture(scope="module")
def deploy_job(workflow):
    return workflow["jobs"]["deploy"]


class TestWorkflowTriggers:
    def test_triggers_on_push_to_main(self, workflow):
        assert "main" in workflow["on"]["push"]["branches"]

    def test_manual_dispatch_enabled(self, workflow):
        assert "workflow_dispatch" in workflow["on"]


class TestJobStructure:
    def test_build_job_exists(self, workflow):
        assert "build" in workflow["jobs"]

    def test_deploy_job_exists(self, workflow):
        assert "deploy" in workflow["jobs"]

    def test_deploy_needs_build(self, deploy_job):
        needs = deploy_job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "build" in needs, "deploy job must declare needs: [build]"

    def test_build_runs_on_ubuntu(self, build_job):
        assert "ubuntu" in build_job["runs-on"]

    def test_deploy_runs_on_ubuntu(self, deploy_job):
        assert "ubuntu" in deploy_job["runs-on"]


class TestBuildOutputs:
    def test_image_tag_output_defined(self, build_job):
        assert "image_tag" in build_job.get("outputs", {})

    def test_kong_fqdn_output_defined(self, build_job):
        assert "kong_fqdn" in build_job.get("outputs", {})

    def test_image_tag_expression_is_well_formed(self, build_job):
        ref = build_job["outputs"]["image_tag"].strip()
        assert re.match(r'^\$\{\{[^}]*steps\.tag\.outputs\.tag[^}]*\}\}$', ref), (
            f"image_tag output expression is malformed or missing closing braces: {ref!r}"
        )

    def test_deploy_consumes_image_tag_output(self, workflow_text):
        assert "needs.build.outputs.image_tag" in workflow_text


class TestRequiredSecrets:
    @pytest.mark.parametrize("secret", [
        "AZURE_CREDENTIALS",
        "JWT_SECRET",
        "POSTGRES_PASSWORD",
        "ACR_PASSWORD",
        "ANON_KEY",
        "SERVICE_ROLE_KEY",
        "TEMPORAL_DB_PASSWORD",
        "SITE_URL",
        "RESOURCE_GROUP",
        "ENV_NAME",
        "ACR_NAME",
    ])
    def test_secret_referenced_in_non_comment_context(self, workflow_text, secret):
        # Search for the secret name appearing after `secrets.` outside of comment lines
        assert re.search(rf'secrets\.{re.escape(secret)}\b', workflow_text), (
            f"secrets.{secret} not found in workflow (comment lines excluded)"
        )


class TestBuildSteps:
    def test_build_checks_out_code(self, build_job):
        steps = build_job.get("steps", [])
        assert any("checkout" in str(s.get("uses", "")) for s in steps)

    def test_deploy_checks_out_code(self, deploy_job):
        steps = deploy_job.get("steps", [])
        assert any("checkout" in str(s.get("uses", "")) for s in steps)

    def test_build_pushes_temporal_worker_image(self, build_job):
        steps = build_job.get("steps", [])
        assert any(
            "docker push" in str(s.get("run", "")) and "temporal-worker" in str(s.get("run", ""))
            for s in steps
        ), "No step found that runs 'docker push' with a temporal-worker image"

    def test_build_pushes_kong_image(self, build_job):
        steps = build_job.get("steps", [])
        assert any(
            "docker push" in str(s.get("run", "")) and "kong" in str(s.get("run", "")).lower()
            for s in steps
        ), "No step found that runs 'docker push' with a kong image"

    def test_build_pushes_frontend_image(self, build_job):
        steps = build_job.get("steps", [])
        assert any(
            "docker push" in str(s.get("run", "")) and "frontend" in str(s.get("run", ""))
            for s in steps
        ), "No step found that runs 'docker push' with a frontend image"

    def test_deploy_prints_service_urls(self, deploy_job):
        step_names = [s.get("name", "").lower() for s in deploy_job.get("steps", [])]
        assert any("url" in name for name in step_names)


class TestDeploySteps:
    @pytest.mark.parametrize("service", [
        "supabase db",
        "supabase auth",
        "kong",
        "temporal worker",
        "frontend",
    ])
    def test_deploy_has_distinct_step_for_service(self, deploy_job, service):
        step_names = [s.get("name", "") for s in deploy_job.get("steps", [])]
        keyword = service.replace(" ", r"[-_ ]?")
        matching = [n for n in step_names if re.search(keyword, n, re.IGNORECASE)]
        assert len(matching) >= 1, (
            f"No individual deploy step found for '{service}'. "
            f"Step names: {step_names}"
        )
