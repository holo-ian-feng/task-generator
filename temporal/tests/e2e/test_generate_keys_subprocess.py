"""
E2E tests for azure/generate-keys.py.

Runs the script as a subprocess and validates its actual output — the only way
to test it end-to-end since it executes at module level.
Requires: pyjwt installed in the test environment.
"""
import re
import subprocess
import sys
import pytest
import jwt
import paths


def _run():
    return subprocess.run(
        [sys.executable, paths.GENERATE_KEYS_SCRIPT],
        capture_output=True,
        text=True,
    )


def _parse(stdout):
    """Extract KEY=value pairs from script output, ignoring header lines."""
    result = {}
    for line in stdout.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("=") and not line.startswith("#"):
            k, v = line.split("=", 1)
            if k.isupper() and " " not in k:
                result[k] = v
    return result


@pytest.fixture(scope="module")
def output():
    result = _run()
    assert result.returncode == 0, f"Script exited {result.returncode}:\n{result.stderr}"
    return _parse(result.stdout)


class TestScriptExecution:
    def test_exits_with_zero(self):
        assert _run().returncode == 0

    def test_produces_no_stderr_on_success(self):
        assert _run().stderr == ""


class TestOutputKeys:
    def test_jwt_secret_present(self, output):
        assert "JWT_SECRET" in output

    def test_anon_key_present(self, output):
        assert "ANON_KEY" in output

    def test_service_role_key_present(self, output):
        assert "SERVICE_ROLE_KEY" in output

    def test_jwt_secret_is_url_safe_base64(self, output):
        secret = output["JWT_SECRET"]
        assert re.match(r"^[A-Za-z0-9_\-]+$", secret), (
            f"JWT_SECRET contains non-URL-safe characters: {secret!r}"
        )

    def test_jwt_secret_minimum_length(self, output):
        # secrets.token_urlsafe(48) produces at least 64 chars
        assert len(output["JWT_SECRET"]) >= 48


class TestTokenClaims:
    def test_anon_key_has_anon_role(self, output):
        decoded = jwt.decode(
            output["ANON_KEY"], output["JWT_SECRET"],
            algorithms=["HS256"], options={"verify_exp": False},
        )
        assert decoded["role"] == "anon"

    def test_service_key_has_service_role(self, output):
        decoded = jwt.decode(
            output["SERVICE_ROLE_KEY"], output["JWT_SECRET"],
            algorithms=["HS256"], options={"verify_exp": False},
        )
        assert decoded["role"] == "service_role"

    def test_anon_key_issuer_is_supabase(self, output):
        decoded = jwt.decode(
            output["ANON_KEY"], output["JWT_SECRET"],
            algorithms=["HS256"], options={"verify_exp": False},
        )
        assert decoded["iss"] == "supabase"

    def test_service_key_issuer_is_supabase(self, output):
        decoded = jwt.decode(
            output["SERVICE_ROLE_KEY"], output["JWT_SECRET"],
            algorithms=["HS256"], options={"verify_exp": False},
        )
        assert decoded["iss"] == "supabase"

    def test_anon_key_expiry_is_ten_years(self, output):
        decoded = jwt.decode(
            output["ANON_KEY"], output["JWT_SECRET"],
            algorithms=["HS256"], options={"verify_exp": False},
        )
        ten_years = 10 * 365 * 24 * 3600
        assert decoded["exp"] - decoded["iat"] == ten_years

    def test_tokens_only_verify_with_their_own_secret(self, output):
        with pytest.raises(jwt.exceptions.InvalidSignatureError):
            jwt.decode(
                output["ANON_KEY"], "wrong-secret",
                algorithms=["HS256"], options={"verify_exp": False},
            )


class TestRandomness:
    def test_consecutive_runs_produce_different_jwt_secrets(self):
        out1 = _parse(_run().stdout)
        out2 = _parse(_run().stdout)
        assert out1["JWT_SECRET"] != out2["JWT_SECRET"], (
            "Two consecutive runs produced the same JWT_SECRET — secret is not random"
        )
