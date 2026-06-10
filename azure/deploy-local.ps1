# =============================================================================
# deploy-local.ps1 - Deploy task-generator to Azure Container Apps
#
# Run from the project root:
#   cd "path\to\project-template-main"
#   .\azure\deploy-local.ps1
#
# Prerequisites:
#   - az login  (already done)
#   - Docker Desktop running
# =============================================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Configuration -------------------------------------------------------------
$RESOURCE_GROUP = "rg-task-generator"
$LOCATION       = "australiaeast"
$ACR_NAME       = "taskgeneratoracr"      # globally unique, lowercase alphanumeric
$ENV_NAME       = "task-generator-env"
$IMAGE_TAG      = (git rev-parse --short HEAD 2>$null)
if (-not $IMAGE_TAG) { $IMAGE_TAG = "latest" }
# ------------------------------------------------------------------------------

# -- Read Azure AI credentials from .env ---------------------------------------
Write-Host "`n-> Reading Azure AI config from .env..." -ForegroundColor Cyan
$envFile = Join-Path (Join-Path $PSScriptRoot "..") ".env"
$AZURE_AI_ENDPOINT = ""
$AZURE_AI_KEY      = ""
$AZURE_AI_MODEL    = "gpt-4o"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^AZURE_AI_ENDPOINT=(.+)$') { $AZURE_AI_ENDPOINT = $Matches[1] }
        if ($_ -match '^AZURE_AI_KEY=(.+)$')      { $AZURE_AI_KEY      = $Matches[1] }
        if ($_ -match '^AZURE_AI_MODEL=(.+)$')    { $AZURE_AI_MODEL    = $Matches[1] }
    }
}
if (-not $AZURE_AI_KEY) {
    Write-Error "AZURE_AI_KEY not found in .env -- please set it before running this script."
    exit 1
}
Write-Host "   AI endpoint: $AZURE_AI_ENDPOINT" -ForegroundColor Gray

# -- JWT key generation (no external dependencies) ----------------------------
function New-JwtHS256 {
    param([string]$Secret, [hashtable]$Payload)
    $header  = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('{"alg":"HS256","typ":"JWT"}'))
    $header  = $header -replace '=+$','' -replace '\+','-' -replace '/','_'
    $body    = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($Payload | ConvertTo-Json -Compress)))
    $body    = $body -replace '=+$','' -replace '\+','-' -replace '/','_'
    $input_  = "$header.$body"
    $hmac    = New-Object System.Security.Cryptography.HMACSHA256
    $hmac.Key = [Text.Encoding]::UTF8.GetBytes($Secret)
    $sig     = [Convert]::ToBase64String($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($input_)))
    $sig     = $sig -replace '=+$','' -replace '\+','-' -replace '/','_'
    return "$input_.$sig"
}

function New-RandomPassword {
    $bytes = [byte[]]::new(32)
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    return ([Convert]::ToBase64String($bytes) -replace '[^a-zA-Z0-9]','').Substring(0, 32)
}

$azureEnvFile = Join-Path (Join-Path $PSScriptRoot "..") ".env.azure"
$JWT_SECRET = ""; $ANON_KEY = ""; $SERVICE_ROLE_KEY = ""; $POSTGRES_PASSWORD = ""

if (Test-Path $azureEnvFile) {
    Write-Host "`n-> Loading existing keys from .env.azure..." -ForegroundColor Cyan
    Get-Content $azureEnvFile | ForEach-Object {
        if ($_ -match '^JWT_SECRET=(.+)$')       { $JWT_SECRET       = $Matches[1] }
        if ($_ -match '^ANON_KEY=(.+)$')          { $ANON_KEY         = $Matches[1] }
        if ($_ -match '^SERVICE_ROLE_KEY=(.+)$')  { $SERVICE_ROLE_KEY = $Matches[1] }
        if ($_ -match '^POSTGRES_PASSWORD=(.+)$') { $POSTGRES_PASSWORD = $Matches[1] }
    }
    Write-Host "   Keys loaded (reusing existing deployment secrets)." -ForegroundColor Gray
} else {
    Write-Host "`n-> Generating new Supabase JWT keys..." -ForegroundColor Cyan
    $JWT_SECRET       = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([System.Guid]::NewGuid().ToString() + [System.Guid]::NewGuid().ToString()))
    $NOW              = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $EXP              = $NOW + (10 * 365 * 24 * 3600)
    $ANON_KEY         = New-JwtHS256 -Secret $JWT_SECRET -Payload @{ role="anon";         iss="supabase"; iat=$NOW; exp=$EXP }
    $SERVICE_ROLE_KEY = New-JwtHS256 -Secret $JWT_SECRET -Payload @{ role="service_role"; iss="supabase"; iat=$NOW; exp=$EXP }
    $POSTGRES_PASSWORD = New-RandomPassword
    # Save so future re-runs reuse the same secrets
    @"
