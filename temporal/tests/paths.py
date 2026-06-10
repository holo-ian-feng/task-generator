"""Shared path constants for all test modules."""
import os

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPORAL_DIR = os.path.dirname(_TESTS_DIR)
PROJECT_ROOT = os.path.dirname(_TEMPORAL_DIR)

KONG_CONFIG = os.path.join(PROJECT_ROOT, "supabase", "kong", "kong.yml")
DOCKER_COMPOSE_PROD = os.path.join(PROJECT_ROOT, "docker-compose.prod.yml")
GITHUB_WORKFLOW = os.path.join(PROJECT_ROOT, ".github", "workflows", "deploy.yml")
GENERATE_KEYS_SCRIPT = os.path.join(PROJECT_ROOT, "azure", "generate-keys.py")
