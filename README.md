# Boilerplate Stack

Phase 1 scaffolding for the JSON-driven Supabase + Temporal starter.

## Prerequisites
- Docker Desktop with Compose v2
- `make` (comes with macOS/Linux; install via Xcode CLT on macOS)
- Node 18+ (optional for running the frontend outside Docker)
- Supabase CLI (optional) if you want the full Supabase stack locally

## Quick Start
1) Copy environment defaults  
   `cp .env.example .env`
2) Start everything  
   `make up`  
   (add `USE_DEV=1` for live-reload mounts)
3) Open services  
   - Frontend placeholder: http://localhost:3000  
   - Temporal UI: http://localhost:8080  
   - Temporal gRPC: localhost:7234  
   - Supabase Postgres stub: localhost:55432

Common commands:
- `make down` — stop containers
- `make reset` — tear down volumes and recreate containers
- `make logs` — stream all service logs
- `make logs-temporal` / `make logs-frontend` — targeted logs

## What’s Included (Phase 1)
- Docker Compose stack with Temporal server, UI, worker, frontend dev server, and stub Supabase Postgres
- Development overrides in `docker-compose.dev.yml` for live-reloading frontend and worker code
- Makefile wrappers for the usual lifecycle commands
- `.env.example` capturing required variables for frontend, Temporal, and Supabase placeholders

## Notes
- Supabase services are intentionally stubbed for Phase 1; use `supabase start --config supabase/config.toml` when you need the full Supabase stack.
- Frontend and Temporal code are minimal placeholders to keep containers healthy; replace with real implementations in Phases 2–3.