JWT_SECRET=$JWT_SECRET
ANON_KEY=$ANON_KEY
SERVICE_ROLE_KEY=$SERVICE_ROLE_KEY
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
"@ | Set-Content $azureEnvFile
    Write-Host "   Keys generated and saved to .env.azure for future re-runs." -ForegroundColor Gray
}

$TEMPORAL_DB_PASSWORD = New-RandomPassword

# =============================================================================
# STEP 1 - Azure infrastructure
# =============================================================================
Write-Host "`n--- STEP 1: Infrastructure ---" -ForegroundColor Yellow

Write-Host "-> Registering required Azure resource providers (one-time, may take ~30s)..." -ForegroundColor Cyan
az provider register --namespace Microsoft.ContainerRegistry --wait --output none
az provider register --namespace Microsoft.App              --wait --output none
az provider register --namespace Microsoft.OperationalInsights --wait --output none
Write-Host "   Providers registered." -ForegroundColor Gray

Write-Host "-> Creating Azure Container Registry..." -ForegroundColor Cyan
az acr create --resource-group $RESOURCE_GROUP --name $ACR_NAME --sku Basic --admin-enabled true --output none
$ACR_PASSWORD = az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv

Write-Host "-> Creating Log Analytics workspace..." -ForegroundColor Cyan
az monitor log-analytics workspace create --resource-group $RESOURCE_GROUP --workspace-name "$ENV_NAME-logs" --output none 2>$null
$LOG_WS_ID  = az monitor log-analytics workspace show --resource-group $RESOURCE_GROUP --workspace-name "$ENV_NAME-logs" --query customerId -o tsv
$LOG_WS_KEY = az monitor log-analytics workspace get-shared-keys --resource-group $RESOURCE_GROUP --workspace-name "$ENV_NAME-logs" --query primarySharedKey -o tsv

Write-Host "-> Creating Container Apps Environment (skipped if already exists)..." -ForegroundColor Cyan
$existingEnv = az containerapp env show --name $ENV_NAME --resource-group $RESOURCE_GROUP 2>$null
if (-not $existingEnv) {
    az containerapp env create `
        --name $ENV_NAME `
        --resource-group $RESOURCE_GROUP `
        --location $LOCATION `
        --logs-workspace-id $LOG_WS_ID `
        --logs-workspace-key $LOG_WS_KEY `
        --output none
} else {
    Write-Host "   Environment already exists, skipping." -ForegroundColor Gray
}

# =============================================================================
# STEP 2 - Build and push images
# =============================================================================
Write-Host "`n--- STEP 2: Build and push Docker images ---" -ForegroundColor Yellow

Write-Host "-> Logging in to ACR..." -ForegroundColor Cyan
az acr login --name $ACR_NAME

Write-Host "-> Building temporal-worker..." -ForegroundColor Cyan
$WORKER_IMAGE = "$ACR_NAME.azurecr.io/temporal-worker:$IMAGE_TAG"
docker build -t $WORKER_IMAGE ./temporal
docker push $WORKER_IMAGE

Write-Host "-> Building supabase-kong..." -ForegroundColor Cyan
$KONG_IMAGE = "$ACR_NAME.azurecr.io/supabase-kong:$IMAGE_TAG"
docker build -t $KONG_IMAGE ./supabase/kong
docker push $KONG_IMAGE

# Frontend is built after Kong is deployed (we need its FQDN)

# =============================================================================
# STEP 3 - Deploy backend services
# =============================================================================
Write-Host "`n--- STEP 3: Deploy backend services ---" -ForegroundColor Yellow

function Test-ContainerApp {
    param([string]$Name)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $result = az containerapp show --name $Name --resource-group $RESOURCE_GROUP --query "name" -o tsv 2>$null
    $ErrorActionPreference = $prev
    return ($result -and $result.Trim() -ne "")
}

