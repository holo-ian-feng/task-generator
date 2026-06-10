#!/usr/bin/env bash
# One-time Azure infrastructure setup for task-generator.
# Run this ONCE before the first GitHub Actions deploy.
#
# Prerequisites:
#   az login
#   az account set --subscription <your-subscription-id>
#   pip install pyjwt && python azure/generate-keys.py  (copy output to GitHub secrets)
#
# Usage:
#   chmod +x azure/setup.sh
#   ./azure/setup.sh

set -euo pipefail

# ── Edit these ────────────────────────────────────────────────────────────────
RESOURCE_GROUP="rg-task-generator"
LOCATION="australiaeast"          # az account list-locations -o table
ACR_NAME="taskgeneratoracr"       # globally unique, alphanumeric only
ENV_NAME="task-generator-env"
STORAGE_ACCOUNT="taskgenstorage"  # globally unique, lowercase only
# ─────────────────────────────────────────────────────────────────────────────

echo "→ Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o none

echo "→ Creating Azure Container Registry..."
az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true \
  -o none

ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)
echo "   ACR admin password (save this as GitHub secret ACR_PASSWORD): $ACR_PASSWORD"

echo "→ Creating Log Analytics workspace..."
az monitor log-analytics workspace create \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "${ENV_NAME}-logs" \
  -o none

LOG_WS_ID=$(az monitor log-analytics workspace show \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "${ENV_NAME}-logs" \
  --query customerId -o tsv)

LOG_WS_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "${ENV_NAME}-logs" \
  --query primarySharedKey -o tsv)

echo "→ Creating Container Apps Environment..."
az containerapp env create \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --logs-workspace-id "$LOG_WS_ID" \
  --logs-workspace-key "$LOG_WS_KEY" \
  -o none

echo "→ Creating Azure Storage Account for persistent volumes..."
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  -o none

STORAGE_KEY=$(az storage account keys list \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$STORAGE_ACCOUNT" \
  --query "[0].value" -o tsv)

echo "→ Creating file shares for database volumes..."
az storage share create --name supabase-db-data --account-name "$STORAGE_ACCOUNT" --account-key "$STORAGE_KEY" -o none
az storage share create --name temporal-db-data --account-name "$STORAGE_ACCOUNT" --account-key "$STORAGE_KEY" -o none

echo "→ Linking storage to Container Apps Environment..."
az containerapp env storage set \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --storage-name supabase-db \
  --azure-file-account-name "$STORAGE_ACCOUNT" \
  --azure-file-account-key "$STORAGE_KEY" \
  --azure-file-share-name supabase-db-data \
  --access-mode ReadWrite \
  -o none

az containerapp env storage set \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --storage-name temporal-db \
  --azure-file-account-name "$STORAGE_ACCOUNT" \
  --azure-file-account-key "$STORAGE_KEY" \
  --azure-file-share-name temporal-db-data \
  --access-mode ReadWrite \
  -o none

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Infrastructure ready. Now add these GitHub secrets:     ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  AZURE_CREDENTIALS  — output of:                        ║"
echo "║    az ad sp create-for-rbac --name task-generator-sp     ║"
echo "║      --role contributor                                  ║"
echo "║      --scopes /subscriptions/<sub-id>/resourceGroups/$RESOURCE_GROUP ║"
echo "║      --sdk-auth                                          ║"
echo "║  ACR_NAME           = $ACR_NAME"
echo "║  ACR_PASSWORD       = (printed above)"
echo "║  RESOURCE_GROUP     = $RESOURCE_GROUP"
echo "║  ENV_NAME           = $ENV_NAME"
echo "║  JWT_SECRET         )  from azure/generate-keys.py"
echo "║  ANON_KEY           )"
echo "║  SERVICE_ROLE_KEY   )"
echo "║  POSTGRES_PASSWORD  — any strong password"
echo "║  TEMPORAL_DB_PASSWORD — any strong password"
echo "║  AZURE_AI_ENDPOINT  — your Azure AI endpoint"
echo "║  AZURE_AI_KEY       — your Azure AI key"
echo "║  AZURE_AI_MODEL     — deployment name"
echo "╚══════════════════════════════════════════════════════════╝"
