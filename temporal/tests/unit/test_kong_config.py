"""Unit tests for supabase/kong/kong.yml — validates routes, upstreams, and CORS."""
import pytest
import yaml
import paths


@pytest.fixture(scope="module")
def kong():
    with open(paths.KONG_CONFIG) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def services(kong):
    return {s["name"]: s for s in kong["services"]}


@pytest.fixture(scope="module")
def auth_cors(services):
    plugins = {p["name"]: p for p in services["auth-v1"]["plugins"]}
    return plugins["cors"]["config"]


@pytest.fixture(scope="module")
def rest_cors(services):
    plugins = {p["name"]: p for p in services["rest-v1"]["plugins"]}
    return plugins["cors"]["config"]


class TestServiceDefinitions:
    def test_auth_service_exists(self, services):
        assert "auth-v1" in services

    def test_rest_service_exists(self, services):
        assert "rest-v1" in services

    def test_auth_upstream_points_to_gotrue(self, services):
        assert services["auth-v1"]["url"] == "http://supabase-auth:9999/"

    def test_rest_upstream_points_to_postgrest(self, services):
        assert services["rest-v1"]["url"] == "http://supabase-rest:3000/"


class TestRoutes:
    def test_auth_route_path(self, services):
        assert "/auth/v1/" in services["auth-v1"]["routes"][0]["paths"]

    def test_rest_route_path(self, services):
        assert "/rest/v1/" in services["rest-v1"]["routes"][0]["paths"]

    def test_auth_route_strips_path(self, services):
        # strip_path=true means /auth/v1/token becomes /token on GoTrue
        assert services["auth-v1"]["routes"][0]["strip_path"] is True

    def test_rest_route_strips_path(self, services):
        assert services["rest-v1"]["routes"][0]["strip_path"] is True


class TestCorsHeaders:
    def test_auth_has_authorization_header(self, auth_cors):
        assert "Authorization" in auth_cors["headers"]

    def test_auth_has_apikey_header(self, auth_cors):
        assert "Apikey" in auth_cors["headers"]

    def test_auth_has_accept_header(self, auth_cors):
        assert "Accept" in auth_cors["headers"]

    def test_auth_has_content_type_header(self, auth_cors):
        assert "Content-Type" in auth_cors["headers"]

    def test_auth_has_x_client_info_header(self, auth_cors):
        assert "X-Client-Info" in auth_cors["headers"]

    def test_rest_has_prefer_header(self, rest_cors):
        # Prefer is required for PostgREST features like return=representation
        assert "Prefer" in rest_cors["headers"]

    def test_rest_has_authorization_header(self, rest_cors):
        assert "Authorization" in rest_cors["headers"]

    def test_rest_has_content_type_header(self, rest_cors):
        assert "Content-Type" in rest_cors["headers"]

    def test_rest_has_x_client_info_header(self, rest_cors):
        assert "X-Client-Info" in rest_cors["headers"]

    def test_rest_exposes_content_range(self, rest_cors):
        # Content-Range lets clients implement pagination
        assert "Content-Range" in rest_cors["exposed_headers"]

    def test_auth_exposes_x_auth_token(self, auth_cors):
        assert "X-Auth-Token" in auth_cors["exposed_headers"]


class TestCorsMethods:
    @pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"])
    def test_auth_allows_method(self, auth_cors, method):
        assert method in auth_cors["methods"]

    @pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"])
    def test_rest_allows_method(self, rest_cors, method):
        assert method in rest_cors["methods"]


class TestCorsPolicy:
    def test_auth_allows_credentials(self, auth_cors):
        assert auth_cors["credentials"] is True

    def test_rest_allows_credentials(self, rest_cors):
        assert rest_cors["credentials"] is True

    def test_auth_max_age_is_3600(self, auth_cors):
        assert auth_cors["max_age"] == 3600

    def test_rest_max_age_is_3600(self, rest_cors):
        assert rest_cors["max_age"] == 3600

    @pytest.mark.xfail(
        strict=True,
        reason="credentials:true + origins:['*'] is a security misconfiguration — "
               "browsers reject credentialed cross-origin requests to wildcard origins. "
               "Fix: replace '*' with the specific frontend origin.",
    )
    def test_wildcard_origin_not_combined_with_credentials(self, auth_cors, rest_cors):
        for cors in (auth_cors, rest_cors):
            assert cors["origins"] != ["*"], (
                "CORS origins is '*' while credentials is true — "
                "this combination is rejected by browsers per the CORS spec."
            )