function Deploy-ContainerApp {
    param([string]$Name, [string]$Image, [string]$Ingress, [int]$Port, [string[]]$EnvVars, [string[]]$Command = @())
    Write-Host "-> Deploying $Name..." -ForegroundColor Cyan
    $existing = Test-ContainerApp -Name $Name
    $cmdArgs = @(
        "--name", $Name,
        "--resource-group", $RESOURCE_GROUP,
        "--environment", $ENV_NAME,
        "--image", $Image,
        "--min-replicas", "1",
        "--max-replicas", "1",
        "--env-vars"
    ) + $EnvVars

    if ($Ingress -eq "external") {
        $cmdArgs += @("--ingress", "external", "--target-port", $Port.ToString())
    } elseif ($Ingress -eq "internal") {
        $cmdArgs += @("--ingress", "internal", "--target-port", $Port.ToString())
    }
    # When ingress is "none", omit --ingress entirely (the flag doesn't accept "none")

    if ($Command.Count -gt 0) {
        $cmdArgs += @("--command") + $Command
    }

    if ($existing -eq $true) {
        az containerapp update --name $Name --resource-group $RESOURCE_GROUP --image $Image --output none
    } else {
        az containerapp create @cmdArgs --output none
    }
}

# Supabase DB
Deploy-ContainerApp -Name "supabase-db" -Image "supabase/postgres:15.6.1.143" -Ingress "internal" -Port 5432 -EnvVars @(
    "POSTGRES_PASSWORD=$POSTGRES_PASSWORD",
    "PGPASSWORD=$POSTGRES_PASSWORD",
    "JWT_SECRET=$JWT_SECRET"
)

Write-Host "   Waiting for DB to start (30s)..." -ForegroundColor Gray
Start-Sleep -Seconds 30

# Supabase Auth
Deploy-ContainerApp -Name "supabase-auth" -Image "supabase/gotrue:v2.151.0" -Ingress "internal" -Port 9999 -EnvVars @(
    "GOTRUE_API_HOST=0.0.0.0",
    "GOTRUE_API_PORT=9999",
    "API_EXTERNAL_URL=http://supabase-kong:8000",
    "GOTRUE_DB_DRIVER=postgres",
    "GOTRUE_DB_DATABASE_URL=postgres://supabase_auth_admin:${POSTGRES_PASSWORD}@supabase-db:5432/postgres",
    "GOTRUE_SITE_URL=http://localhost:3000",
    "GOTRUE_DISABLE_SIGNUP=false",
    "GOTRUE_JWT_ADMIN_ROLES=service_role",
    "GOTRUE_JWT_AUD=authenticated",
    "GOTRUE_JWT_DEFAULT_GROUP_NAME=authenticated",
    "GOTRUE_JWT_EXP=3600",
    "GOTRUE_JWT_SECRET=$JWT_SECRET",
    "GOTRUE_MAILER_AUTOCONFIRM=true",
    "GOTRUE_EXTERNAL_PHONE_ENABLED=false"
)

# PostgREST
Deploy-ContainerApp -Name "supabase-rest" -Image "postgrest/postgrest:v12.2.0" -Ingress "internal" -Port 3000 -EnvVars @(
    "PGRST_DB_URI=postgres://authenticator:${POSTGRES_PASSWORD}@supabase-db:5432/postgres",
    "PGRST_DB_SCHEMAS=public",
    "PGRST_DB_ANON_ROLE=anon",
    "PGRST_JWT_SECRET=$JWT_SECRET",
    "PGRST_DB_USE_LEGACY_GUCS=false"
) -Command @("postgrest")

