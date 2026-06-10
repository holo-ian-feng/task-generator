# Azure Deployment Guide

## Architecture

All services run as Azure Container Apps in a single environment.

```
Internet
  │
  ├── frontend           (Container App, external ingress, port 3000)
  ├── supabase-kong      (Container App, external ingress, port 8000)  ← Supabase API
  └── temporal-ui        (Container App, external ingress, port 8080)

Internal (not publicly accessible)
  ├── supabase-db        (PostgreSQL with Supabase extensions)
  ├── supabase-auth      (GoTrue — handles /auth/v1/*)
  ├── supabase-rest      (PostgREST — handles /rest/v1/*)
  ├── temporal-db        (PostgreSQL for Temporal)
  ├── temporal           (Temporal server)
  └── temporal-worker    (Python worker — polls + runs workflows)
```

---

## Step 1 — Generate Supabase JWT Keys

```bash
pip install pyjwt
python azure/generate-keys.py
```

Copy the output — you'll add it as GitHub secrets in Step 3.

---

## Step 2 — Provision Azure Infrastructure (one-time)

```bash
az login
az account set --subscription <your-subscription-id>
chmod +x azure/setup.sh
./azure/setup.sh
```

This creates:
- Resource group
- Azure Container Registry (ACR)
- Container Apps Environment
- Azure Storage Account + file shares (persistent DB volumes)

---

## Step 3 — Add GitHub Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret.

| Secret | Value |
|--------|-------|
| `AZURE_CREDENTIALS` | Output of the `az ad sp create-for-rbac` command shown at the end of `setup.sh` |
| `RESOURCE_GROUP` | `rg-task-generator` |
| `ENV_NAME` | `task-generator-env` |
| `ACR_NAME` | `taskgeneratoracr` |
| `ACR_PASSWORD` | Printed by `setup.sh` |
| `JWT_SECRET` | From `generate-keys.py` |
| `ANON_KEY` | From `generate-keys.py` |
| `SERVICE_ROLE_KEY` | From `generate-keys.py` |
| `POSTGRES_PASSWORD` | Any strong password |
| `TEMPORAL_DB_PASSWORD` | Any strong password |
| `SITE_URL` | Your frontend URL (can update after first deploy) |
| `AZURE_AI_ENDPOINT` | `https://ianfeng-7907-resource.services.ai.azure.com/openai/v1` |
| `AZURE_AI_KEY` | Your Azure AI key |
| `AZURE_AI_MODEL` | `gpt-4o` (or your deployment name) |

---

## Step 4 — Deploy

Push to `main` (or trigger manually via GitHub Actions → Run workflow).

The workflow:
1. Builds `temporal-worker`, `supabase-kong`, and `frontend` Docker images
2. Pushes them to ACR
3. Creates/updates each Container App in order
4. Prints the public URLs at the end

---

## Step 5 — First-time Frontend Fix

The **frontend** is built with `VITE_SUPABASE_URL` baked in at build time.
On the very first deploy, Kong's FQDN isn't known yet, so the frontend will
have a placeholder URL.

After the first deploy:
1. Copy the `supabase-kong` FQDN from the workflow output
2. Add it as GitHub secret `SITE_URL` (format: `https://<kong-fqdn>`)
3. Re-run the workflow — the frontend will be rebuilt with the correct URL

---

## Updating After Code Changes

Just push to `main`. GitHub Actions rebuilds and redeploys only the custom
images (`temporal-worker`, `frontend`, `supabase-kong`). The Supabase and
Temporal infrastructure images are not rebuilt on each push.

---

## Useful Azure CLI Commands

```bash
# View all Container Apps
az containerapp list --resource-group rg-task-generator -o table

# Stream logs from the worker
az containerapp logs show --name temporal-worker --resource-group rg-task-generator --follow

# Get a service's public URL
az containerapp show --name frontend --resource-group rg-task-generator \
  --query properties.configuration.ingress.fqdn -o tsv

# Restart a service
az containerapp revision restart --name temporal-worker --resource-group rg-task-generator
```
