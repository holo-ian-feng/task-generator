"""
Unit-level assertions against actual generate-keys.py output.

Runs the script once per test session and verifies that the emitted JWT tokens
carry the correct claims, algorithm, and expiry — connected to the real code,
not a local re-implementation.
"""
import subprocess
import sys
import time
import pytest
import jwt
import paths

TEN_YEARS = 10 * 365 * 24 * 3600


def _run_script():
    return subprocess.run(
        [sys.executable, paths.GENERATE_KEYS_SCRIPT],
        capture_output=True,
        text=True,
    )


def _parse(stdout):
    result = {}
    for line in stdout.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("=") and not line.startswith("#"):
            k, v = line.split("=", 1)
            if k.isupper() and " " not in k:
                result[k] = v
    return result


@pytest.fixture(scope="module")
def keys():
    result = _run_script()
    assert result.returncode == 0, f"Script failed:\n{result.stderr}"
    return _parse(result.stdout)


def _decode(token, secret):
    return jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False})


class TestAnonPayload:
    def test_role_is_anon(self, keys):
        assert _decode(keys["ANON_KEY"], keys["JWT_SECRET"])["role"] == "anon"

    def test_issuer_is_supabase(self, keys):
        assert _decode(keys["ANON_KEY"], keys["JWT_SECRET"])["iss"] == "supabase"

    def test_expiry_is_ten_years_from_iat(self, keys):
        decoded = _decode(keys["ANON_KEY"], keys["JWT_SECRET"])
        assert decoded["exp"] - decoded["iat"] == TEN_YEARS

    def test_iat_is_close_to_current_time(self, keys):
        # Guards against a script that uses a hardcoded or cached timestamp
        decoded = _decode(keys["ANON_KEY"], keys["JWT_SECRET"])
        assert abs(decoded["iat"] - int(time.time())) < 10


class TestServicePayload:
    def test_role_is_service_role(self, keys):
        assert _decode(keys["SERVICE_ROLE_KEY"], keys["JWT_SECRET"])["role"] == "service_role"

    def test_issuer_is_supabase(self, keys):
        assert _decode(keys["SERVICE_ROLE_KEY"], keys["JWT_SECRET"])["iss"] == "supabase"

    def test_expiry_is_ten_years_from_iat(self, keys):
        decoded = _decode(keys["SERVICE_ROLE_KEY"], keys["JWT_SECRET"])
        assert decoded["exp"] - decoded["iat"] == TEN_YEARS


class TestTokenSecurity:
    def test_algorithm_is_hs256(self, keys):
        header = jwt.get_unverified_header(keys["ANON_KEY"])
        assert header["alg"] == "HS256"

    def test_wrong_secret_raises_invalid_signature(self, keys):
        with pytest.raises(jwt.exceptions.InvalidSignatureError):
            jwt.decode(
                keys["ANON_KEY"], "wrong-secret",
                algorithms=["HS256"], options={"verify_exp": False},
            )

    def test_anon_and_service_tokens_differ(self, keys):
        # Different payloads must produce different tokens
        assert keys["ANON_KEY"] != keys["SERVICE_ROLE_KEY"]