# Kong
Write-Host "-> Deploying supabase-kong..." -ForegroundColor Cyan
$existingKong = Test-ContainerApp -Name "supabase-kong"
if ($existingKong) {
    az containerapp update --name supabase-kong --resource-group $RESOURCE_GROUP --image $KONG_IMAGE --output none
} else {
    az containerapp create `
        --name supabase-kong `
        --resource-group $RESOURCE_GROUP `
        --environment $ENV_NAME `
        --image $KONG_IMAGE `
        --registry-server "$ACR_NAME.azurecr.io" `
        --registry-username $ACR_NAME `
        --registry-password $ACR_PASSWORD `
        --ingress external --target-port 8000 `
        --min-replicas 1 --max-replicas 1 `
        --env-vars "KONG_DATABASE=off" "KONG_DECLARATIVE_CONFIG=/var/lib/kong/kong.yml" "KONG_DNS_ORDER=LAST,A,CNAME" "KONG_PLUGINS=request-transformer,cors,key-auth,acl" `
        --output none
}

Write-Host "   Waiting for Kong to get a public FQDN (20s)..." -ForegroundColor Gray
Start-Sleep -Seconds 20
$KONG_FQDN = az containerapp show --name supabase-kong --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv
$SUPABASE_URL = "https://$KONG_FQDN"
Write-Host "   Supabase URL: $SUPABASE_URL" -ForegroundColor Green

# Temporal DB
Deploy-ContainerApp -Name "temporal-db" -Image "postgres:15-alpine" -Ingress "internal" -Port 5432 -EnvVars @(
    "POSTGRES_USER=temporal",
    "POSTGRES_PASSWORD=$TEMPORAL_DB_PASSWORD",
    "POSTGRES_DB=temporal"
)

Write-Host "   Waiting for Temporal DB (20s)..." -ForegroundColor Gray
Start-Sleep -Seconds 20

# Temporal server
Deploy-ContainerApp -Name "temporal" -Image "temporalio/auto-setup:1.21.3" -Ingress "internal" -Port 7233 -EnvVars @(
    "DB=postgresql",
    "DB_PORT=5432",
    "POSTGRES_USER=temporal",
    "POSTGRES_PWD=$TEMPORAL_DB_PASSWORD",
    "POSTGRES_SEEDS=temporal-db"
)

# Temporal UI
Deploy-ContainerApp -Name "temporal-ui" -Image "temporalio/ui:2.21.2" -Ingress "external" -Port 8080 -EnvVars @(
    "TEMPORAL_ADDRESS=temporal:7233",
    "TEMPORAL_CORS_ORIGINS=*"
)

# Temporal worker
Write-Host "-> Deploying temporal-worker..." -ForegroundColor Cyan
$existingWorker = Test-ContainerApp -Name "temporal-worker"
if ($existingWorker) {
    az containerapp update --name temporal-worker --resource-group $RESOURCE_GROUP --image $WORKER_IMAGE --output none
} else {
    az containerapp create `
        --name temporal-worker `
        --resource-group $RESOURCE_GROUP `
        --environment $ENV_NAME `
        --image $WORKER_IMAGE `
        --registry-server "$ACR_NAME.azurecr.io" `
        --registry-username $ACR_NAME `
        --registry-password $ACR_PASSWORD `
        --min-replicas 1 --max-replicas 1 `
        --env-vars `
            "TEMPORAL_ADDRESS=temporal:7233" `
            "TEMPORAL_NAMESPACE=default" `
            "TEMPORAL_TASK_QUEUE=main" `
            "SUPABASE_URL=http://supabase-kong:8000" `
            "SUPABASE_SERVICE_ROLE_KEY=$SERVICE_ROLE_KEY" `
            "AZURE_AI_ENDPOINT=$AZURE_AI_ENDPOINT" `
            "AZURE_AI_KEY=$AZURE_AI_KEY" `
            "AZURE_AI_MODEL=$AZURE_AI_MODEL" `
        --output none
}

# =============================================================================
# STEP 4 - Build and deploy frontend (needs Kong FQDN)
# =============================================================================
Write-Host "`n--- STEP 4: Build and deploy frontend ---" -ForegroundColor Yellow

Write-Host "-> Building frontend with Supabase URL baked in..." -ForegroundColor Cyan
$FRONTEND_IMAGE = "$ACR_NAME.azurecr.io/frontend:$IMAGE_TAG"
docker build `
    --build-arg "VITE_SUPABASE_URL=$SUPABASE_URL" `
    --build-arg "VITE_SUPABASE_ANON_KEY=$ANON_KEY" `
    --build-arg "VITE_API_URL=$SUPABASE_URL/functions/v1" `
    -t $FRONTEND_IMAGE `
    ./frontend
docker push $FRONTEND_IMAGE

Write-Host "-> Deploying frontend..." -ForegroundColor Cyan
$existingFrontend = Test-ContainerApp -Name "frontend"
if ($existingFrontend) {
    az containerapp update --name frontend --resource-group $RESOURCE_GROUP --image $FRONTEND_IMAGE --output none
} else {
    az containerapp create `
        --name frontend `
        --resource-group $RESOURCE_GROUP `
        --environment $ENV_NAME `
        --image $FRONTEND_IMAGE `
        --registry-server "$ACR_NAME.azurecr.io" `
        --registry-username $ACR_NAME `
        --registry-password $ACR_PASSWORD `
        --ingress external --target-port 3000 `
        --min-replicas 1 --max-replicas 1 `
        --output none
}

# =============================================================================
# STEP 5 - Run database migrations (as a Container App Job inside the env)
# =============================================================================
Write-Host "`n--- STEP 5: Run database migrations ---" -ForegroundColor Yellow
Write-Host "-> Creating migration job (runs inside Container Apps env)..." -ForegroundColor Cyan

# Encode all SQL files into a single base64 string to pass as an env var
$migrationSql = (Get-ChildItem -Path ".\supabase\migrations\*.sql" | Sort-Object Name | ForEach-Object { Get-Content $_ -Raw }) -join "`n"
$sqlB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($migrationSql))
$jobName = "db-migrate-$IMAGE_TAG"

