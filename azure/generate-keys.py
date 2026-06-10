"""
Generate Supabase JWT keys from a JWT_SECRET.
Run once, then store the output as GitHub secrets / Azure env vars.

Usage:
    pip install pyjwt
    python azure/generate-keys.py
"""
import secrets
import time

try:
    import jwt
except ImportError:
    print("Install pyjwt first:  pip install pyjwt")
    raise

JWT_SECRET = secrets.token_urlsafe(48)   # 64-char random secret
NOW = int(time.time())

anon_payload = {
    "role": "anon",
    "iss": "supabase",
    "iat": NOW,
    "exp": NOW + (10 * 365 * 24 * 3600),  # 10 years
}
service_payload = {
    "role": "service_role",
    "iss": "supabase",
    "iat": NOW,
    "exp": NOW + (10 * 365 * 24 * 3600),
}

anon_key     = jwt.encode(anon_payload,    JWT_SECRET, algorithm="HS256")
service_key  = jwt.encode(service_payload, JWT_SECRET, algorithm="HS256")

print("=== Add these to GitHub Secrets (Settings -> Secrets -> Actions) ===\n")
print(f"JWT_SECRET={JWT_SECRET}")
print(f"ANON_KEY={anon_key}")
print(f"SERVICE_ROLE_KEY={service_key}")
print("\n=== Also set in your .env.prod file ===")