$envId      = az containerapp env show --name $ENV_NAME --resource-group $RESOURCE_GROUP --query id -o tsv
$subId      = az account show --query id -o tsv
$apiUrl     = "https://management.azure.com/subscriptions/$subId/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.App/jobs/${jobName}?api-version=2023-05-01"

# Build the ARM body as a PowerShell hashtable and serialize to JSON.
# This avoids all CLI argument-parsing issues (e.g. -c being treated as --container).
$shellArg   = "echo `$SQL_B64 | base64 -d | psql -h supabase-db -U postgres -d postgres"
$jobBody    = @{
    location   = $LOCATION
    properties = @{
        environmentId = $envId
        configuration = @{
            triggerType           = "Manual"
            replicaTimeout        = 120
            manualTriggerConfig   = @{ replicaCompletionCount = 1; parallelism = 1 }
        }
        template = @{
            containers = @(
                @{
                    name    = "migrate"
                    image   = "postgres:15-alpine"
                    command = @("/bin/sh")
                    args    = @("-c", $shellArg)
                    env     = @(
                        @{ name = "PGPASSWORD"; value = $POSTGRES_PASSWORD }
                        @{ name = "SQL_B64";    value = $sqlB64 }
                    )
                }
            )
        }
    }
}
$tempJson = [System.IO.Path]::GetTempFileName()
($jobBody | ConvertTo-Json -Depth 10 -Compress) | Set-Content $tempJson -Encoding UTF8

# Delete previous migration job if it exists
$prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
az containerapp job delete --name $jobName --resource-group $RESOURCE_GROUP --yes 2>$null
$ErrorActionPreference = $prev

# PUT via REST API — file reference avoids Windows command-line length limits
az rest --method PUT --uri $apiUrl --body "@$tempJson" --output none
Remove-Item $tempJson -ErrorAction SilentlyContinue

# Start the job
az containerapp job start --name $jobName --resource-group $RESOURCE_GROUP --output none
Write-Host "   Migration job started. To check status:" -ForegroundColor Gray
Write-Host "   az containerapp job execution list --name $jobName --resource-group $RESOURCE_GROUP -o table" -ForegroundColor Gray

# =============================================================================
# DONE
# =============================================================================
$FRONTEND_FQDN  = az containerapp show --name frontend     --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv
$TEMPORAL_FQDN  = az containerapp show --name temporal-ui  --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv

Write-Host ""
Write-Host "+------------------------------------------------------+" -ForegroundColor Green
Write-Host "|  Deployment complete!                                |" -ForegroundColor Green
Write-Host "+------------------------------------------------------+" -ForegroundColor Green
Write-Host "|  Frontend:     https://$FRONTEND_FQDN" -ForegroundColor Green
Write-Host "|  Supabase API: $SUPABASE_URL" -ForegroundColor Green
Write-Host "|  Temporal UI:  https://$TEMPORAL_FQDN" -ForegroundColor Green
Write-Host "+------------------------------------------------------+" -ForegroundColor Green
Write-Host "|  Secrets are persisted in .env.azure (gitignored).  |" -ForegroundColor Green
Write-Host "|  Re-runs will reuse the same keys automatically.     |" -ForegroundColor Green
Write-Host "+------------------------------------------------------+" -ForegroundColor Green
